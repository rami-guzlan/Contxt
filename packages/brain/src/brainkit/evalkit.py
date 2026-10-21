"""Retrieval measured across many Brains, the way anybody's Brain would be served
(general-retrieval plan, stage 0).

A suite is a list of Brains, each a vault and its labeled requests:

    generated   tests/evals/general/<name>/{vault, requests.json, labels.json}: a persona's
                notes written by one model, requests written by another from the persona
                alone, labels written by reading the notes; splits.json puts each Brain in
                tuning, validation or sealed
    demo        the packaged starters and tests/evals/retrieval.json (already tuned on)
    private     any vault with an eval.json, such as a person's own Brain; only numbers are
                ever reported for it, never its requests or note ids

Every Brain runs on a scratch copy and a throwaway session ledger. Zero-config (the default)
empties routing.json and topics.md and removes must-hold trigger words, as a new person's
Brain starts; `configured=True` keeps them, to show the gap.

Each Brain is also asked the off-topic scoring set (off_topic.json), and may be asked the
calibration bank (null_requests.txt). The calibration bank is what a Brain sets its bar
for "nothing here" from, so once that is in use its correct-nothing rate is a fit, not a
result: the scoring set is the one to read.

Measures are counts (k of n), so each has a Wilson interval: recall (needed notes the brief
carried, whole or in short, or the session already held), whole recall, reachable recall
(listed too, one notes_get away), precision (delivered notes that were needed or useful),
correct nothing (the Brain's own off-topic requests and the scoring set), false nothing
(needed something, got nothing), must-hold recall and decoys. Tokens and latency are lists.
Across Brains: the mean of each Brain's rate (every Brain counts alike), the worst Brain,
and the pooled rate.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import time
from collections.abc import Callable, Iterable

from . import evaluate
from . import safeguards_eval as se

# Measures where a higher rate is worse: the worst Brain is the highest.
LOWER_IS_BETTER = {"false_nothing", "must_hold_decoys", "off_topic_must_holds"}
MEASURES = ("recall", "whole_recall", "reachable", "precision", "correct_nothing",
            "off_topic_nothing", "null_nothing", "false_nothing", "must_hold_recall",
            "must_hold_decoys", "off_topic_must_holds")
LABELS = {
    "recall": "Needed-note recall", "whole_recall": "Whole", "reachable": "Reachable",
    "precision": "Precision", "correct_nothing": "Own off-topic: nothing",
    "off_topic_nothing": "Off-topic set: nothing", "null_nothing": "Calibration bank: nothing",
    "false_nothing": "False nothing", "must_hold_recall": "Must-hold recall",
    "must_hold_decoys": "Must-hold decoys", "off_topic_must_holds": "Must-holds off topic",
}


# ---------------------------------------------------------------------------- arithmetic
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """The Wilson score interval for k successes in n (95% by default)."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(pair) -> float | None:
    k, n = pair
    return k / n if n else None


def across(results: list[dict]) -> dict:
    """Per measure: the mean of each Brain's rate, the worst Brain, the pooled rate and its
    interval. A Brain with no cases for a measure is left out of it."""
    out = {}
    for measure in MEASURES:
        rows = [(r["name"], r["counts"][measure]) for r in results
                if measure in r["counts"] and r["counts"][measure][1]]
        if not rows:
            continue
        rates = [(name, k / n) for name, (k, n) in rows]
        pick = max if measure in LOWER_IS_BETTER else min
        worst = pick(rates, key=lambda item: item[1])
        k = sum(pair[0] for _name, pair in rows)
        n = sum(pair[1] for _name, pair in rows)
        out[measure] = {"mean": statistics.fmean(r for _n, r in rates), "brains": len(rows),
                        "worst": {"brain": worst[0], "rate": worst[1]},
                        "pooled": k / n, "interval": wilson(k, n), "k": k, "n": n}
    return out


def leave_one_out(brains: list[dict], fit: Callable, score: Callable) -> list:
    """Fit on every Brain but one, score that one, for each Brain: what anything fitted
    would do on a Brain it never saw."""
    out = []
    for index, brain in enumerate(brains):
        train = brains[:index] + brains[index + 1:]
        out.append(score(brain, fit(train)))
    return out


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


