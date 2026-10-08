"""Safeguard evaluations: must-hold recall, disagreement detection and dated values.

Phase 0 of the safeguards work: put a number on each gap before building, then keep the
numbers as regression checks. Every evaluation runs on a scratch copy of a vault and a
throwaway session ledger, so nothing here touches a real Brain or its history.

MUST-HOLD RECALL. For a constraint note, requests from its domain that never name it ("plan
Tuesday dinner" for a peanut allergy) and decoys from other domains. The constraint counts as
delivered when the packet carries it: in its "Must hold" section, among the notes it selected,
or in the startup context when the note is standing. `relevance_only` first sets every target
note to `load: on-demand` in the copy, which measures what relevance alone does.

DISAGREEMENT. Labeled pairs of statements (contradicts, narrows, extends, agrees, unrelated).
A detector says whether the second disagrees with the first; recall and precision are over
"contradicts".

DATED VALUES. Two or more dated notes give a figure for the same subject; a request asks for
it. The packet should carry the newest and leave the older ones out, or mark them as older.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile

from . import frontmatter as fm
from . import util

KNOWLEDGE = "knowledge"


# ---------------------------------------------------------------------------- scratch vaults
def copy_vault(src: str, models_dir: str | None = None) -> str:
    """A scratch copy of `src` (a vault folder) without its runtime state. With `models_dir`
    (a folder holding a downloaded embedding model), the copy can match by meaning."""
    root = tempfile.mkdtemp(prefix="brain-safeguards-")
    dest = os.path.join(root, "vault")
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".brain", ".git"))
    if models_dir:
        target = os.path.join(dest, ".brain", "models")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(models_dir, target)
    return dest


def _note_files(vault: str) -> dict[str, str]:
    """{note id: path} for every note file under knowledge/."""
    out = {}
    for base, _dirs, files in os.walk(os.path.join(vault, KNOWLEDGE)):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(base, name)
            meta, _body, _errors = fm.parse(util.read_text(path))
            if meta.get("id"):
                out[str(meta["id"])] = path
    return out


def set_meta(vault: str, note_ids, **changes) -> list[str]:
    """Rewrite these notes' front matter in place (a scratch copy only): a value of None
    removes the key. Returns the ids it changed."""
    files = _note_files(vault)
    done = []
    for note_id in note_ids:
        path = files.get(note_id)
        if path is None:
            continue
        meta, body, _errors = fm.parse(util.read_text(path))
        for key, value in changes.items():
            if value is None:
                meta.pop(key, None)
            else:
                meta[key] = value
        util.atomic_write(path, fm.dump(meta, body, order=["id", "title", "summary"]))
        done.append(note_id)
    return done


def add_notes(vault: str, notes) -> None:
    """Write notes straight into a scratch copy (bypassing governance, which is fine for a
    measurement): each a dict with id, area, topic, body and any other front matter."""
    for spec in notes:
        meta = {key: value for key, value in spec.items() if key != "body"}
        meta.setdefault("status", "approved")
        meta.setdefault("scope", "company")
        meta.setdefault("load", "on-demand")
        meta.setdefault("kind", "state")
        meta.setdefault("added", util.today())
        meta.setdefault("supersedes", "none")
        folder = os.path.join(vault, KNOWLEDGE, meta["area"], meta["topic"])
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{meta['added']}-{meta['id']}.md")
        util.atomic_write(path, fm.dump(meta, spec["body"], order=["id", "title", "summary"]))


def open_brain(vault: str, semantic: bool = False):
    from .api import Brain
    from .sessions import Ledger
    brain = Brain(vault, embeddings=semantic, rerank=False)
    scratch = tempfile.mkdtemp(prefix="brain-safeguards-ledger-")
    brain._ledger = Ledger(os.path.join(scratch, "sessions.sqlite"), 30)
    return brain


def _delivered(brain, data) -> set[str]:
    """Every note id this packet carried, the startup context's standing notes included."""
    st = brain.state()
    chain = data.get("scope_chain") or []
    standing = {n.id for n in st.index.notes.values() if n.standing and n.scope in chain}
    return (set(data.get("note_ids") or []) | set(data.get("must_hold_ids") or [])
            | set(data.get("standing_ids") or []) | standing)


