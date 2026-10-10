"""The updating loop (brain-logic plan 9): how the Brain learns what it got wrong, and keeps
its own approvals honest. Code finds, a model judges where words are needed, the owner decides.

- CORRECTIONS. When the owner corrects an AI's output (the capture cue, or "that's wrong" in
  the app), the notes in the brief before it become suspects; the most likely one, by overlap
  with the correction, gets a "Still true?" card. A note that turns out wrong (the owner edits
  or retires it from that card) is offered a stronger load: salience from consequences.
- EXCEPTIONS. An approval that bends or overrides a rule (a proposal that contradicts or
  narrows it, approved anyway) is counted against the rule; at three in 90 days the owner is
  asked to change the rule or stop the exceptions (normalization of deviance, as a check).
- APPROVAL HEALTH. The median time to approve and the approval rate over 30 days; approvals
  that take seconds and nearly always pass suggest moving more types to "applies with undo".
- SINGLE SOURCE. Notes used in planning and decision briefs that rest on one source are
  flagged for corroboration.
- INDEPENDENT EVIDENCE. Outputs made from the same brief lineage count once as evidence,
  however many agents repeat them.
- QUARTERLY REVIEW. Goals, rules and must-holds still right? Offered when the alignment check
  has not run for 90 days.
"""
from __future__ import annotations

import datetime as dt
import statistics

from . import util

SUSPECTS = 3                 # notes a correction names, most likely first
EXCEPTION_WINDOW = 90        # days
EXCEPTION_LIMIT = 3          # at the third, the owner is asked
HEALTH_DAYS = 30
FAST_SECONDS = 10            # a median approval this fast, ...
HIGH_RATE = 0.95             # ... with this approval rate, suggests fewer, weightier decisions
DECISION_TYPES = ("decision", "planning")  # request types whose briefs a single source matters in
REVIEW_DAYS = 90


def _terms(text: str) -> set[str]:
    return set(util.content_terms(str(text or "")))


