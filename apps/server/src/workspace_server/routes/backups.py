"""Backups from the app: make one now (the database, the stored files and the Brain, with its
original documents), list them, and download one. They live in the data folder's backups/,
beside the snapshots taken before a migration; restoring stays a command (`contxt restore`)."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from workspace_core.backup import backup
from workspace_core.errors import NotFound, PermissionDenied

from ..deps import WS, Who
from .brain import disposition

router = APIRouter(prefix="/api/backups")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.zip$")


def _folder(request: Request) -> str:
    return os.path.join(request.app.state.settings.data_dir, "backups")


@router.get("")
def listing(request: Request, who: Who) -> list[dict[str, Any]]:
    """The backups on this computer, newest first."""
    who.require("workspace.admin")
    folder = _folder(request)
    out = []
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not NAME.match(name) or not os.path.isfile(path):
                continue
            info = os.stat(path)
            out.append(
                {
                    "name": name,
                    "size": info.st_size,
                    "at": datetime.fromtimestamp(info.st_mtime, UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
    out.sort(key=lambda b: str(b["at"]), reverse=True)
    return out


@router.post("", status_code=201)
def make(request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Back up now: the database, the stored files and the Brain (with its original
    documents), in one archive."""
    who.require("workspace.admin")
    if not who.is_human:
        raise PermissionDenied("Only a person makes a backup.")
    folder = _folder(request)
    os.makedirs(folder, exist_ok=True)
    stamp = ws.rt.clock.now().strftime("%Y%m%dT%H%M%SZ")
    name = f"workspace-{stamp}.zip"
    path = os.path.join(folder, name)
    vault = request.app.state.settings.brain_vault
    manifest = backup(ws, path, brain_vault=vault or None)
    with ws.rt.write() as tx:
        tx.emit(
            "workspace.backed_up",
            actor_id=who.actor_id,
            subject_type="workspace",
            subject_id=ws.rt.workspace_id,
            data={"name": name, "brain": bool(manifest["brain"]["included"])},
        )
    return {
        "name": name,
        "size": os.path.getsize(path),
        "records": sum(manifest["tables"].values()),
        "files": manifest["objects"]["count"],
        "brain_files": manifest["brain"]["files"],
        "originals": manifest["brain"].get("originals", 0),
    }


@router.get("/{name}")
def download(name: str, request: Request, who: Who) -> FileResponse:
    """One backup, as a download."""
    who.require("workspace.admin")
    path = os.path.join(_folder(request), name)
    if not NAME.match(name) or not os.path.isfile(path):
        raise NotFound(f"No backup {name}.")
    return FileResponse(
        path, media_type="application/zip", headers={"Content-Disposition": disposition(name)}
    )