# ---------------------------------------------------------------------------- must-holds
def must_hold_eval(brain, cases) -> dict:
    """Recall over in-domain requests and the inclusion rate over decoys, per note and in all.
    Held-out requests (written after a must-hold's triggers were fixed) are scored apart."""
    rows, misses, decoy_hits = [], [], []
    hit = total = decoy_in = decoys = held_hit = held_total = 0
    for case in cases:
        note = case["note"]
        got = 0
        for request in case.get("held_out") or []:
            data = brain.context(request, record=False, include_kernel=False).data
            held_total += 1
            if note in _delivered(brain, data):
                held_hit += 1
            else:
                misses.append({"note": note, "request": request, "held_out": True,
                               "listed": note in set(data.get("related_ids") or [])})
        for request in case.get("requests") or []:
            data = brain.context(request, record=False, include_kernel=False).data
            total += 1
            if note in _delivered(brain, data):
                hit += 1
                got += 1
            else:
                misses.append({"note": note, "request": request,
                               "listed": note in set(data.get("related_ids") or [])})
        dgot = 0
        for request in case.get("decoys") or []:
            data = brain.context(request, record=False, include_kernel=False).data
            decoys += 1
            # A decoy counts only what this request's packet chose, not the startup context.
            chosen = set(data.get("note_ids") or []) | set(data.get("must_hold_ids") or [])
            if note in chosen:
                decoy_in += 1
                dgot += 1
                decoy_hits.append({"note": note, "request": request})
        rows.append({"note": note, "recall": round(got / max(1, len(case.get("requests") or [])), 3),
                     "decoy_rate": round(dgot / max(1, len(case.get("decoys") or [])), 3)})
    return {"recall": round(hit / total, 3) if total else 1.0,
            "decoy_rate": round(decoy_in / decoys, 3) if decoys else 0.0,
            "held_out_recall": round(held_hit / held_total, 3) if held_total else None,
            "held_out": held_total,
            "requests": total, "decoys": decoys, "by_note": rows, "misses": misses,
            "decoy_hits": decoy_hits}


def run_must_holds(brains_root: str, spec: dict, *, relevance_only: bool = False,
                   models_dir: str | None = None) -> dict:
    """Run the must-hold cases for every packaged Brain they name."""
    by_brain: dict[str, list] = {}
    for case in spec.get("cases") or []:
        by_brain.setdefault(case["brain"], []).append(case)
    results, rows, misses, decoy_hits = {}, [], [], []
    hit = total = decoy_in = decoys = held_hit = held_total = 0
    for name, cases in sorted(by_brain.items()):
        vault = copy_vault(os.path.join(brains_root, name, "vault"), models_dir)
        try:
            if relevance_only:
                set_meta(vault, [c["note"] for c in cases], load="on-demand",
                         applies_to=None, triggers=None, critical=None)
            brain = open_brain(vault, semantic=bool(models_dir))
            try:
                result = must_hold_eval(brain, cases)
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
        results[name] = result
        hit += round(result["recall"] * result["requests"])
        total += result["requests"]
        decoy_in += round(result["decoy_rate"] * result["decoys"])
        decoys += result["decoys"]
        if result["held_out"]:
            held_hit += round(result["held_out_recall"] * result["held_out"])
            held_total += result["held_out"]
        rows += [dict(r, brain=name) for r in result["by_note"]]
        misses += [dict(m, brain=name) for m in result["misses"]]
        decoy_hits += [dict(d, brain=name) for d in result["decoy_hits"]]
    return {"recall": round(hit / total, 3) if total else 1.0,
            "decoy_rate": round(decoy_in / decoys, 3) if decoys else 0.0,
            "held_out_recall": round(held_hit / held_total, 3) if held_total else None,
            "held_out": held_total,
            "requests": total, "decoys": decoys, "by_note": rows, "misses": misses,
            "decoy_hits": decoy_hits, "brains": results}


# ---------------------------------------------------------------------------- disagreement
def tension_eval(pairs, detect) -> dict:
    """`detect(existing, proposed)` is truthy when the second disagrees with the first."""
    tp = fp = fn = tn = 0
    missed, wrong = [], []
    for pair in pairs:
        positive = pair["relation"] == "contradicts"
        said = bool(detect(pair["a"], pair["b"]))
        if positive and said:
            tp += 1
        elif positive:
            fn += 1
            missed.append(pair)
        elif said:
            fp += 1
            wrong.append(pair)
        else:
            tn += 1
    recall = tp / (tp + fn) if tp + fn else 1.0
    precision = tp / (tp + fp) if tp + fp else 1.0
    return {"recall": round(recall, 3), "precision": round(precision, 3),
            "pairs": len(pairs), "contradictions": tp + fn, "missed": missed,
            "false_alarms": wrong}


# ---------------------------------------------------------------------------- dated values
def run_time_cases(brains_root: str, cases, *, models_dir: str | None = None) -> dict:
    """For each case, add its dated notes to a scratch copy and ask its request. Success is
    the newest value delivered without an older one left unmarked beside it."""
    rows = []
    good = 0
    for case in cases:
        vault = copy_vault(os.path.join(brains_root, case["brain"], "vault"), models_dir)
        try:
            add_notes(vault, case["notes"])
            brain = open_brain(vault, semantic=bool(models_dir))
            try:
                data = brain.context(case["request"], record=False,
                                     include_kernel=False).data
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
        delivered = set(data.get("note_ids") or [])
        older_marked = set(data.get("older_ids") or [])
        newest = case["newest"] in delivered
        stale_left = [o for o in case["older"] if o in delivered and o not in older_marked]
        ok = newest and not stale_left
        good += ok
        rows.append({"id": case["id"], "newest_delivered": newest,
                     "older_unmarked": stale_left, "ok": ok})
    return {"score": round(good / len(cases), 3) if cases else 1.0, "cases": rows}


def load_spec(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