def _when(stamp: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------- corrections
def suspects(brain, correction: str, *, session_id: str = "", packet_id: str = "") -> list[dict]:
    """The notes the brief before a correction carried, most likely first, each with its score
    (overlap of the correction with the note's words)."""
    packet = brain.ledger.packet(packet_id) if packet_id else None
    if packet is None and session_id:
        packet = brain.ledger.last_packet(session_id)
        if packet is not None:
            packet = {"data": packet}
    data = (packet or {}).get("data") or {}
    st = brain.state()
    said = _terms(correction)
    out = []
    for note_id in data.get("note_ids") or []:
        note = st.index.note(note_id)
        if note is None or not said:
            continue
        words = _terms(f"{note.title} {note.body}")
        score = len(said & words) / max(1, len(said))
        out.append({"id": note.id, "title": note.title, "score": round(score, 3)})
    out.sort(key=lambda s: -s["score"])
    return out[:SUSPECTS]


def record_correction(brain, correction: str, *, session_id: str = "", packet_id: str = "",
                      by: str = "") -> dict:
    """Keep a correction and its top suspect: the "Still true?" card Catch up shows."""
    found = suspects(brain, correction, session_id=session_id, packet_id=packet_id)
    top = found[0] if found and found[0]["score"] > 0 else None
    brain.ledger.add_correction(util.excerpt(correction, 400), session_id=session_id,
                                packet_id=packet_id, suspect=top["id"] if top else "",
                                score=top["score"] if top else 0.0, by=by)
    return {"suspects": found, "card": top}


# ---------------------------------------------------------------------- exceptions
def note_exception(brain, rule_id: str, proposal_id: str, relation: str, *, by: str = "") -> int:
    """Count an approval that bent a rule; returns how many in the window."""
    brain.ledger.add_exception(rule_id, proposal_id, relation, by=by)
    return exceptions(brain, rule_id)


def exceptions(brain, rule_id: str, *, today: dt.date | None = None) -> int:
    since = ((today or util.today_date()) - dt.timedelta(days=EXCEPTION_WINDOW)).isoformat()
    return len([e for e in brain.ledger.exceptions(rule_id) if e["at"] >= since])


def bent_rules(brain, *, today: dt.date | None = None) -> list[dict]:
    """Rules bent three times or more in 90 days: ask to change the rule or stop."""
    since = ((today or util.today_date()) - dt.timedelta(days=EXCEPTION_WINDOW)).isoformat()
    st = brain.state()
    counts: dict[str, list[dict]] = {}
    for row in brain.ledger.exceptions():
        if row["at"] >= since:
            counts.setdefault(row["rule"], []).append(row)
    out = []
    for rule, rows in counts.items():
        note = st.index.note(rule)
        if note is not None and len(rows) >= EXCEPTION_LIMIT:
            out.append({"rule": rule, "title": note.title, "count": len(rows),
                        "proposals": [r["proposal"] for r in rows]})
    return out


# ---------------------------------------------------------------------- approval health
def approval_health(brain, *, today: dt.date | None = None) -> dict:
    """The median seconds from proposal to decision, and the approval rate, over 30 days."""
    since = ((today or util.today_date()) - dt.timedelta(days=HEALTH_DAYS)).isoformat()
    seconds, approved, decided = [], 0, 0
    for record in brain.vault.decisions():
        at = str(record.get("at") or "")
        if at < since or record.get("action") not in ("approved", "rejected"):
            continue
        decided += 1
        approved += record.get("action") == "approved"
        created = str(record.get("created") or record.get("proposal_created") or "")
        if created:
            start, end = _when(created), _when(at)
            if start and end:
                seconds.append(max(0.0, (end - start).total_seconds()))
    median = statistics.median(seconds) if seconds else None
    rate = approved / decided if decided else None
    advice = ""
    if median is not None and rate is not None and decided >= 10 and median <= FAST_SECONDS \
            and rate >= HIGH_RATE:
        advice = ("Approvals take seconds and nearly always pass: let more kinds apply with "
                  "undo, and keep your yes for the decisions that weigh.")
    return {"decided": decided, "approved": approved, "rate": rate, "median_seconds": median,
            "advice": advice}


# ---------------------------------------------------------------------- single source
def single_source(brain, *, days: int = 30, limit: int = 5) -> list[dict]:
    """Notes that planning and decision briefs leaned on, resting on one source."""
    st = brain.state()
    since = (util.today_date() - dt.timedelta(days=days)).isoformat()
    used: dict[str, int] = {}
    for row in brain.ledger.requests(limit=500):
        if str(row.get("at") or "") < since:
            continue
        data = row.get("data") or {}
        if data.get("request_type") not in DECISION_TYPES:
            continue
        for note_id in data.get("note_ids") or []:
            used[note_id] = used.get(note_id, 0) + 1
    out = []
    for note_id, count in sorted(used.items(), key=lambda kv: -kv[1]):
        note = st.index.note(note_id)
        if note is None or note.kind in ("identity", "goal", "focus"):
            continue
        sources = [s for s in str(note.meta.get("sources") or "").split(";") if s.strip()]
        if len(sources) <= 1 and not note.meta.get("corroborated"):
            out.append({"id": note.id, "title": note.title, "uses": count,
                        "source": str(note.meta.get("source") or note.meta.get("evidence")
                                      or "")[:200]})
    return out[:limit]


# ---------------------------------------------------------------------- independent evidence
def independent(brain, paths: list[str]) -> dict:
    """Outputs as evidence, counted by brief lineage: outputs from the same conversation's
    briefs (the same notes handed) count once."""
    from .activity import normal_path
    lineages: dict[str, list[str]] = {}
    for path in paths:
        found = brain.ledger.output(normal_path(path)) or {}
        session = str(found.get("session_id") or "")
        items = brain.ledger.session_items(session) if session else []
        key = util.short_hash("|".join(sorted(f"{k}:{i}" for k, i, *_rest in items
                                              if k == "note")), 10) if items else path
        lineages.setdefault(key, []).append(path)
    return {"given": len(paths), "independent": len(lineages),
            "lineages": list(lineages.values())}


# ---------------------------------------------------------------------- quarterly review
def review_due(last_run: str, *, today: dt.date | None = None) -> bool:
    found = util.parse_date(str(last_run or "")[:10])
    return found is None or ((today or util.today_date()) - found).days >= REVIEW_DAYS
