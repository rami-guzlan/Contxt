"""Skills over REST: the procedures your AI follows, run from the app, improved, written new."""

from __future__ import annotations

import mimetypes
import os
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse

from workspace_core.domain.records import Task
from workspace_core.errors import NotFound, ValidationFailed

from .. import skill_files
from ..deps import WS, Who
from ..files import served
from ..schemas import (
    SkillDraftIn,
    SkillEditIn,
    SkillGitIn,
    SkillImproveIn,
    SkillPushIn,
    SkillRunIn,
    SkillsRunIn,
    SuggestionDismissIn,
)
from .brain import disposition

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


@router.post("/import", status_code=201)
async def bring_in(
    who: Who,
    ws: WS,
    file: Annotated[UploadFile | None, File()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    paths: Annotated[list[str] | None, Form()] = None,
) -> dict[str, Any]:
    """A skill from a zip (`file`), or from a folder picked in the browser (`files`, each with
    its path inside the folder in `paths`). It applies at once, with an undo point; what the
    Brain does not keep is listed as skipped."""
    if file is not None:
        data = await file.read(skill_files.MAX_ZIP + 1)
        if len(data) > skill_files.MAX_ZIP:
            raise ValidationFailed("The zip is larger than 30 MB.")
        found = skill_files.read_zip(data)
        hint, source = (
            os.path.splitext(os.path.basename(file.filename or ""))[0],
            file.filename or "a zip",
        )
    elif files:
        named = list(paths or [])
        found = {}
        for index, upload in enumerate(files):
            rel = named[index] if index < len(named) else upload.filename or f"file-{index}"
            found[rel] = await upload.read(skill_files.MAX_ZIP + 1)
        top = next(iter(found), "").replace("\\", "/").split("/")[0]
        hint, source = top, f"the folder {top}"
    else:
        raise ValidationFailed("Bring in a zip, or the folder of a skill.")
    return _bring(ws, who, skill_files.read_bundle(found, hint=hint), source)


@router.post("/import/git", status_code=201)
def bring_in_git(body: SkillGitIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """A skill from a GitHub repository (a shallow clone with this computer's own git
    sign-in; Contxt keeps no token)."""
    cache = os.path.join(request.app.state.runtime.settings.data_dir, "library-cache")
    found, where = skill_files.fetch_repo_skill(body.url, cache, path=body.path)
    return _bring(ws, who, skill_files.read_bundle(found), where)


def _bring(ws: Any, who: Any, bundle: skill_files.Bundle, source: str) -> dict[str, Any]:
    made = ws.skills.import_skill(who, **bundle.fields(), source=source)
    return {**made, "skipped": bundle.skipped, "files": len(bundle.files)}


@router.get("/suggestions")
def suggestions(who: Who, ws: WS) -> dict[str, Any]:
    """Skills worth writing down: asks repeated with no skill to follow, and prompts run
    often. Found by code and no model."""
    return ws.suggestions.list(who)


@router.post("/suggestions/dismiss", status_code=204)
def dismiss(body: SuggestionDismissIn, who: Who, ws: WS) -> None:
    ws.suggestions.dismiss(who, body.key)


@router.get("/{name}/about")
def about(name: str, who: Who, ws: WS) -> dict[str, Any]:
    """What uses the skill, when it was last edited and used, what it loads that changed
    since, and its copies in Claude Code with how far behind each is."""
    return {
        "used_by": ws.skill_users(who, name),
        "freshness": ws.skills.freshness(who, name),
        "pushed": skill_files.pushed(ws, who, name),
    }


@router.get("/{name}/export")
def export(name: str, who: Who, ws: WS) -> Response:
    """The skill and its files as a zip, to bring into another Contxt or any tool."""
    skill = ws.skills.find(who, name)
    folder = ws.rt.brain.skill_folder(skill.name)
    if not folder:
        raise NotFound(f"The files of /{skill.name} are not on this computer.")
    return Response(
        skill_files.zip_skill(folder, skill.name),
        media_type="application/zip",
        headers={"Content-Disposition": disposition(f"{skill.name}.zip")},
    )


@router.post("/{name}/push")
def push(name: str, body: SkillPushIn, who: Who, ws: WS) -> dict[str, Any]:
    """Copy the skill into Claude Code, with a stamp of the version that went."""
    return skill_files.push(ws, who, name, project_dir=body.project_dir)


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
