"""The earlier workspace over REST: what it holds, a copy as files, and its context moved into
the Brain (services/legacy.py)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

from ..deps import WS, Who

router = APIRouter(prefix="/api/legacy")


def export_dir(root: str, now: datetime) -> str:
    """A new folder for a copy made `now`, under `root` (the workspace's exports)."""
    base = os.path.join(root, f"workspace-export-{now:%Y-%m-%d}")
    return base if not os.path.exists(base) else f"{base}-{now:%H%M%S}"


@router.get("")
def summary(who: Who, ws: WS) -> dict[str, Any]:
    """How much the earlier workspace holds, when it was copied out, and what has moved."""
    return ws.legacy.summary(who)


@router.post("/export", status_code=201)
def export(request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Write everything the earlier workspace holds to a new folder; nothing changes in it."""
    settings = request.app.state.settings
    root = settings.exports_dir or os.path.join(settings.data_dir, "exports")
    made = ws.legacy.export(who, export_dir(root, ws.rt.clock.now()))
    return {"dir": made["dir"], "files": made["files"]}


@router.post("/bring-into-brain")
def bring_into_brain(who: Who, ws: WS) -> dict[str, Any]:
    """Move the earlier workspace's context into the Brain (once; a second run adds nothing)."""
    return ws.legacy.bring_into_brain(who)
