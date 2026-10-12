"""Goals and Projects over REST (goals plan G1): the ladder, one goal's page, check-ins, the
strategy board, suggested next steps, the goal coach (a background job on the model the owner
chose), the knowledge agent's starter goals, goal checks and Home's strip.

`/api/brain/goals` keeps answering the purpose interview, so the ladder lives here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..deps import WS, Who
from ..knowledge_agent import AgentWork
from ..schemas import (
    GoalBoardIn,
    GoalChangeIn,
    GoalCheckInIn,
    GoalCoachIn,
    GoalDecisionIn,
    GoalIn,
    GoalLinkIn,
    GoalSettingsIn,
    GoalSuggestionIn,
)

router = APIRouter(prefix="/api/goals")


def work(request: Request) -> AgentWork:
    found: AgentWork = request.app.state.runtime.agent
    return found


@router.get("")
def ladder(who: Who, ws: WS, signals: bool = False) -> dict[str, Any]:
    """The purpose, your goals and agent goals; with `signals`, the signal library and each
    signal's value now (the measure picker)."""
    return ws.goals.ladder(who, with_signals=signals)


@router.post("", status_code=201)
def set_goal(body: GoalIn, who: Who, ws: WS) -> dict[str, Any]:
    """Set a goal from the coach's draft or the form."""
    return ws.goals.set(who, body.model_dump(exclude_none=True))


@router.get("/home")
def home(who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.home(who)


@router.get("/rules")
def rules(who: Who, ws: WS) -> dict[str, Any]:
    """What every AI is told: the startup context, the must-holds, how and never."""
    return ws.goals.rules(who)


@router.get("/settings")
def settings(who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.settings(who)


@router.put("/settings")
def configure(body: GoalSettingsIn, who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.configure(who, weekly_review=body.weekly_review)


@router.post("/starters")
def starters(who: Who, ws: WS) -> dict[str, Any]:
    """Turn on the knowledge agent's four goals."""
    return ws.goals.starters(who)


@router.post("/checks")
def checks(who: Who, ws: WS) -> dict[str, Any]:
    """Run every computed check now, whatever its cadence."""
    return {"checks": ws.goals.run_checks(who, force=True), "ladder": ws.goals.ladder(who)}


@router.post("/coach", status_code=201)
def coach(body: GoalCoachIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """One turn of the goal coach, in the background; poll /api/brain/agent/jobs/{id}."""
    messages = [m.model_dump() for m in body.messages]
    return (
        work(request)
        .start_work(
            who,
            "goal-coach",
            lambda: ws.goals.coach_prompt(who, messages),
            _read_coach,
            model=body.model,
            message=messages[-1]["text"] if messages else "",
        )
        .to_dict()
    )


def _read_coach(answer: str) -> dict[str, Any]:
    from workspace_core.services.goals import read_coach

    return read_coach(answer)


@router.get("/{goal_id}")
def goal(goal_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.get(who, goal_id)


@router.patch("/{goal_id}")
def change(goal_id: str, body: GoalChangeIn, who: Who, ws: WS) -> dict[str, Any]:
    changes = body.changes()
    reason = str(changes.pop("reason", "") or "")
    return ws.goals.change(who, goal_id, changes, reason)


@router.post("/{goal_id}/check-in")
def check_in(goal_id: str, body: GoalCheckInIn, who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.check_in(who, goal_id, call=body.call, value=body.value, line=body.line)


@router.put("/{goal_id}/board")
def board(goal_id: str, body: GoalBoardIn, who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.save_board(who, goal_id, body.layout, expected_version=body.expected_version)


@router.post("/{goal_id}/suggestions/{suggestion_id}")
def suggestion(
    goal_id: str, suggestion_id: str, body: GoalSuggestionIn, who: Who, ws: WS
) -> dict[str, Any]:
    """Make a suggested step part of the plan, or say no (remembered)."""
    return ws.goals.answer_suggestion(who, goal_id, suggestion_id, accept=body.accept)


@router.post("/{goal_id}/decisions")
def decide(goal_id: str, body: GoalDecisionIn, who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.decide(who, goal_id, body.text)


@router.post("/{goal_id}/projects")
def link(goal_id: str, body: GoalLinkIn, who: Who, ws: WS) -> dict[str, Any]:
    return ws.goals.link(who, goal_id, body.project, linked=body.linked)
