"""Time as knowledge in motion (v4 backend plan, 13.3), not hours worked.

The timeline is built from the decision journal (`journal/decisions.jsonl`, history.py):
entries kept (a proposal approved or applied), changed (edited, updated, restored), superseded
(replaced by a kept one), disputed (marked so) and archived, in a window, newest first. Each
carries both dates: when it was recorded, and from when it was true (its `as_of`, else when it
was added). Reads are scope-filtered: an entry the caller may not see is left out, with no
count.

"What changed since my last session" is the timeline since this app's last conversation (the
session ledger), as one line in a new conversation's first packet; the details are one call
away.
"""
from __future__ import annotations

import datetime as dt

from .scopes import Scopes

KINDS = {"approved": "kept", "auto-applied": "kept", "edited": "changed", "updated": "changed",
         "restored": "changed", "reverted": "changed", "redone": "changed",
         "unarchived": "changed", "verified": "verified", "archived": "archived"}
ORDER = ("kept", "changed", "superseded", "disputed", "verified", "archived")
LIMIT = 50


def _entry(index, note_id: str):
    return index.notes.get(note_id) or index.archived.get(note_id)


def entries(brain, st, chain, partitions, *, since=None, until=None, project=None,
            area=None) -> list[dict]:
    """Every movement in the window the caller may see, newest first."""
    index = st.index
    focus = None
    if project:
        from .relations import _project
        focus = _project(index, str(project))
    out = []
    for record in reversed(brain.vault.decisions()):
        at = str(record.get("at") or "")
        if since and at < str(since):
            continue
        if until and at > str(until):
            continue
        action = str(record.get("action") or "")
        moved = []
        kind = KINDS.get(action)
        if action == "marked" and record.get("state") == "disputed":
            kind = "disputed"
        target = record.get("note") or record.get("pointer")
        if kind and target:
            moved.append((kind, str(target)))
        if action in ("approved", "auto-applied"):
            moved += [("superseded", str(old)) for old in record.get("superseded") or []]
        for what, note_id in moved:
            note = _entry(index, note_id)
            if note is None or not Scopes.admits(note.scope, note.partition, chain, partitions):
                continue
            if area and not note.route_key.startswith(str(area).strip("/")):
                continue
            if focus is not None and note.id != focus.id and str(
                    note.meta.get("project") or "") not in {focus.id, focus.title, focus.slug}:
                continue
            out.append({"what": what, "id": note.id, "title": note.title, "recorded": at,
                        "true_from": note.as_of or note.added or "", "by":
                        record.get("by") or record.get("proposer") or "",
                        "area": note.route_key})
    return out


def _day(stamp: str) -> str:
    try:
        moment = dt.date.fromisoformat(str(stamp)[:10])
    except ValueError:
        return str(stamp)[:10]
    return f"{moment:%b} {moment.day}"


def counts(rows: list[dict]) -> str:
    tally: dict[str, int] = {}
    for row in rows:
        tally[row["what"]] = tally.get(row["what"], 0) + 1
    return ", ".join(f"{tally[k]} {k}" for k in ORDER if tally.get(k))


def changed_line(brain, st, chain, partitions, since: str) -> str:
    """The line a new conversation's first packet carries, or "" when nothing moved."""
    found = since_line(brain, st, chain, partitions, since)
    if not found:
        return ""
    return (f"Changed since your last conversation ({_day(since)}): "
            f"{found.split(': ', 1)[1]} Details: "
            f'activity(action: "timeline", since: "{since}").')


def since_line(brain, st, chain, partitions, since: str) -> str:
    """"Since Oct 21: 6 kept, 2 superseded, 1 waiting", or "" when nothing moved."""
    rows = entries(brain, st, chain, partitions, since=since)
    waiting = len(st.snapshot.proposals) if hasattr(st, "snapshot") else 0
    parts = [counts(rows)] if rows else []
    if waiting:
        parts.append(f"{waiting} waiting")
    return f"Since {_day(since)}: {', '.join(parts)}." if parts else ""
