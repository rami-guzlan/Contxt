"""The task bus over REST (parity with the MCP tools), and the AI work the app started."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header

from workspace_core.domain.records import Run, Task

from ..deps import WS, Who
from ..schemas import ClaimIn, CompleteIn, ReasonIn, RunEventIn

router = APIRouter(prefix="/api")
Key = Header(default=None, alias="Idempotency-Key")


# ---------------------------------------------------------------------- AI work


@router.get("/tasks/{task_id}")
def get_task(task_id: str, who: Who, ws: WS) -> Task:
    """One piece of AI work the app started ("find what to remember", a reconcile)."""
    return ws.tasks.get(who, task_id)


@router.get("/tasks/{task_id}/runs")
def task_runs(task_id: str, who: Who, ws: WS) -> list[Run]:
    return ws.tasks.runs(who, task_id)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, body: ReasonIn, who: Who, ws: WS) -> Task:
    """Stop work that has not finished: a waiting request, or one a model holds."""
    return ws.tasks.cancel(who, task_id, reason=body.reason)


# ---------------------------------------------------------------------- bus and runs


@router.get("/bus/due")
def due(who: Who, ws: WS, limit: int = 20) -> dict[str, Any]:
    work = ws.bus.due(who, limit=limit)
    return {"tasks": work.tasks, "active_runs": work.active_runs}


@router.post("/bus/claim", status_code=201)
def claim(body: ClaimIn, who: Who, ws: WS, idempotency_key: str | None = Key) -> dict[str, Any]:
    result = ws.bus.claim(
        who, body.task_id, lease_seconds=body.lease_seconds, idempotency_key=idempotency_key
    )
    return {"run": result.run, "packet": result.packet}


@router.get("/runs/{run_id}")
def get_run(run_id: str, who: Who, ws: WS) -> Run:
    return ws.bus.run(who, run_id)


@router.post("/runs/{run_id}/events", status_code=201)
def run_event(
    run_id: str, body: RunEventIn, who: Who, ws: WS, idempotency_key: str | None = Key
) -> dict[str, Any]:
    event = ws.bus.append(
        who,
        run_id,
        type=body.type,
        message=body.message,
        data=body.data,
        idempotency_key=idempotency_key,
    )
    return event.to_dict()


@router.post("/runs/{run_id}/complete")
def complete(
    run_id: str, body: CompleteIn, who: Who, ws: WS, idempotency_key: str | None = Key
) -> Run:
    return ws.bus.complete(
        who, run_id, summary=body.summary, outcome=body.outcome, idempotency_key=idempotency_key
    )
