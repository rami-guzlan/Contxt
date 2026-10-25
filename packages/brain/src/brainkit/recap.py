"""What happened in the brain since a moment: the recap a person reads when they come back.

It reads the decision journal (what went in on its own, and what people decided), the waiting
proposals (what came in and waits), the projects' journals (what moved) and the session ledger
(what the brain could not answer). It writes nothing.

SOURCES. Everything that came in is counted by where it came from, as a person would say it:
`chat` (an AI conversation), `files` (a document or asset filed), `you` (the owner, in the
app or the CLI), `ai_work` (work a model did through the workspace), `moved_in` (what an AI
app already knew, brought in) and `other`.
"""
from __future__ import annotations

from . import checkpoints, inventory

SOURCES = ("chat", "files", "you", "ai_work", "moved_in", "other")
ORIGIN_SOURCES = {"conversation": "chat", "file": "files", "doc": "files", "meeting": "files",
                  "output": "files", "you": "you", "workspace": "you", "work": "ai_work",
                  "import": "moved_in"}
DECIDED = ("approved", "rejected", "archived", "edited", "restored", "unarchived", "updated",
           "verified", "marked")
LIMIT = 100


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _origin_source(origin: str, source: str = "") -> str:
    kind = str(origin or "").partition(":")[0].strip().lower()
    if kind in ORIGIN_SOURCES:
        return ORIGIN_SOURCES[kind]
    low = str(source or "").lower()
    if low.startswith("workspace"):
        return "ai_work" if "model:" in low else "you"
    return "other"


def record_source(record: dict, note) -> str:
    """Where a journal record's change came from."""
    if str(record.get("kind") or "") == "file.add":
        return "files"
    if str(record.get("session") or "").strip():
        return "chat"
    if note is not None:
        found = inventory.origin_of(note, record)["kind"]
        if found in ORIGIN_SOURCES:
            return ORIGIN_SOURCES[found]
    return "other"


def proposal_source(proposal) -> str:
    """Where a waiting proposal came from."""
    if proposal.kind == "file.add":
        return "files"
    if str(proposal.meta.get("session") or "").strip():
        return "chat"
    target = proposal.target or {}
    return _origin_source(str(target.get("origin") or ""), str(target.get("source") or ""))


def _undo_points(brain) -> dict[str, str]:
    """{proposal id: the undo point that can still take its change back}."""
    out: dict[str, str] = {}
    for point in checkpoints.list_checkpoints(brain, 200):
        if point.get("undone_by") or point.get("kind") != "decisions":
            continue
        for decision in point.get("decisions") or []:
            if decision.get("proposal"):
                out.setdefault(str(decision["proposal"]), str(point["id"]))
    return out


def since(brain, moment: str):
    """The recap since an ISO moment (see the module's docstring)."""
    st = brain.state()
    moment = str(moment or "")
    index = st.index
    records = [r for r in brain.vault.decisions() if str(r.get("at") or "") >= moment]
    points = _undo_points(brain)
    went_in, decided = [], {}
    came: dict[str, int] = dict.fromkeys(SOURCES, 0)
    for record in records:
        action = str(record.get("action") or "")
        kind = str(record.get("kind") or "")
        note_id = str(record.get("pointer") or record.get("note") or "")
        note = index.note(note_id, include_archived=True) if note_id else None
        if action == "auto-applied":
            source = record_source(record, note)
            came[source] += 1
            target = record.get("target") if isinstance(record.get("target"), dict) else {}
            title = (index.file_title(str(record.get("path"))) if kind == "file.add"
                     and record.get("path") in index.cards else None) or (
                note.title if note is not None else note_id) or str(
                target.get("title") or record.get("outcome") or kind)  # a value, progress, task
            went_in.append({"at": record.get("at"), "kind": kind, "id": note_id,
                            "title": title, "source": source,
                            "capture": str(record.get("capture") or ""),
                            "path": record.get("path") if kind == "file.add" else None,
                            "live": bool(note is not None and note.live),
                            "checkpoint": points.get(str(record.get("proposal") or "")),
                            # Auto: the governing AI kept it, and why (the auto default)
                            "by_governor": record.get("applied_by") == "governor",
                            "reason": str(record.get("reason") or "")})
        elif action in DECIDED:
            decided[action] = decided.get(action, 0) + 1
            if action == "approved":
                came[record_source(record, note)] += 1
    waiting = 0
    for proposal in st.snapshot.proposals.values():
        if str(proposal.created or "") >= moment:
            waiting += 1
            came[proposal_source(proposal)] += 1
    went_in.sort(key=lambda row: str(row["at"] or ""), reverse=True)
    projects = []
    for focus in index.focuses.values():
        moved = [u for u in focus.updates if str(u.at or "") >= moment]
        if moved:
            last = max(moved, key=lambda u: str(u.at or ""))
            projects.append({"id": focus.id, "title": focus.title, "updates": len(moved),
                             "last": {"at": last.at, "summary": last.summary}})
    projects.sort(key=lambda p: str(p["last"]["at"] or ""), reverse=True)
    try:
        gaps = len(brain.ledger.gaps(moment)) if moment else 0
    except Exception:  # an unreadable ledger costs the count, not the recap
        gaps = 0
    total = sum(came.values())
    return _result(
        f"Since {moment[:10] or 'the start'}: {len(went_in)} went in on their own, "
        f"{sum(decided.values())} decided, {waiting} came in and wait.",
        {"since": moment, "went_in": went_in[:LIMIT], "went_in_total": len(went_in),
         "decided": decided, "came_in": {"total": total, "by_source": came,
                                         "waiting": waiting},
         "projects": projects, "gaps": gaps})
