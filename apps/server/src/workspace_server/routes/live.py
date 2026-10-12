"""Workspace's live context and Activity's tasks and handoffs over REST (UX plan 4.3, goals plan
6.9): State sheets with their rows, history and the AI values that wait; and tasks, moved only
through `hand_off`, the same function the tool uses."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..deps import WS, Who
from ..schemas import HandOffIn, LiveActIn

router = APIRouter(prefix="/api/work")


@router.get("/live")
def live(who: Who, ws: WS) -> dict[str, Any]:
    """The sheets, the templates, and the AI values waiting for you."""
    return ws.live.overview(who)


@router.get("/live/{sheet_id}")
def sheet(sheet_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return ws.live.sheet(who, sheet_id)


@router.get("/live/{sheet_id}/history")
def history(
    sheet_id: str, who: Who, ws: WS, row: str, column: str | None = None
) -> list[dict[str, Any]]:
    """A row's cell log, newest first (one column's, with `column`)."""
    return ws.live.history(who, sheet_id, row, column)


@router.post("/live/act")
def act(body: LiveActIn, who: Who, ws: WS) -> dict[str, Any]:
    """create_sheet, add_column, add_row, write, touch, decide, remove_row."""
    return ws.live.act(who, body.action, body.fields)


@router.get("/handoffs")
def now(
    who: Who,
    ws: WS,
    goal: str = "",
    project: str = "",
    owner: str = "",
    tool: str = "",
) -> dict[str, Any]:
    """The tasks by lane: waiting for you, handed off, working, blocked, open; done this
    week."""
    return ws.handoffs.now(who, goal=goal, project=project, owner=owner, tool=tool)


@router.get("/handoffs/timeline")
def timeline(who: Who, ws: WS, days: int = 7) -> dict[str, Any]:
    return ws.handoffs.timeline(who, days=days)


@router.get("/handoffs/{task_id}")
def task(task_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return ws.handoffs.task(who, task_id)


@router.post("/handoffs")
def hand_off(body: HandOffIn, who: Who, ws: WS) -> dict[str, Any]:
    """Open, save, pass on, claim or finish a task, as you."""
    return ws.handoffs.hand_off(who, body.model_dump(exclude_none=True))


@router.post("/handoffs/{task_id}/take-back")
def take_back(task_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return ws.handoffs.take_back(who, task_id)
