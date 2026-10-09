"""The Workspace over REST: the owner's docs and links by project (and anything linked to a
project), made from a template or brought in from a file, linked to projects from either side,
and worked on with AI only when asked (draft from it, push back on it, continue it), with what a
run made taken as the doc's next version, added at its end, or kept as a new doc. A doc leaves
as Markdown or Word. Each doc is a note: its text, versions and the rest are /api/notes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Response, UploadFile

from workspace_core.domain.records import Task
from workspace_core.services.notes import Note

from ..deps import WS, Who
from ..schemas import (
    WorkspaceContinueIn,
    WorkspaceDocIn,
    WorkspaceDraftIn,
    WorkspaceLinkIn,
    WorkspaceProjectsIn,
    WorkspaceUseIn,
)
from .brain import disposition

router = APIRouter(prefix="/api/workspace")

MAX_IMPORT = 25 * 1024 * 1024


@router.get("/items")  # GET /api/workspace itself is the app's settings (routes/system.py)
def items(who: Who, ws: WS, project: str | None = None, archived: bool = False) -> dict[str, Any]:
    """Docs and links by project, and anything linked to one (or what was set aside, with
    `archived`); for one project (`project`), also the agents that work on it."""
    return ws.docs.items(who, project=project or None, archived=archived)


@router.post("/docs", status_code=201)
def new_doc(body: WorkspaceDocIn, who: Who, ws: WS) -> Note:
    """A new doc, blank or from a template, linked to the projects given."""
    return ws.docs.create(who, template=body.template, title=body.title, projects=body.projects)


@router.post("/links", status_code=201)
def new_link(body: WorkspaceLinkIn, who: Who, ws: WS) -> Note:
    """A link kept in the Workspace: a calendar, a sheet, a folder, a page."""
    return ws.docs.link(who, url=body.url, title=body.title, projects=body.projects)


@router.post("/import", status_code=201)
async def import_doc(
    who: Who,
    ws: WS,
    file: Annotated[UploadFile, File()],
    projects: Annotated[str, Form()] = "",
) -> Note:
    """A document brought in as a doc to work in (projects: ids, comma separated)."""
    data = await file.read(MAX_IMPORT + 1)
    linked = [p.strip() for p in projects.split(",") if p.strip()]
    return ws.docs.import_file(who, filename=file.filename or "", data=data, projects=linked)


@router.put("/{note_id}/projects")
def link_projects(note_id: str, body: WorkspaceProjectsIn, who: Who, ws: WS) -> Note:
    """Link it to these projects, and no others. It stays private and is never copied."""
    return ws.docs.set_projects(who, note_id, body.projects)


@router.post("/{note_id}/draft", status_code=201)
def draft(note_id: str, body: WorkspaceDraftIn, who: Who, ws: WS) -> Task:
    """Draft from the doc with a skill or an agent, the doc pinned as it is now."""
    return ws.docs.draft(who, note_id, skill=body.skill, agent=body.agent, ask=body.ask)


@router.post("/{note_id}/push-back", status_code=201)
def push_back(note_id: str, who: Who, ws: WS) -> Task:
    """Questions and challenges on the doc; nothing written for you."""
    return ws.docs.push_back(who, note_id)


@router.post("/{note_id}/continue", status_code=201)
def continue_doc(note_id: str, body: WorkspaceContinueIn, who: Who, ws: WS) -> Task:
    """Finish the doc where it stops, or from the part named."""
    return ws.docs.continue_(who, note_id, where=body.where)


@router.get("/{note_id}/runs")
def runs(note_id: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    """What AI made from this doc, newest first."""
    return ws.docs.runs(who, note_id)


@router.post("/{note_id}/use")
def use(note_id: str, body: WorkspaceUseIn, who: Who, ws: WS) -> Note:
    """Take what a run made: as the next version, added at the end, or as a new doc."""
    return ws.docs.use(who, note_id, task_id=body.task_id, how=body.how)


@router.get("/{note_id}/export")
def export(note_id: str, who: Who, ws: WS, format: str = "md") -> Response:
    """The doc as Markdown or Word, as a download."""
    name, mime, data = ws.docs.export(who, note_id, fmt=format)
    return Response(
        data,
        media_type=mime,
        headers={"Content-Disposition": disposition(name), "X-Content-Type-Options": "nosniff"},
    )
