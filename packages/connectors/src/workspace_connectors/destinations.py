"""Destinations: where an approved artifact can be sent.

A destination declares the artifact types it accepts. The core only offers it for an approved
version, records every export as an event, and never exports on its own.
"""

from __future__ import annotations

import os
import re
from typing import Any

from workspace_core.domain.artifact_types import TYPES
from workspace_core.domain.records import Artifact, ArtifactVersion


def _safe(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return cleaned[:120] or "artifact"


class FolderDestination:
    """Copies the approved file into a local folder, one subfolder per project."""

    name = "folder"
    label = "Local folder"
    accepts = tuple(TYPES)

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)

    def deliver(
        self, *, artifact: Artifact, version: ArtifactVersion, data: bytes
    ) -> dict[str, Any]:
        folder = os.path.join(self.root, _safe(artifact.project_id or "unfiled"))
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, _safe(version.filename))
        stem, ext = os.path.splitext(target)
        counter = 2
        while os.path.exists(target):
            with open(target, "rb") as handle:
                if handle.read() == data:
                    return {"location": target, "unchanged": True}
            target = f"{stem}-{counter}{ext}"
            counter += 1
        with open(target, "wb") as handle:
            handle.write(data)
        return {"location": target, "bytes": len(data)}
