"""The Library over REST: documents kept whole, by what they are for (guides to follow,
references to read whole, influences whose taste to borrow), added by upload, by writing, from a
web page or from a GitHub repository, and kept current from where they came from."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, UploadFile

from workspace_core.errors import ValidationFailed

from ..deps import WS, Who
from ..library import Library, today
from ..schemas import LibraryItemIn, LibraryRefreshIn, LibraryRepoIn, LibraryUrlIn, LibraryWriteIn

router = APIRouter(prefix="/api/library")

MAX_UPLOAD = 10 * 1024 * 1024
KINDS = ("guide", "reference", "influence")


def library(request: Request) -> Library:
    found: Library = request.app.state.runtime.library
    return found


def _filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "library-item"
    return f"{slug}.md"


def _filed(result: Any) -> dict[str, Any]:
    out = asdict(result)
    out["status"] = "unchanged" if result.status == "duplicate" else result.status
    return out


@router.get("")
def items(who: Who, ws: WS) -> list[dict[str, Any]]:
    """Every document kept whole, as Library items, most recently changed first."""
    return ws.brain.library(who)


@router.get("/item")
def item(path: str, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """One item with its text, and when the app last checked it against its source."""
    found = ws.brain.library_item(who, path)
    content = ws.brain.file_content(who, path)
    found["text"] = content.data.decode("utf-8", errors="replace")
    found["checked_at"] = library(request).checks.read().get(path)
    return found


@router.put("/item")
def update(body: LibraryItemIn, who: Who, ws: WS) -> dict[str, Any]:
    """Change what kind of item it is, or how often it is fetched again: one undo point."""
    return ws.brain.library_update(who, body.path, kind=body.kind, refresh=body.refresh)


@router.post("/write", status_code=201)
def write(body: LibraryWriteIn, who: Who, ws: WS) -> dict[str, Any]:
    """Keep a guide (or a reference) written here, in Markdown."""
    result = ws.brain.add_file(
        who,
        filename=_filename(body.title),
        data=body.text.encode("utf-8"),
        title=body.title,
        project=body.project,
        library={"library": body.kind},
    )
    return _filed(result)


@router.post("/upload", status_code=201)
async def upload(
    who: Who,
    ws: WS,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "reference",
    title: Annotated[str, Form()] = "",
    project: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """Keep a document whole in the Library: PDF, Word, PowerPoint, HTML, Markdown or text."""
    if kind not in KINDS:
        raise ValidationFailed(
            "A Library item is a guide, a reference or an influence.", field="kind"
        )
    data = await file.read(MAX_UPLOAD + 1)
    result = ws.brain.add_file(
        who,
        filename=file.filename or "",
        data=data,
        title=title,
        project=project or None,
        library={"library": kind},
    )
    return _filed(result)


@router.post("/url", status_code=201)
def from_url(body: LibraryUrlIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Fetch a web page and keep it, with where it came from and how often to fetch it again."""
    source = library(request).fetch(url=body.url)
    title = body.title.strip() or source.title
    result = ws.brain.add_file(
        who,
        filename=_filename(title),
        data=source.markdown.encode("utf-8"),
        title=title,
        project=body.project,
        library={
            "library": body.kind,
            "source_url": source.url,
            "fetched_at": today(),
            "refresh": body.refresh,
        },
    )
    if result.path:
        library(request).checks.mark(result.path)
    return _filed(result)


@router.post("/repo", status_code=201)
def from_repo(body: LibraryRepoIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Keep a GitHub repository as a snapshot: its README, its folder tree and the files
    picked, fetched with this computer's own git sign-in."""
    source = library(request).fetch(repo=body.url, paths=body.paths)
    title = body.title.strip() or source.title
    result = ws.brain.add_file(
        who,
        filename=_filename(title),
        data=source.markdown.encode("utf-8"),
        title=title,
        project=body.project,
        library={
            "library": body.kind,
            "source_repo": source.url,
            "source_paths": list(source.paths),
            "fetched_at": today(),
            "refresh": body.refresh,
        },
    )
    if result.path:
        library(request).checks.mark(result.path)
    return _filed(result)


@router.post("/refresh")
def refresh(body: LibraryRefreshIn, request: Request, who: Who) -> dict[str, Any]:
    """Fetch an item again now. Changed text goes in as its next version (with an undo
    point); unchanged text changes nothing."""
    return library(request).refresh(who, body.path)
