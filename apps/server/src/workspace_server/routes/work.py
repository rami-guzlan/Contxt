"""Work as one place: what in it needs a look, for its overview. Each part has its own routes
(compose, workspace, skills, agents, workflows, library, outputs)."""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Request

from ..deps import WS, Who
from ..schemas import WorkAskIn
from ..work_with_ai import WorkWithAI

router = APIRouter(prefix="/api/work")

KEEP = 60.0  # seconds a look is kept: reading every skill's history is not free
_kept: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


@router.get("/attention")
def attention(who: Who, ws: WS, fresh: bool = False) -> dict[str, Any]:
    """Skills whose loads changed after their last edit, and agents whose pointers broke."""
    key = f"{ws.rt.workspace_id}:{who.actor_id}"
    with _lock:
        kept = _kept.get(key)
    if kept and not fresh and time.monotonic() - kept[0] < KEEP:
        return kept[1]
    found = ws.work_attention(who)
    with _lock:
        _kept[key] = (time.monotonic(), found)
    return found


def _work(request: Request) -> WorkWithAI:
    runtime = request.app.state.runtime
    return WorkWithAI(runtime.ws, runtime.runners)


@router.post("/projects/{project_id}/ask", status_code=201)
def ask(project_id: str, body: WorkAskIn, request: Request, who: Who) -> dict[str, Any]:
    """Work with AI (Release 1 plan, section 11): one prompt becomes one job in this
    project's Tasks, run now; what it makes lands in Outputs as a draft."""
    return _work(request).ask(
        who,
        project_id,
        body.prompt,
        skill=body.skill,
        agent=body.agent,
        runner=body.runner,
        model=body.model,
    )


@router.get("/projects/{project_id}/timeline")
def timeline(project_id: str, request: Request, who: Who) -> list[dict[str, Any]]:
    """Each Work with AI job in the project, newest first: status, model, outputs,
    proposals, tokens and cost, and why it failed."""
    return _work(request).timeline(who, project_id)
