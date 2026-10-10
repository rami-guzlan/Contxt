"""The updating loop over REST (brain-logic plan 9): what it asks of the owner, "That's wrong"
on a request, "Still true?" answered, lessons kept, an output checked against the must-holds,
a proposal's blast radius, and the knowledge agent's runs with their steps."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..deps import WS, Who
from ..schemas import CheckOutputIn, CorrectionAnswerIn, CorrectionIn, LessonIn

router = APIRouter(prefix="/api/loop")


@router.get("")
def status(who: Who, ws: WS) -> dict[str, Any]:
    return ws.loop.status(who)


@router.post("/corrections")
def correct(body: CorrectionIn, who: Who, ws: WS) -> dict[str, Any]:
    """ "That's wrong" on a request: the brief's notes become suspects."""
    return ws.loop.correct(
        who, body.text, session_id=body.session_id or "", packet_id=body.packet_id or ""
    )


@router.post("/corrections/{correction_id}")
def answer(correction_id: int, body: CorrectionAnswerIn, who: Who, ws: WS) -> dict[str, Any]:
    return ws.loop.answer(who, correction_id, body.status)


@router.post("/lessons")
def keep_lesson(body: LessonIn, who: Who, ws: WS) -> dict[str, Any]:
    return ws.loop.keep_lesson(who, body.key)


@router.post("/check")
def check(body: CheckOutputIn, who: Who, ws: WS) -> dict[str, Any]:
    return {"violations": ws.loop.check(who, body.text)}


@router.get("/blast/{proposal_id}")
def blast(proposal_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return ws.loop.blast(who, proposal_id)


@router.get("/runs")
def runs(who: Who, ws: WS, limit: int = 20) -> list[dict[str, Any]]:
    return ws.loop.runs(who, limit)
