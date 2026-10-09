"""Skills over REST: the procedures your AI follows, run from the app, improved, written new."""

from __future__ import annotations

import mimetypes
import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from workspace_core.domain.records import Task

from ..deps import WS, Who
from ..files import served
from ..schemas import SkillDraftIn, SkillEditIn, SkillImproveIn, SkillRunIn, SkillsRunIn

router = APIRouter(prefix="/api/skills")


@router.get("")
def cards(who: Who, ws: WS) -> dict[str, Any]:
    """Every skill with what it makes and its last run, and the new skills waiting in Review."""
    return ws.skills.cards(who)


@router.post("/drafts", status_code=201)
def draft(body: SkillDraftIn, who: Who, ws: WS) -> Task:
    """Ask a model to write a new skill from a description, or from something brought in."""
    return ws.skills.draft(who, ask=body.ask, capture_id=body.capture_id)


@router.get("/runs")
def recent_runs(who: Who, ws: WS, limit: int = 10) -> list[dict[str, Any]]:
    """The latest runs, from the Skills page and from every skill, with what came of each."""
    return ws.skills.recent(who, limit=limit)


@router.post("/runs", status_code=201)
def run_many(body: SkillsRunIn, who: Who, ws: WS) -> Task:
    """Ask a model for what is needed with the skills chosen, followed in order; with none
    chosen, with the one that fits."""
    return ws.skills.run_many(
        who,
        body.names,
        ask=body.ask,
        capture_id=body.capture_id,
        project=body.project,
        files=body.files,
    )


@router.get("/runs/{task_id}/files/{name:path}")
def made_file(task_id: str, name: str, who: Who, ws: WS, download: bool = True) -> FileResponse:
    """One file a run made, from its folder: a picture shown in place when asked, anything
    else downloaded (nothing a model made runs in this origin)."""
    path = ws.skills.made_file(who, task_id, name)
    return served(
        path,
        media=mimetypes.guess_type(path)[0],
        filename=os.path.basename(path),
        download=download,
    )


@router.get("/{name}/runs")
def runs(name: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    """The skill's recent runs and drafts, with what came of each."""
    return ws.skills.runs(who, name)


@router.post("/{name}/runs", status_code=201)
def run(name: str, body: SkillRunIn, who: Who, ws: WS) -> Task:
    """Ask a model to run the skill, with what is needed and what to use."""
    return ws.skills.run(
        who,
        name,
        ask=body.ask,
        capture_id=body.capture_id,
        project=body.project,
        files=body.files,
    )


@router.post("/{name}/improve", status_code=201)
def improve(name: str, body: SkillImproveIn, who: Who, ws: WS) -> Task:
    """Ask a model for a better version of the skill, learning from an example when one is
    given (something it made, or something brought in); it waits in Review."""
    return ws.skills.improve(
        who, name, ask=body.ask, capture_id=body.capture_id, example=body.example
    )


@router.put("/{name}")
def edit(name: str, body: SkillEditIn, who: Who, ws: WS) -> dict[str, Any]:
    """The person's own new version of the skill: it applies at once, as an undo point."""
    return ws.skills.edit(
        who,
        name,
        body=body.body,
        description=body.description,
        when_to_use=body.when_to_use,
        triggers=body.triggers,
        reason=body.reason,
    )


@router.get("/{name}/versions")
def versions(name: str, who: Who, ws: WS, text: bool = False) -> list[dict[str, Any]]:
    """Every version of the skill's procedure, newest first."""
    return ws.skills.versions(who, name, with_text=text)
