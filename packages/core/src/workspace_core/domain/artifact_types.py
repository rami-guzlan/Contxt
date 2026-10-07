"""Artifact types: each has a small contract for what it holds and how it is previewed.

Destinations (connectors) declare which of these types they accept, so a routing action only
appears where it makes sense.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from workspace_core.errors import ValidationFailed


@dataclass(frozen=True)
class ArtifactType:
    name: str
    label: str
    mimes: tuple[str, ...]  # fnmatch patterns
    preview: str  # markdown | text | image | table | none
    default_mime: str
    extension: str


TYPES: dict[str, ArtifactType] = {
    t.name: t
    for t in (
        ArtifactType(
            "document",
            "Document",
            (
                "text/markdown",
                "text/plain",
                "text/html",
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.*",
            ),
            "markdown",
            "text/markdown",
            ".md",
        ),
        ArtifactType(
            "social_post",
            "Social post",
            ("text/plain", "text/markdown"),
            "text",
            "text/plain",
            ".txt",
        ),
        ArtifactType("image", "Image", ("image/*",), "image", "image/png", ".png"),
        ArtifactType(
            "data_file",
            "Data file",
            (
                "text/csv",
                "application/json",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "table",
            "text/csv",
            ".csv",
        ),
        ArtifactType("file", "File", ("*",), "none", "application/octet-stream", ".bin"),
    )
}


def get(name: str) -> ArtifactType:
    try:
        return TYPES[name]
    except KeyError as exc:
        raise ValidationFailed(
            f"Unknown artifact type {name!r}; use one of {', '.join(TYPES)}.", field="type"
        ) from exc


def check_content(type_name: str, mime: str) -> ArtifactType:
    kind = get(type_name)
    if not any(fnmatch.fnmatch(mime, pattern) for pattern in kind.mimes):
        raise ValidationFailed(
            f"A {kind.label.lower()} cannot hold {mime}; it takes {', '.join(kind.mimes)}.",
            field="mime",
        )
    return kind
