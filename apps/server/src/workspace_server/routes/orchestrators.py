"""A project's agent orchestrators (AGENTS.md 8b): list, save, run with a steer, the activity
timeline, Outputs grouped by run with the final pinned on top, the auto sheets, and the
owner's yes to a gate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..deps import Who
from ..orchestration import Orchestration
from ..schemas import GateDecisionIn, OrchestratorIn, OrchestratorRunIn

router = APIRouter(prefix="/api/projects/{project_id}/orchestrators")


def _orc(request: Request) -> Orchestration:
    found: Orchestration = request.app.state.orchestration
    return found


def _spec(body: OrchestratorIn) -> dict[str, Any]:
    spec = body.model_dump(exclude={"expected_version"})
    return spec


@router.get("")
def overview(project_id: str, request: Request, who: Who) -> dict[str, Any]:
    """The orchestrators with their latest runs, the agent tasks, and the CLIs and models."""
    return _orc(request).overview(who, project_id)


@router.post("", status_code=201)
def create(project_id: str, body: OrchestratorIn, request: Request, who: Who) -> dict[str, Any]:
    """Make an orchestrator. A new agent profile is saved to Agents too."""
    return _orc(request).save(who, project_id, _spec(body))


@router.get("/timeline")
def timeline(
    project_id: str, request: Request, who: Who, run_id: str | None = None
) -> list[dict[str, Any]]:
    """Every step of the project's runs, newest first."""
    orc = _orc(request)
    pid = orc.project_id(who, project_id)
    return orc.core.timeline(who, pid, run_id=run_id) if pid else []


@router.get("/outputs")
def outputs(
    project_id: str, request: Request, who: Who, orchestrator_id: str | None = None
) -> list[dict[str, Any]]:
    """The runs, newest first: each with its final output and the trail that led to it."""
    orc = _orc(request)
    pid = orc.project_id(who, project_id)
    return orc.core.runs(who, pid, orchestrator_id=orchestrator_id) if pid else []


@router.get("/sheets")
def sheets(project_id: str, request: Request, who: Who) -> list[dict[str, Any]]:
    """Each orchestrator's auto Context sheet."""
    orc = _orc(request)
    pid = orc.project_id(who, project_id)
    return orc.core.sheets(who, pid) if pid else []


@router.get("/runs/{run_id}")
def run_of(project_id: str, run_id: str, request: Request, who: Who) -> dict[str, Any]:
    found: dict[str, Any] = _orc(request).core.run_of(who, run_id)
    return found


@router.post("/runs/{run_id}/gates/{gate_id}")
def decide(
    project_id: str, run_id: str, gate_id: str, body: GateDecisionIn, request: Request, who: Who
) -> dict[str, Any]:
    """The owner's yes (or no) to what a run waits for."""
    return _orc(request).decide(
        who, run_id, gate_id, approve=body.decision == "approve", quote=body.quote
    )


@router.get("/{orchestrator_id}")
def get(project_id: str, orchestrator_id: str, request: Request, who: Who) -> dict[str, Any]:
    found: dict[str, Any] = _orc(request).core.get(who, orchestrator_id)
    return found


@router.put("/{orchestrator_id}")
def save(
    project_id: str, orchestrator_id: str, body: OrchestratorIn, request: Request, who: Who
) -> dict[str, Any]:
    return _orc(request).save(
        who,
        project_id,
        _spec(body),
        orchestrator_id=orchestrator_id,
        expected_version=body.expected_version,
    )


@router.post("/{orchestrator_id}/run", status_code=201)
def run(
    project_id: str, orchestrator_id: str, body: OrchestratorRunIn, request: Request, who: Who
) -> dict[str, Any]:
    """Run it now, with an optional steer: its CLI starts on this computer."""
    return _orc(request).run(who, project_id, orchestrator_id, steer=body.steer)
