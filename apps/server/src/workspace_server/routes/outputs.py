"""The outputs folder over REST: list it, download a file, see what a file was made from, and
organize it (a new folder; move or rename a file). Nothing is ever deleted."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from ..deps import Who
from ..outputs import Outputs
from ..schemas import OutputFolderIn, OutputLinkIn, OutputMoveIn
from .brain import disposition

router = APIRouter(prefix="/api/outputs")


def outputs(request: Request) -> Outputs:
    found: Outputs = request.app.state.runtime.outputs
    return found


@router.get("")
def listing(request: Request, who: Who) -> dict[str, Any]:
    """Every file in the outputs folder, newest first, and its folders."""
    return outputs(request).listing(who)


@router.get("/file")
def download(request: Request, who: Who, path: str, download: bool = True) -> FileResponse:
    """One file, as a download (or shown in place with download=false)."""
    found, name, mime = outputs(request).file(who, path)
    headers = {"Content-Disposition": disposition(name)} if download else None
    return FileResponse(found, media_type=mime, headers=headers)


@router.get("/made-from")
def made_from(request: Request, who: Who, path: str) -> dict[str, Any]:
    """What one file was made from: a skill run and what it was handed, an export and its
    work, or a conversation that said it saved the file."""
    return outputs(request).made_from(who, path)


@router.post("/folders", status_code=201)
def make_folder(body: OutputFolderIn, request: Request, who: Who) -> dict[str, Any]:
    return outputs(request).make_folder(who, body.path)


@router.post("/link")
def link(body: OutputLinkIn, request: Request, who: Who) -> dict[str, Any]:
    """Say what a file is for: a project, a State row."""
    return outputs(request).link(who, body.path, project=body.project, row=body.row)


@router.post("/move")
def move(body: OutputMoveIn, request: Request, who: Who) -> dict[str, Any]:
    """Move or rename one file; never over another."""
    return outputs(request).move(who, body.source, body.target)
