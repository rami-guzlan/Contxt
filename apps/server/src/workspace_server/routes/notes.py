"""Notes over REST: the person's scratchpad, its versions, and the two ways a note reaches the
Brain (filed as a document, or read by a model for what to remember)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Response

from workspace_core.domain.records import Task

from ..deps import WS, Who
from ..schemas import (
    NoteIn,
    NoteNameIn,
    NoteRestoreIn,
    NoteSaveIn,
    NoteToBrainIn,
    RememberIn,
)
from .brain import disposition

router = APIRouter(prefix="/api/notes")


@router.get("")
def list_notes(who: Who, ws: WS, archived: bool = False) -> list[dict[str, Any]]:
    """The person's notes, most recently changed first (without their text)."""
    return [dict(asdict(n), body=None) for n in ws.notes.list(who, archived=archived)]


@router.post("", status_code=201)
def create_note(body: NoteIn, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.notes.create(who, title=body.title, body=body.body))


@router.get("/{note_id}")
def get_note(note_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.notes.get(who, note_id))


@router.put("/{note_id}")
def save_note(note_id: str, body: NoteSaveIn, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(
        ws.notes.save(
            who,
            note_id,
            title=body.title,
            body=body.body,
            expected_version=body.expected_version,
        )
    )


@router.post("/{note_id}/name")
def name_version(note_id: str, body: NoteNameIn, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.notes.name_version(who, note_id, body.label))


@router.get("/{note_id}/versions")
def versions(note_id: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    return [asdict(v) for v in ws.notes.versions(who, note_id)]


@router.get("/{note_id}/versions/{revision}")
def version(note_id: str, revision: int, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.notes.version(who, note_id, revision))


@router.post("/{note_id}/restore")
def restore(note_id: str, body: NoteRestoreIn, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.notes.restore(who, note_id, body.revision))


@router.post("/{note_id}/archive")
def archive(note_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.notes.archive(who, note_id))


@router.post("/{note_id}/unarchive")
def unarchive(note_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.notes.archive(who, note_id, archived=False))


@router.get("/{note_id}/download")
def download(note_id: str, who: Who, ws: WS) -> Response:
    """The note as a Markdown file."""
    note = ws.notes.get(who, note_id)
    text = f"# {note.title}\n\n{note.body.strip()}\n"
    name = "".join(c if c.isalnum() or c in " -_" else "-" for c in note.title).strip() or "note"
    return Response(
        text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": disposition(f"{name}.md")},
    )


@router.post("/{note_id}/brain", status_code=201)
def to_brain(note_id: str, body: NoteToBrainIn, who: Who, ws: WS) -> dict[str, Any]:
    """Add the note to the Brain as a document, as it reads now (in a project when one is
    named): every AI can then quote it."""
    return asdict(ws.notes.to_brain(who, note_id, project=body.project, status=body.status))


@router.get("/{note_id}/remember")
def remember_requests(note_id: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    """The requests to find what to remember in this note, newest first, with what each
    proposed and where each proposal stands."""
    ws.notes.get(who, note_id)
    return [asdict(r) for r in ws.distill.requests(who, item_id=note_id, limit=20)]


@router.post("/{note_id}/remember", status_code=201)
def remember(note_id: str, body: RememberIn, who: Who, ws: WS) -> Task:
    """Ask a model to find what in this note should last, as proposals for the Brain."""
    ws.notes.get(who, note_id)
    return ws.distill.request(who, item_ids=[note_id], **body.model_dump())