# ---------------------------------------------------------------------------- the Brains
def null_requests() -> list[str]:
    """The calibration bank: requests unrelated to anyone's notes."""
    from .calibration import null_bank
    return null_bank()


def off_topic_cases(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        spec = json.load(handle)
    return [{"id": r["id"], "request": r["request"], "must": [], "useful": [], "noise": [],
             "must_holds": [], "nothing": True, "set": "off_topic"}
            for r in spec["requests"]]


def null_cases() -> list[dict]:
    return [{"id": f"null-{i:03d}", "request": text, "must": [], "useful": [], "noise": [],
             "must_holds": [], "nothing": True, "set": "null"}
            for i, text in enumerate(null_requests(), 1)]


def generated_brains(root: str, splits: Iterable[str] | None = None) -> list[dict]:
    """The generated Brains under `root` that have a vault, requests and labels."""
    with open(os.path.join(root, "splits.json"), encoding="utf-8") as handle:
        split_of = json.load(handle)
    wanted = set(splits) if splits else None
    out = []
    for name in sorted(split_of):
        folder = os.path.join(root, name)
        paths = [os.path.join(folder, part) for part in ("vault", "requests.json",
                                                          "labels.json")]
        if not all(os.path.exists(p) for p in paths):
            continue
        if wanted is not None and split_of[name] not in wanted:
            continue
        with open(paths[1], encoding="utf-8") as handle:
            requests = json.load(handle)
        with open(paths[2], encoding="utf-8") as handle:
            labels = {c["id"]: c for c in json.load(handle)["cases"]}
        cases = []
        for request in requests:
            label = labels.get(request["id"]) or {}
            cases.append({"id": request["id"], "request": request["request"],
                          "kind": request.get("kind", "work"),
                          "must": label.get("must") or [], "useful": label.get("useful") or [],
                          "noise": label.get("noise") or [],
                          "must_holds": label.get("must_holds") or [],
                          "nothing": bool(label.get("nothing")), "set": "own",
                          "labeled": request["id"] in labels})
        out.append({"name": name, "split": split_of[name], "vault": paths[0],
                    "cases": cases, "private": False, "must_hold_labels": True})
    return out


def demo_brains(brains_root: str, spec: dict) -> list[dict]:
    """The packaged starters with their labeled requests (tests/evals/retrieval.json)."""
    by_brain: dict[str, list] = {}
    for case in spec.get("cases") or []:
        by_brain.setdefault(case["brain"], []).append(
            dict(case, must_holds=[], nothing=bool(case.get("nothing")), set="own",
                 holdout=False))
    return [{"name": name, "split": "demo", "vault": os.path.join(brains_root, name, "vault"),
             "cases": cases, "private": False} for name, cases in sorted(by_brain.items())]


def private_brain(vault: str, name: str = "private") -> dict:
    """A Brain with its own eval.json (a person's real Brain): numbers only, ever."""
    with open(os.path.join(vault, "eval.json"), encoding="utf-8") as handle:
        spec = json.load(handle)
    cases = [dict(c, must_holds=c.get("must_holds") or [], nothing=bool(c.get("nothing")),
                  set="own", holdout=False) for c in spec.get("cases") or []]
    return {"name": name, "split": "private", "vault": vault, "cases": cases, "private": True}


# ---------------------------------------------------------------------------- one Brain
def zero_config(vault: str) -> None:
    """Make a scratch copy start as a new person's Brain does: no routing.json hints, no
    topics.md lines, no must-hold trigger words."""
    with open(os.path.join(vault, "routing.json"), "w", encoding="utf-8") as handle:
        handle.write("{}\n")
    with open(os.path.join(vault, "topics.md"), "w", encoding="utf-8") as handle:
        handle.write("# Topics\n")
    with_triggers = []
    for note_id, path in se._note_files(vault).items():
        with open(path, encoding="utf-8") as handle:
            if "\ntriggers:" in handle.read():
                with_triggers.append(note_id)
    se.set_meta(vault, with_triggers, triggers=None)


ENRICHMENT = ("asked_as", "applies_when", "not_when", "role", "suggested_triggers", "enriched",
              "enriched_by", "enriched_hash")


def strip_enrichment(vault: str) -> None:
    """Make a scratch copy as a Brain without a model would be: no enrichment fields."""
    enriched = []
    for note_id, path in se._note_files(vault).items():
        with open(path, encoding="utf-8") as handle:
            if "\nasked_as:" in handle.read():
                enriched.append(note_id)
    se.set_meta(vault, enriched, **{key: None for key in ENRICHMENT})


def run_brain(entry: dict, *, models_dir: str | None = None, configured: bool = False,
              extra: Iterable[dict] = (), prepare: Callable | None = None,
              enriched: bool = True) -> dict:
    """Score one Brain on its labeled requests plus `extra` (off-topic sets), on a scratch
    copy. `prepare(vault)` may change the copy first (a stage's experiment)."""
    vault = se.copy_vault(entry["vault"], models_dir)
    try:
        if not configured:
            zero_config(vault)
        if not enriched:
            strip_enrichment(vault)
        if prepare is not None:
            prepare(vault)
        cases = [c for c in entry["cases"] if c.get("labeled", True)] + list(extra)
        spec_path = os.path.join(os.path.dirname(vault), "eval.json")
        with open(spec_path, "w", encoding="utf-8") as handle:
            json.dump({"cases": cases}, handle)
        brain = se.open_brain(vault, semantic=bool(models_dir))
        try:
            started = time.perf_counter()
            st = brain.state()
            brain.context("warm up", record=False)
            build_ms = (time.perf_counter() - started) * 1000
            must_holds = sorted(n.id for n in st.index.notes.values() if n.must_hold)
            note_count = len(st.index.notes)
            rows = evaluate.run(brain, spec_path)["rows"]
        finally:
            brain.close()
    finally:
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    by_id = {c["id"]: c for c in cases}
    for row in rows:
        case = by_id[row["id"]]
        row["set"] = case.get("set", "own")
        row["must_holds_expected"] = case.get("must_holds") or []
    return {"name": entry["name"], "split": entry["split"], "private": entry["private"],
            "notes": note_count, "build_ms": round(build_ms),
            "counts": counts(rows, must_holds if entry.get("must_hold_labels") else []),
            "tokens": [r["tokens"] or 0 for r in rows if r["set"] == "own"],
            "ms": [r["ms"] for r in rows], "rows": rows}


def counts(rows: list[dict], must_holds: list[str]) -> dict:
    """Every measure as [k, n]. `must_holds` is empty for a Brain whose requests are not
    labeled with the must-holds in play: its must-hold measures are then not counted."""
    own = [r for r in rows if r["set"] == "own"]
    work = [r for r in own if not r.get("nothing_expected")]
    out: dict[str, list[int]] = {
        "recall": [sum(r["hits"] for r in own), sum(r["must"] for r in own)],
        "whole_recall": [sum(r["body_hits"] for r in own), sum(r["must"] for r in own)],
        "reachable": [sum(r["reach"] for r in own), sum(r["must"] for r in own)],
        "precision": [sum(r["good"] for r in work), sum(r["delivered"] for r in work)],
    }
    for measure, subset in (("correct_nothing", [r for r in own if r.get("nothing_expected")]),
                            ("off_topic_nothing", [r for r in rows if r["set"] == "off_topic"]),
                            ("null_nothing", [r for r in rows if r["set"] == "null"])):
        out[measure] = [sum(bool(r["got_nothing"]) for r in subset), len(subset)]
    needed = [r for r in own if r["must"]]
    out["false_nothing"] = [sum(bool(r["got_nothing"]) for r in needed), len(needed)]
    hit = pairs = decoy = chances = 0
    for row in own:
        carried = set(row.get("must_holds") or []) | set(row.get("notes") or [])
        expected = set(row["must_holds_expected"])
        for note in must_holds:
            if note in expected:
                pairs += 1
                hit += note in carried
            else:
                chances += 1
                decoy += note in carried
    if must_holds:
        out["must_hold_recall"] = [hit, pairs]
        out["must_hold_decoys"] = [decoy, chances]
    off = [r for r in rows if r["set"] in ("off_topic", "null")]
    if must_holds:
        out["off_topic_must_holds"] = [
            sum(bool(set(r.get("must_holds") or []) & set(must_holds)) for r in off),
            len(off)]
    return out


def run_suite(entries: list[dict], *, models_dir: str | None = None,
              configured: bool = False, off_topic: list[dict] | None = None,
              null_bank: bool = False, prepare: Callable | None = None,
              progress: Callable | None = None, enriched: bool = True) -> list[dict]:
    extra = list(off_topic or []) + (null_cases() if null_bank else [])
    results = []
    for entry in entries:
        if progress:
            progress(entry["name"])
        results.append(run_brain(entry, models_dir=models_dir, configured=configured,
                                 extra=extra, prepare=prepare, enriched=enriched))
    return results


# ---------------------------------------------------------------------------- scale
def scale_vault(sources: list[str], size: int) -> str:
    """A scratch Brain of about `size` notes for latency: the first source's vault, filled
    with copies of every source's on-demand notes, each copy with its own id, topic and a
    line that tells it apart, so the index sees `size` different notes."""
    from . import frontmatter as fm
    from . import util
    vault = se.copy_vault(sources[0])
    with open(os.path.join(vault, "brain.json"), encoding="utf-8") as handle:
        areas = [a for a in json.load(handle)["structure"]["areas"]
                 if a not in ("projects", "topics")]
    pool = []
    for source in sources:
        label = os.path.basename(os.path.dirname(os.path.abspath(source)))
        for path in se._note_files(source).values():
            meta, body, _errors = fm.parse(util.read_text(path))
            if meta.get("load", "on-demand") == "on-demand" and not meta.get("project"):
                pool.append((label, meta, body))
    have = len(se._note_files(vault))
    notes, copy = [], 0
    while have + len(notes) < size and pool:
        label, meta, body = pool[copy % len(pool)]
        round_ = copy // len(pool)
        notes.append({
            "id": f"{meta['id']}-{label}-{round_}", "title": meta.get("title") or meta["id"],
            "summary": meta.get("summary") or "", "area": areas[copy % len(areas)],
            "topic": f"{label}-{meta.get('topic') or 'misc'}-{round_}",
            "kind": meta.get("kind") or "fact", "added": str(meta.get("added") or ""),
            "source": "scale test", "body": f"{body.strip()}\n\nFrom set {label} {round_}.\n"})
        copy += 1
    se.add_notes(vault, notes)
    return vault


def latency_at(sources: list[str], size: int, requests: list[str], *,
               models_dir: str | None = None) -> dict:
    """The first brief's time (the index built) and p50/p95 for `requests` on a Brain of
    about `size` notes, each request in its own conversation."""
    vault = scale_vault(sources, size)
    if models_dir:
        target = os.path.join(vault, ".brain", "models")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(models_dir, target)
    try:
        brain = se.open_brain(vault, semantic=bool(models_dir))
        try:
            started = time.perf_counter()
            notes = len(brain.state().index.notes)
            brain.context("warm up", session_id="sess-warm")
            build_ms = (time.perf_counter() - started) * 1000
            ms = []
            for index, request in enumerate(requests):
                started = time.perf_counter()
                brain.context(request, session_id=f"sess-lat-{index:03d}")
                ms.append((time.perf_counter() - started) * 1000)
        finally:
            brain.close()
    finally:
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return {"notes": notes, "build_ms": build_ms, "p50": percentile(ms, 0.5),
            "p95": percentile(ms, 0.95)}


# ---------------------------------------------------------------------------- reporting
def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _cell(pair) -> str:
    k, n = pair
    if not n:
        return "n/a"
    low, high = wilson(k, n) or (0.0, 0.0)
    return f"{k / n:.0%} ({low:.0%} to {high:.0%})"


def latency(result: dict) -> dict:
    ms = result.get("ms") or []
    return {"p50": percentile(ms, 0.5), "p95": percentile(ms, 0.95)}


def markdown(results: list[dict], *, title: str, columns: Iterable[str] | None = None) -> str:
    """Per-Brain rows and, per split, the mean, worst Brain and pooled rate. A private
    Brain shows numbers only: no request, no note id, no miss list."""
    columns = list(columns or ("recall", "reachable", "precision", "off_topic_nothing",
                               "correct_nothing", "false_nothing", "must_hold_recall",
                               "must_hold_decoys"))
    lines = [f"## {title}", "",
             "| Brain | Split | Notes | " + " | ".join(LABELS[c] for c in columns)
             + " | Avg tokens | p95 ms |",
             "| --- | --- | --- | " + " | ".join("---" for _ in columns) + " | --- | --- |"]
    for r in results:
        tokens = r.get("tokens") or []
        avg = round(statistics.fmean(tokens)) if tokens else 0
        p95 = latency(r)["p95"]
        lines.append(f"| {r['name']} | {r['split']} | {r.get('notes', '')} | "
                     + " | ".join(_cell(r["counts"].get(c, [0, 0])) for c in columns)
                     + f" | {avg} | {'' if p95 is None else round(p95)} |")
    for split in dict.fromkeys(r["split"] for r in results):
        group = [r for r in results if r["split"] == split]
        if len(group) < 2:
            continue
        summary = across(group)
        lines += ["", f"**{split}** ({len(group)} Brains): "
                  + "; ".join(f"{LABELS[c].lower()} mean {_pct(summary[c]['mean'])}, worst "
                              f"{_pct(summary[c]['worst']['rate'])} "
                              f"({summary[c]['worst']['brain']})"
                              for c in columns if c in summary) + "."]
    return "\n".join(lines) + "\n"


def misses(results: list[dict]) -> str:
    """What each non-private Brain missed or got wrong, for reading while tuning (never
    for sealed Brains: those are read once, at the end of a stage)."""
    lines = []
    for r in results:
        if r["private"] or r["split"] == "sealed":
            continue
        for row in r["rows"]:
            parts = []
            if row["set"] == "own" and row["missed"]:
                parts.append("missed " + "; ".join(" or ".join(g) for g in row["missed"]))
            if row["set"] == "own" and row["noise"]:
                parts.append("noise " + ", ".join(row["noise"]))
            if row.get("nothing_expected") and not row["got_nothing"]:
                parts.append("should get nothing, got "
                             + ", ".join(row.get("notes") or ["parts of files"]))
            expected = set(row.get("must_holds_expected") or [])
            lost = expected - set(row.get("must_holds") or []) - set(row.get("notes") or [])
            if lost:
                parts.append("must-hold missed " + ", ".join(sorted(lost)))
            if parts:
                lines.append(f"- {r['name']}, {row['id']}: {'; '.join(parts)}")
    return "\n".join(lines) + ("\n" if lines else "")


def public(result: dict) -> dict:
    """A result safe to save or print: rows dropped for a private Brain."""
    if not result.get("private"):
        return result
    return {k: v for k, v in result.items() if k != "rows"}


# ---------------------------------------------------------------------------- learning
def learning_effect(entry: dict, *, models_dir: str | None = None) -> dict:
    """Stage 4's measure: half the work requests are asked, and for each needed note the
    brief neither carried nor listed the conversation opens it (as an AI that searched
    would); the Brain learns from those gaps. Both halves are asked again: the first half
    shows what was learned, the second whether it carries to other requests."""
    from . import learn
    work = [c for c in entry["cases"] if c.get("must") and c.get("labeled", True)]
    halves = (work[0::2], work[1::2])
    vault = se.copy_vault(entry["vault"], models_dir)
    try:
        zero_config(vault)
        brain = se.open_brain(vault, semantic=bool(models_dir))
        try:
            def reach(cases, tag):
                hit = total = 0
                for i, case in enumerate(cases):
                    data = brain.context(case["request"], session_id=f"sess-{tag}-{i:03d}").data
                    got = set(data.get("note_ids") or []) | set(data.get("related_ids") or [])
                    got |= set(data.get("must_hold_ids") or [])
                    total += len(case["must"])
                    hit += sum(bool(got & set(g)) for g in case["must"])
                return [hit, total]
            before = [reach(halves[0], "a0"), reach(halves[1], "b0")]
            for i, case in enumerate(halves[0]):
                session = f"sess-learn-{i:03d}"
                data = brain.context(case["request"], session_id=session).data
                got = set(data.get("note_ids") or []) | set(data.get("related_ids") or [])
                for group in case["must"]:
                    if not got & set(group):
                        brain.note(group[0], session_id=session)
            learned = learn.from_gaps(brain)
            after = [reach(halves[0], "a1"), reach(halves[1], "b1")]
        finally:
            brain.close()
    finally:
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return {"name": entry["name"], "split": entry["split"], "learned": len(learned["learned"]),
            "asked": {"before": before[0], "after": after[0]},
            "other": {"before": before[1], "after": after[1]}}
