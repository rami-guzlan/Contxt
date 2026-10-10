"""The private eval set: real requests from this brain's ledger, labeled by its owner
(brain-logic plan 10.1).

`sample` draws requests the brain served, spread over request types and newest first, with the
notes each brief carried, into the vault's runtime folder (`.brain/eval/private.json`), in the
format `evaluate.py` reads. A case waits unlabeled until the owner says, for each note the brief
carried, whether it was needed, useful or noise, and names any note it should have carried.
Every labeled case whose id hashes into the last quarter is held out, so about a quarter of
the set is never tuned on.

The set is the owner's own requests: it lives with the vault's runtime state, never in the
engine's repository, and is never sent anywhere.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import tempfile

from . import util

HELD_OUT = 0.3


def path(brain) -> str:
    return os.path.join(brain.vault.runtime_dir, "eval", "private.json")


def load(brain) -> dict:
    try:
        with open(path(brain), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = {}
    data.setdefault("cases", [])
    data.setdefault("thresholds", {"holdout_must_recall": 0.9})
    return data


def save(brain, data: dict) -> None:
    target = path(brain)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    util.atomic_write(target, json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def _held_out(case_id: str) -> bool:
    digest = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:8], 16)
    return (digest % 100) < int(HELD_OUT * 100)


def sample(brain, n: int = 80, *, days: int = 60) -> dict:
    """Add up to `n` logged requests not yet in the set, spread over request types."""
    data = load(brain)
    have = {c.get("packet_id") for c in data["cases"]}
    known = {" ".join(str(c.get("request") or "").lower().split()) for c in data["cases"]}
    since = (util.now() - _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_type: dict[str, list] = {}
    for row in reversed(brain.ledger.packet_rows(since)):
        text = " ".join(str(row.get("request") or "").split())
        payload = row.get("data") or {}
        if (row["id"] in have or not text or text.lower() in known or len(text) < 12
                or not (payload.get("note_ids") or payload.get("related_ids"))):
            continue
        known.add(text.lower())
        by_type.setdefault(str(payload.get("request_type") or "standard"), []).append(row)
    added = []
    while len(added) < n and any(by_type.values()):
        for kind in sorted(by_type):
            if by_type[kind] and len(added) < n:
                added.append(by_type[kind].pop(0))
    for row in added:
        payload = row.get("data") or {}
        data["cases"].append({
            "id": f"real-{row['id'][-10:]}", "packet_id": row["id"], "request": row["request"],
            "request_type": payload.get("request_type"), "at": row["at"],
            "partition": payload.get("partition"),
            "delivered": list(payload.get("note_ids") or []),
            "listed": list(payload.get("related_ids") or []),
            "labeled": False, "must": [], "useful": [], "noise": []})
    save(brain, data)
    return {"added": len(added), "cases": len(data["cases"]),
            "labeled": sum(1 for c in data["cases"] if c.get("labeled"))}


def case_for(brain, packet_id: str) -> dict | None:
    return next((c for c in load(brain)["cases"] if c.get("packet_id") == packet_id), None)


def label(brain, case_id: str, *, needed=(), useful=(), noise=(), missing=()) -> dict:
    """The owner's labels for one case: needed notes (each a must), useful ones, noise, and
    notes the brief should have carried (also musts)."""
    data = load(brain)
    case = next((c for c in data["cases"] if c["id"] == case_id or
                 c.get("packet_id") == case_id), None)
    if case is None:
        raise KeyError(case_id)
    st = brain.state()
    unknown = [i for i in [*needed, *useful, *noise, *missing] if st.index.note(i) is None]
    if unknown:
        raise ValueError(f"No such note: {', '.join(sorted(set(unknown)))}")
    case["must"] = [[i] for i in dict.fromkeys([*needed, *missing])]
    case["useful"] = list(dict.fromkeys(useful))
    case["noise"] = list(dict.fromkeys(noise))
    case["missing"] = list(dict.fromkeys(missing))
    case["labeled"] = True
    case["holdout"] = _held_out(case["id"])
    case["labeled_at"] = util.now_iso()
    save(brain, data)
    return case


def add(brain, request: str, packet_id: str | None = None) -> dict:
    """Put one logged request in the set (from Activity), unlabeled."""
    data = load(brain)
    found = next((c for c in data["cases"] if packet_id and c.get("packet_id") == packet_id),
                 None)
    if found is not None:
        return found
    payload = (brain.ledger.packet(packet_id) or {}).get("data") or {} if packet_id else {}
    case = {"id": f"real-{(packet_id or util.sha256(request))[-10:]}", "packet_id": packet_id,
            "request": request, "request_type": payload.get("request_type"),
            "partition": payload.get("partition"),
            "at": util.now_iso(), "delivered": list(payload.get("note_ids") or []),
            "listed": list(payload.get("related_ids") or []), "labeled": False,
            "must": [], "useful": [], "noise": []}
    data["cases"].append(case)
    save(brain, data)
    return case


def status(brain) -> dict:
    cases = load(brain)["cases"]
    labeled = [c for c in cases if c.get("labeled")]
    return {"path": path(brain), "cases": len(cases), "labeled": len(labeled),
            "held_out": sum(1 for c in labeled if c.get("holdout")),
            "by_type": {t: sum(1 for c in labeled if c.get("request_type") == t)
                        for t in sorted({str(c.get("request_type")) for c in labeled})}}


def run(brain, *, holdout: bool | None = None) -> dict:
    """Score the brain on the labeled cases (evaluate.py)."""
    from . import evaluate
    data = load(brain)
    cases = [c for c in data["cases"] if c.get("labeled")]
    if not cases:
        return {"cases": 0, "labeled": 0}
    with tempfile.TemporaryDirectory(prefix="brain-private-eval-") as folder:
        spec = os.path.join(folder, "eval.json")
        with open(spec, "w", encoding="utf-8") as handle:
            json.dump({"cases": cases, "thresholds": data.get("thresholds") or {}}, handle)
        return evaluate.run(brain, spec, holdout=holdout)
