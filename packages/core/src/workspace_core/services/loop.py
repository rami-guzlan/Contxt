"""The updating loop in the app (brain-logic plan 9): what it asks of the owner, as Catch up's
cards, and what the owner does with each.

- "Still true?" after a correction: the note most likely behind it, kept, fixed or set aside;
- a rule bent three times in 90 days: change the rule or stop the exceptions;
- approval health: when approvals take seconds and nearly always pass;
- single-source notes that planning leaned on: corroborate them;
- the quarterly alignment review, offered;
- lessons the knowledge agent learned from the owner's decisions, kept as notes;
- the agent's hand-ups, for a larger model or the owner.

"That's wrong" on a request records a correction; nothing changes a note on its own.
"""

from __future__ import annotations

from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.errors import NotFound, ValidationFailed
from workspace_core.ports import BrainPort

from .brain import Brain
from .runtime import Runtime

ANSWERS = ("still_true", "fixed", "dismissed")


def _quarter(stamp: str) -> str:
    year, month = stamp[:4], int(stamp[5:7] or 1)
    return f"{year}-Q{(month - 1) // 3 + 1}"


def cards(port: BrainPort, now: str, hidden: set[str]) -> list[dict[str, Any]]:
    """The loop's cards for Catch up, each with a `key` it can be set aside by."""
    status = port.loop_status()
    out: list[dict[str, Any]] = []
    for c in status.get("corrections") or []:
        out.append(
            {
                "key": f"correction:{c['id']}",
                "type": "still_true",
                "correction": c["id"],
                "note": c["note"],
                "title": c["title"],
                "text": c["text"],
                "salience": bool(c.get("salience")),
                "ask": f'You corrected an AI ("{c["text"][:160]}"). Is "{c["title"]}" still true?',
            }
        )
    for b in status.get("bent_rules") or []:
        out.append(
            {
                "key": f"bent:{b['rule']}:{b['count']}",
                "type": "bent_rule",
                "note": b["rule"],
                "title": b["title"],
                "count": b["count"],
                "ask": f'You approved {b["count"]} exceptions to "{b["title"]}" in 90 days. '
                "Change the rule, or stop making exceptions?",
            }
        )
    health = status.get("approval_health") or {}
    if health.get("advice"):
        out.append(
            {
                "key": f"approvals:{now[:7]}",
                "type": "approval_health",
                "median_seconds": health.get("median_seconds"),
                "rate": health.get("rate"),
                "decided": health.get("decided"),
                "ask": health["advice"],
            }
        )
    for s in status.get("single_source") or []:
        out.append(
            {
                "key": f"single:{s['id']}",
                "type": "corroborate",
                "note": s["id"],
                "title": s["title"],
                "uses": s["uses"],
                "source": s.get("source") or "",
                "ask": f"Planning and decisions leaned on this {s['uses']} times, and it rests "
                "on one source. Find a second one?",
            }
        )
    if status.get("review_due"):
        out.append(
            {
                "key": f"review:{_quarter(now)}",
                "type": "quarterly_review",
                "ask": (
                    "It has been three months since your goals, rules and projects were "
                    "checked against each other."
                    if status.get("last_review")
                    else "Your goals, rules and projects have not been checked against each "
                    "other yet."
                )
                + " Run the alignment check?",
            }
        )
    for lesson in status.get("lessons") or []:
        out.append(
            {
                "key": f"lesson:{lesson['action']}:{lesson['area']}:{lesson['decision']}",
                "type": "lesson",
                "action": lesson["action"],
                "area": lesson["area"],
                "cases": lesson["cases"],
                "text": lesson["text"],
                "ask": "Keep this as a note, so the agent stops asking?",
            }
        )
    for h in status.get("hand_ups") or []:
        out.append(
            {
                "key": f"handup:{h['id']}",
                "type": "hand_up",
                "action": h["action"],
                "at": h["at"],
                "why": h.get("why") or "",
                "ask": "The knowledge agent handed this job up. Run it with a larger model or "
                "Claude Code, or look at the candidates yourself.",
            }
        )
    return [c for c in out if c["key"] not in hidden]


class Loop:
    def __init__(self, rt: Runtime, brain: Brain) -> None:
        self.rt = rt
        self.brain = brain

    def status(self, who: Principal) -> dict[str, Any]:
        who.require("brain.read")
        return self.rt.brain.loop_status()

    def correct(
        self, who: Principal, text: str, *, session_id: str = "", packet_id: str = ""
    ) -> dict[str, Any]:
        """ "That's wrong": the owner corrects what an AI made from a request. The notes in
        that brief become suspects; the likeliest gets a "Still true?" card."""
        who.require("brain.govern")
        text = " ".join(str(text or "").split())
        if not text:
            raise ValidationFailed("Say what was wrong.", field="text")
        if not session_id and not packet_id:
            raise ValidationFailed("Name the request it was about.", field="packet_id")
        return self.rt.brain.correction(text[:1000], session_id=session_id, packet_id=packet_id)

    def answer(self, who: Principal, correction_id: int, status: str) -> dict[str, Any]:
        """A "Still true?" card answered: still true (the note is confirmed today), fixed (the
        owner changed the note), or set aside."""
        who.require("brain.govern")
        if status not in ANSWERS:
            raise ValidationFailed(f"Answer one of {', '.join(ANSWERS)}.", field="status")
        found = next(
            (
                c
                for c in self.rt.brain.loop_status().get("corrections") or []
                if int(c["id"]) == int(correction_id)
            ),
            None,
        )
        if found is None:
            raise NotFound("That correction is closed or unknown.", id=correction_id)
        if status == "still_true":
            self.brain.verify(who, found["note"])
        self.rt.brain.close_correction(int(correction_id), status)
        return {"id": correction_id, "status": status}

    def keep_lesson(self, who: Principal, key: str) -> dict[str, Any]:
        """A lesson kept as a governed note: it waits in Catch up like any suggestion."""
        who.require("brain.propose")
        lesson = next(
            (
                lesson
                for lesson in self.rt.brain.loop_status().get("lessons") or []
                if f"lesson:{lesson['action']}:{lesson['area']}:{lesson['decision']}" == key
            ),
            None,
        )
        if lesson is None:
            raise NotFound("No such lesson.", key=key)
        made = self.brain.propose(
            who,
            title=f"How I decide {lesson['action']} suggestions in {lesson['area']}",
            statement=lesson["text"],
            kind="rule",
            evidence=f"{lesson['cases']} decisions in Catch up",
            origin=f"agent:lesson:{lesson['action']}",
        )
        return {"proposal_id": made.proposal_id, "status": made.status}

    def check(self, who: Principal, text: str) -> list[dict[str, Any]]:
        """An output's text against the must-holds in play."""
        who.require("brain.read")
        return self.rt.brain.check_output(str(text or ""))

    def blast(self, who: Principal, proposal_id: str) -> dict[str, Any]:
        """What a waiting proposal would change in the last briefs that used its note."""
        who.require("brain.read")
        return self.rt.brain.blast_radius(proposal_id)

    def runs(self, who: Principal, limit: int = 20) -> list[dict[str, Any]]:
        """The knowledge agent's runs, newest first, each with its steps."""
        who.require("brain.read")
        return self.rt.brain.agent_runs(max(1, min(int(limit), 100)))
