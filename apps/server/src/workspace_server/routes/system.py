"""Health, identity, the numbers every page shows, and global search."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request

from workspace_core import __version__
from workspace_core.db import migrate
from workspace_core.domain.records import Event, WorkspaceInfo

from ..deps import WS, Who
from ..schemas import WorkspacePatch

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    ws = request.app.state.ws
    return {
        "status": "ok",
        "version": __version__,
        "schema_revision": migrate.current_revision(ws.rt.db),
        "brain": ws.rt.brain.status().get("available", False),
    }


@router.get("/me")
def me(who: Who, ws: WS) -> dict[str, Any]:
    return {
        "actor_id": who.actor_id,
        "kind": who.kind,
        "name": who.name,
        "actions": sorted(who.grant.actions),
        "projects": sorted(who.grant.projects) if who.grant.projects is not None else None,
        "workspace": ws.info(),
    }


@router.get("/workspace")
def workspace(who: Who, ws: WS) -> WorkspaceInfo:
    return ws.info()


@router.patch("/workspace")
def update_workspace(body: WorkspacePatch, who: Who, ws: WS) -> WorkspaceInfo:
    return ws.update_settings(who, **body.changes())


@router.get("/home")
def home(who: Who, ws: WS) -> dict[str, Any]:
    """What the navigation shows on every page: the workspace, and what waits for the person."""
    return {"workspace": ws.info(), "counts": ws.counts(who)}


@router.get("/events")
def events(
    who: Who,
    ws: WS,
    subject_id: str | None = None,
    actor_id: str | None = None,
    include_noise: bool = False,
    before_seq: int | None = None,
    limit: int = 100,
) -> list[Event]:
    """What happened in the app, newest first: notes, files, decisions, AI work."""
    return ws.events.activity(
        who,
        subject_id=subject_id,
        actor_id=actor_id,
        include_noise=include_noise,
        before_seq=before_seq,
        limit=limit,
    )


@router.get("/search")
def search(q: str, who: Who, ws: WS, limit: int = 10) -> dict[str, Any]:
    """The Brain's entries, the projects it follows and the caller's notes, matching `q`."""
    results = ws.search(who, q, limit=limit)
    return {
        "query": q,
        "brain": [asdict(h) for h in results.brain],
        "projects": [asdict(p) for p in results.projects],
        "notes": [dict(asdict(n), body=None) for n in results.notes],
    }
