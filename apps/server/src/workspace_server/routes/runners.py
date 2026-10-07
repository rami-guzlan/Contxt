"""Run tasks now with the AI command-line tools on this machine, or from a copied prompt."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request

from workspace_core.domain.policy import Principal
from workspace_core.errors import NotFound
from workspace_core.workspace import Workspace

from ..deps import WS, Who
from ..runners import LocalRun, Runners
from ..schemas import OnboardingIn, RunIn

router = APIRouter()


def runners(request: Request) -> Runners:
    found: Runners = request.app.state.runners
    return found


def brief(run: LocalRun) -> dict[str, Any]:
    data = run.to_dict()
    data.pop("events")
    return data


def place(ws: Workspace, who: Principal, task_id: str) -> str | None:
    """The page a run's work belongs to: the skill it ran, the capture it summarized, or
    Review, where what it proposed waits."""
    try:
        task = ws.tasks.get(who, task_id)
    except NotFound:
        return None
    about = task.provenance or {}
    if task.template in ("skill", "skill-draft"):
        name = (about.get("skill") or {}).get("name")
        return f"/skills/{quote(str(name))}" if name else "/review"
    if task.template == "digest":
        item = (about.get("digest") or {}).get("item")
        return f"/capture/{quote(str(item))}" if item else None
    if task.template in ("distill", "reconcile"):
        return "/review"
    return None


@router.get("/api/runners")
def statuses(request: Request, who: Who, refresh: bool = False) -> list[dict[str, Any]]:
    """Each CLI: installed, signed in, and the model its runs act as."""
    return [asdict(s) for s in runners(request).statuses(who, refresh=refresh)]


@router.get("/api/onboarding")
def onboarding(request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """First-time setup: each step and whether it is done, worked out from the workspace
    (a CLI on this computer that can run tasks counts as a connected model)."""
    local = who.can("workspace.admin") and any(
        s.one_click and s.installed and s.signed_in is not False and s.actor_id
        for s in runners(request).statuses(who)
    )
    return ws.onboarding.status(who, local_model=local)


@router.post("/api/onboarding")
def mark_onboarding(body: OnboardingIn, who: Who, ws: WS) -> dict[str, Any]:
    """Keep a moment of the setup: finished, put aside, the tour taken, a step done as is."""
    return ws.onboarding.mark(who, **body.model_dump())


@router.post("/api/runners/{runner_id}/sign-in")
def sign_in(runner_id: str, request: Request, who: Who) -> dict[str, Any]:
    """Open a terminal where the person signs in to the CLI (the CLI keeps the login)."""
    return runners(request).sign_in(who, runner_id)


@router.post("/api/runners/{runner_id}/runs", status_code=201)
def start(runner_id: str, body: RunIn, request: Request, who: Who) -> dict[str, Any]:
    return runners(request).start(who, runner_id, body.task_id).to_dict()


@router.get("/api/runners/runs")
def recent(request: Request, who: Who, ws: WS) -> list[dict[str, Any]]:
    """What runs here now and what finished lately, each with the page its work belongs to."""
    return [
        dict(brief(run), link=place(ws, who, run.task_id)) for run in runners(request).recent(who)
    ]


@router.get("/api/runners/runs/{run_id}")
def follow(run_id: str, request: Request, who: Who, after: int = 0) -> dict[str, Any]:
    """The run so far; `after` returns only the events past that sequence number."""
    return runners(request).get(who, run_id).to_dict(after=after)


@router.post("/api/runners/runs/{run_id}/cancel")
def cancel(run_id: str, request: Request, who: Who) -> dict[str, Any]:
    return runners(request).cancel(who, run_id).to_dict()


@router.get("/api/tasks/{task_id}/prompt")
def prompt(task_id: str, request: Request, who: Who, ws: WS) -> dict[str, str]:
    """The prompt that runs this one task in any connected client, for copying."""
    task = ws.tasks.get(who, task_id)
    return {"prompt": request.app.state.templates.run_prompt(ws.info().name, task.id)}
