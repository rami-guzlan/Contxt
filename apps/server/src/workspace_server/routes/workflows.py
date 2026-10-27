"""Workflows over REST: steps run as one thing, on a schedule, by a button or from any AI.
List and build them (from a template, or from nothing), run one now, follow its runs, decide at
a check, stop a run, and take a workflow away as a file or bring one in. The server's worker
starts what is due and moves each run along (flows.py)."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Request, Response

from workspace_core.errors import ValidationFailed
from workspace_core.services.workflows import Workflow, WorkflowRun

from ..deps import WS, Who
from ..flows import connectors
from ..schemas import WorkflowDecideIn, WorkflowIn, WorkflowRunIn
from .brain import disposition

router = APIRouter(prefix="/api/workflows")

FILE_FIELDS = ("name", "description", "schedule", "ai", "steps", "runner", "output")


@router.get("")
def workflows(who: Who, ws: WS, archived: bool = False) -> list[Workflow]:
    """Every workflow, with its last run and whether one is going now."""
    return ws.workflows.list(who, archived=archived)


@router.get("/templates")
def templates(who: Who, ws: WS) -> list[dict[str, Any]]:
    """Workflows to start from."""
    return ws.workflows.templates()


@router.get("/library")
def node_library(who: Who, ws: WS) -> dict[str, Any]:
    """The canvas's node library: kinds of step with what each takes and gives."""
    who.require("tasks.read")
    return ws.workflows.library()


@router.get("/connectors")
def connector_list(request: Request, who: Who) -> dict[str, Any]:
    """The MCP servers Claude Code on this computer connects to (`claude mcp list`), to name
    a connector step's tools from. Contxt never reads their credentials."""
    who.require("workspace.admin")
    return connectors(request.app.state.runtime.runners)


@router.get("/waiting")
def waiting(who: Who, ws: WS) -> list[WorkflowRun]:
    """Runs waiting for the owner: a check, or a step a person must unblock."""
    return ws.workflows.waiting(who)


@router.get("/runs")
def recent_runs(who: Who, ws: WS, limit: int = 20) -> list[WorkflowRun]:
    return ws.workflows.runs(who, limit=limit)


@router.get("/runs/{run_id}")
def one_run(run_id: str, who: Who, ws: WS) -> WorkflowRun:
    return ws.workflows.run_of(who, run_id)


@router.get("/runs/{run_id}/steps/{index}")
def step_result(run_id: str, index: int, who: Who, ws: WS) -> dict[str, Any]:
    """What one step made, in full (to read, or to edit at a check)."""
    return ws.workflows.step_result(who, run_id, index)


@router.post("/runs/{run_id}/decide")
def decide(run_id: str, body: WorkflowDecideIn, who: Who, ws: WS) -> WorkflowRun:
    """At a check: go on (with what the step before made, or your edit of it), or stop."""
    return ws.workflows.decide(who, run_id, go=body.go, edit=body.edit, note=body.note)


@router.post("/runs/{run_id}/retry")
def retry(run_id: str, who: Who, ws: WS) -> WorkflowRun:
    """Retry the step that failed, on the same CLI; the run resumes there."""
    return ws.workflows.retry(who, run_id)


@router.post("/runs/{run_id}/stop")
def stop(run_id: str, who: Who, ws: WS) -> WorkflowRun:
    return ws.workflows.stop(who, run_id)


@router.post("", status_code=201)
def create(body: WorkflowIn, who: Who, ws: WS) -> Workflow:
    return ws.workflows.save(who, **body.fields())


@router.post("/import", status_code=201)
def bring_in(body: dict[str, Any], who: Who, ws: WS) -> Workflow:
    """A workflow from a file another Contxt made: a new workflow, switched off until you
    turn it on."""
    if body.get("contxt") != "workflow":
        raise ValidationFailed("That is not a workflow file.", field="contxt")
    fields = {key: body.get(key) for key in FILE_FIELDS if key in body}
    form = WorkflowIn.model_validate({**fields, "enabled": False})
    return ws.workflows.save(who, **form.fields())


@router.get("/{workflow_id}")
def workflow(workflow_id: str, who: Who, ws: WS) -> Workflow:
    return ws.workflows.get(who, workflow_id)


@router.put("/{workflow_id}")
def change(workflow_id: str, body: WorkflowIn, who: Who, ws: WS) -> Workflow:
    """A change is a new revision; its next run is worked out again."""
    return ws.workflows.save(
        who, workflow_id=workflow_id, expected_version=body.expected_version, **body.fields()
    )


@router.delete("/{workflow_id}")
def archive(workflow_id: str, who: Who, ws: WS) -> Workflow:
    return ws.workflows.archive(who, workflow_id)


@router.post("/{workflow_id}/restore")
def restore(workflow_id: str, who: Who, ws: WS) -> Workflow:
    """Bring it back, switched off."""
    return ws.workflows.archive(who, workflow_id, archived=False)


@router.post("/{workflow_id}/run", status_code=201)
def run(workflow_id: str, body: WorkflowRunIn, who: Who, ws: WS) -> WorkflowRun:
    """Run it now: its first step starts at once."""
    return ws.workflows.run(who, workflow_id, request=body.request)


@router.get("/{workflow_id}/runs")
def runs(workflow_id: str, who: Who, ws: WS, limit: int = 20) -> list[WorkflowRun]:
    return ws.workflows.runs(who, workflow_id=workflow_id, limit=limit)


@router.get("/{workflow_id}/export")
def export(workflow_id: str, who: Who, ws: WS) -> Response:
    """The workflow as a file (JSON) another Contxt can bring in."""
    found = ws.workflows.get(who, workflow_id)
    data = {"contxt": "workflow", "version": 1, **{k: getattr(found, k) for k in FILE_FIELDS}}
    stem = re.sub(r"[^A-Za-z0-9 ._-]+", "", found.name).strip() or "workflow"
    return Response(
        json.dumps(data, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={"Content-Disposition": disposition(f"{stem}.json")},
    )
