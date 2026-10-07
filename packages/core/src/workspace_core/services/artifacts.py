"""Artifacts: typed, versioned results with lineage and their own review lifecycle.

Every version records where it came from (goal, project, task, run, producing model, prompt
version, the pinned input versions, and the context the producer says it used). No model can
add a version to another model's artifact, and nothing leaves the workspace unless a person
approved that version.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Any, Protocol

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain import artifact_types
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Artifact, ArtifactVersion, ExportRecord
from workspace_core.domain.states import ARTIFACT
from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed

from .bus import active_run
from .runtime import Runtime, recall, remember

MAX_ARTIFACT = 50 * 1024 * 1024
PREVIEW_CHARS = 20000


class Destination(Protocol):
    """Where an approved artifact can be sent. Implemented in workspace-connectors."""

    name: str
    label: str
    accepts: tuple[str, ...]

    def deliver(
        self, *, artifact: Artifact, version: ArtifactVersion, data: bytes
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Made:
    artifact: Artifact
    version: ArtifactVersion


def _textual(mime: str) -> bool:
    return mime.startswith("text/") or mime in ("application/json", "image/svg+xml")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "artifact"


def _refs(values: list[Any] | None) -> list[dict[str, Any]]:
    out = []
    for value in values or []:
        if isinstance(value, dict) and value.get("ref"):
            out.append({k: v for k, v in value.items() if k in ("ref", "version", "note")})
        elif isinstance(value, str) and value.strip():
            out.append({"ref": value.strip()})
    return out


class Artifacts:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.destinations: dict[str, Destination] = {}

    # ---------------------------------------------------------------- queries

    def get(self, who: Principal, artifact_id: str) -> Artifact:
        with self.rt.read() as tx:
            row = tx.one(schema.artifacts, artifact_id, "artifact")
        who.require("artifacts.read", row["project_id"])
        return Artifact.from_row(row)

    def list(
        self,
        who: Principal,
        *,
        project_id: str | None = None,
        goal_id: str | None = None,
        task_id: str | None = None,
        status: str | builtins.list[str] | None = None,
        type: str | None = None,
        created_by: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> builtins.list[Artifact]:
        who.require("artifacts.read", project_id)
        table = schema.artifacts
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id)
        for column, value in (
            ("project_id", project_id),
            ("goal_id", goal_id),
            ("task_id", task_id),
            ("type", type),
            ("created_by", created_by),
        ):
            if value:
                query = query.where(table.c[column] == value)
        if status:
            query = query.where(
                table.c.status.in_([status] if isinstance(status, str) else list(status))
            )
        if not include_archived:
            query = query.where(table.c.archived_at.is_(None))
        with self.rt.read() as tx:
            rows = tx.rows(query.order_by(table.c.updated_at.desc()).limit(limit))
        return [Artifact.from_row(r) for r in rows if who.sees_project(r["project_id"])]

    def versions(self, who: Principal, artifact_id: str) -> builtins.list[ArtifactVersion]:
        self.get(who, artifact_id)
        table = schema.artifact_versions
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table).where(table.c.artifact_id == artifact_id).order_by(table.c.number)
            )
        return [ArtifactVersion.from_row(r) for r in rows]

    def version(
        self, who: Principal, artifact_id: str, number: int | None = None
    ) -> ArtifactVersion:
        artifact = self.get(who, artifact_id)
        table = schema.artifact_versions
        with self.rt.read() as tx:
            row = tx.first(
                sa.select(table).where(
                    table.c.artifact_id == artifact_id,
                    table.c.number == (number or artifact.current_version),
                )
            )
        if row is None:
            raise NotFound(f"Artifact {artifact_id} has no version {number}.")
        return ArtifactVersion.from_row(row)

    def content(
        self, who: Principal, artifact_id: str, number: int | None = None
    ) -> tuple[ArtifactVersion, bytes]:
        version = self.version(who, artifact_id, number)
        return version, self.rt.objects.read(version.object_key)

    def exports(self, who: Principal, artifact_id: str) -> builtins.list[ExportRecord]:
        self.get(who, artifact_id)
        table = schema.exports
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table)
                .where(table.c.artifact_id == artifact_id)
                .order_by(table.c.created_at)
            )
        return [ExportRecord.from_row(r) for r in rows]

    # ---------------------------------------------------------------- writes

    def create(
        self,
        who: Principal,
        *,
        type: str,
        title: str,
        content: str | bytes,
        run_id: str | None = None,
        artifact_id: str | None = None,
        project_id: str | None = None,
        mime: str | None = None,
        filename: str | None = None,
        context_used: builtins.list[Any] | None = None,
        note: str | None = None,
        idempotency_key: str | None = None,
    ) -> Made:
        """A new artifact, or a new version of one this producer (or a person) made."""
        kind = artifact_types.get(type)
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if not data:
            raise ValidationFailed("An artifact needs content.", field="content")
        if len(data) > MAX_ARTIFACT:
            raise ValidationFailed("Artifacts are at most 50 MB.", field="content")
        mime = mime or kind.default_mime
        artifact_types.check_content(type, mime)
        if isinstance(content, str) and not _textual(mime):
            raise ValidationFailed(
                f"A {kind.label.lower()} ({mime}) needs binary content, not text.", field="content"
            )
        title = " ".join(str(title or "").split())
        if not title:
            raise ValidationFailed("An artifact needs a title.", field="title")
        request = {
            "type": type,
            "title": title,
            "run_id": run_id,
            "artifact_id": artifact_id,
            "project_id": project_id,
            "mime": mime,
            "filename": filename,
            "sha": hashlib.sha256(data).hexdigest(),
            "context_used": context_used,
            "note": note,
        }
        stored = self.rt.objects.put(data)
        preview = (
            data.decode("utf-8", errors="replace")[:PREVIEW_CHARS]
            if mime.startswith("text/") or mime == "application/json"
            else None
        )
        with self.rt.write() as tx:
            prior = recall(tx, who, idempotency_key, "artifacts.create", request)
            if prior:
                version = tx.one(schema.artifact_versions, prior, "artifact version")
                artifact = tx.one(schema.artifacts, version["artifact_id"], "artifact")
                return Made(Artifact.from_row(artifact), ArtifactVersion.from_row(version))
            lineage = self._lineage(tx, who, run_id, project_id)
            if artifact_id:
                artifact = self._revisable(tx, who, artifact_id, type)
                number = artifact["current_version"] + 1
                changes: dict[str, Any] = {"current_version": number, "title": title}
                if artifact["status"] != "draft":
                    ARTIFACT.check(artifact["status"], "draft")
                    changes["status"] = "draft"
                if lineage["run_id"]:
                    changes["run_id"] = lineage["run_id"]
                self._cancel_pending(tx, who, artifact["id"])
                artifact = tx.update(schema.artifacts, artifact, changes)
                event = "artifact.versioned"
            else:
                number = 1
                artifact = tx.insert(
                    schema.artifacts,
                    {
                        "id": tx.new_id("art"),
                        "workspace_id": self.rt.workspace_id,
                        "goal_id": lineage["goal_id"],
                        "project_id": lineage["project_id"],
                        "task_id": lineage["task_id"],
                        "run_id": lineage["run_id"],
                        "type": type,
                        "title": title,
                        "status": ARTIFACT.initial,
                        "current_version": 1,
                        "created_by": who.actor_id,
                        "created_at": tx.now,
                        "updated_at": tx.now,
                        "version": 1,
                        "archived_at": None,
                    },
                )
                event = "artifact.created"
            version = tx.insert(
                schema.artifact_versions,
                {
                    "id": tx.new_id("artv"),
                    "artifact_id": artifact["id"],
                    "number": number,
                    "object_key": stored.key,
                    "filename": filename or f"{slug(title)}-v{number}{kind.extension}",
                    "mime": mime,
                    "size": stored.size,
                    "content_hash": stored.key,
                    "preview_text": preview,
                    "run_id": lineage["run_id"],
                    "task_revision": lineage["task_revision"],
                    "prompt_version": lineage["prompt_version"],
                    "inputs": lineage["inputs"],
                    "context_used": _refs(context_used),
                    "note": note,
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                },
            )
            tx.emit(
                event,
                actor_id=who.actor_id,
                subject_type="artifact",
                subject_id=artifact["id"],
                project_id=artifact["project_id"],
                data={"version": number, "type": type, "title": title, "run_id": lineage["run_id"]},
            )
            remember(
                tx,
                who,
                idempotency_key,
                "artifacts.create",
                request,
                "artifact_version",
                version["id"],
            )
        return Made(Artifact.from_row(artifact), ArtifactVersion.from_row(version))

    def archive(self, who: Principal, artifact_id: str) -> Artifact:
        with self.rt.write() as tx:
            row = tx.one(schema.artifacts, artifact_id, "artifact")
            who.require("artifacts.review", row["project_id"])
            ARTIFACT.check(row["status"], "archived")
            row = tx.update(schema.artifacts, row, {"status": "archived", "archived_at": tx.now})
            tx.emit(
                "artifact.archived",
                actor_id=who.actor_id,
                subject_type="artifact",
                subject_id=artifact_id,
                project_id=row["project_id"],
            )
        return Artifact.from_row(row)

    def export(self, who: Principal, artifact_id: str, destination: str) -> ExportRecord:
        """Send the approved version to a destination. Never for an unapproved version."""
        target = self.destinations.get(destination)
        if target is None:
            raise NotFound(
                f"No destination {destination!r}; connected: "
                f"{', '.join(sorted(self.destinations)) or 'none'}."
            )
        with self.rt.read() as tx:
            artifact = tx.one(schema.artifacts, artifact_id, "artifact")
        who.require("artifacts.export", artifact["project_id"])
        if artifact["status"] not in ("approved", "exported"):
            raise Conflict(
                "Only an approved artifact can be exported; this one is "
                f"{artifact['status'].replace('_', ' ')}.",
                status=artifact["status"],
            )
        if artifact["type"] not in target.accepts:
            raise ValidationFailed(f"{target.label} does not accept {artifact['type']}.")
        version, data = self.content(who, artifact_id)
        result = target.deliver(artifact=Artifact.from_row(artifact), version=version, data=data)
        with self.rt.write() as tx:
            row = tx.one(schema.artifacts, artifact_id, "artifact")
            if row["status"] == "approved":
                tx.update(schema.artifacts, row, {"status": "exported"})
            record = tx.insert(
                schema.exports,
                {
                    "id": tx.new_id("exp"),
                    "artifact_id": artifact_id,
                    "artifact_version": version.number,
                    "destination": destination,
                    "status": "delivered",
                    "result": result or {},
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                },
            )
            tx.emit(
                "artifact.exported",
                actor_id=who.actor_id,
                subject_type="artifact",
                subject_id=artifact_id,
                project_id=row["project_id"],
                data={
                    "destination": destination,
                    "version": version.number,
                    "result": result or {},
                },
            )
        return ExportRecord.from_row(record)

    def bundle(
        self,
        who: Principal,
        *,
        project_id: str | None = None,
        goal_id: str | None = None,
        statuses: tuple[str, ...] = ("approved", "exported"),
    ) -> bytes:
        """A human-readable zip: README, lineage.json and the files, no special tools."""
        if not (project_id or goal_id):
            raise ValidationFailed("Bundle a project or a goal.")
        items = self.list(who, project_id=project_id, goal_id=goal_id, status=list(statuses))
        if goal_id and not project_id:
            with self.rt.read() as tx:
                projects = [
                    r["id"]
                    for r in tx.rows(
                        sa.select(schema.projects.c.id).where(schema.projects.c.goal_id == goal_id)
                    )
                ]
            extra = [
                a for p in projects for a in self.list(who, project_id=p, status=list(statuses))
            ]
            items = list({a.id: a for a in items + extra}.values())
        with self.rt.read() as tx:
            heading = (
                tx.one(schema.projects, project_id, "project")["title"]
                if project_id
                else tx.one(schema.goals, str(goal_id), "goal")["title"]
            )
        buffer = io.BytesIO()
        lineage = []
        lines = [f"# {heading}", "", f"{len(items)} artifact(s), exported from the workspace.", ""]
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for artifact in sorted(items, key=lambda a: a.created_at):
                version, data = self.content(who, artifact.id)
                path = f"artifacts/{version.filename}"
                archive.writestr(path, data)
                lines.append(
                    f"- **{artifact.title}** ({artifact.type}, version "
                    f"{version.number}, {artifact.status}): `{path}`"
                )
                lineage.append(
                    {"artifact": artifact.to_dict(), "version": version.to_dict(), "path": path}
                )
            archive.writestr("README.md", "\n".join(lines) + "\n")
            archive.writestr("lineage.json", json.dumps(lineage, indent=2, ensure_ascii=False))
        return buffer.getvalue()

    # ---------------------------------------------------------------- internals

    def _lineage(
        self, tx: Tx, who: Principal, run_id: str | None, project_id: str | None
    ) -> dict[str, Any]:
        if run_id:
            run = active_run(tx, who, run_id)
            task = tx.one(schema.tasks, run["task_id"], "task")
            who.require("artifacts.create", task["project_id"])
            project = tx.get(schema.projects, task["project_id"]) if task["project_id"] else None
            packet = run["packet"]
            return {
                "run_id": run_id,
                "task_id": task["id"],
                "project_id": task["project_id"],
                "goal_id": project["goal_id"] if project else None,
                "task_revision": run["task_revision"],
                "prompt_version": packet.get("instructions", {}).get("prompt_version"),
                "inputs": [
                    {
                        "ref": i.get("ref"),
                        "version": i.get("version"),
                        "content_hash": i.get("content_hash"),
                    }
                    for i in packet.get("inputs", [])
                ]
                # The Brain entries the run was handed, each at the version it was handed:
                # what to check again when one of them changes (Brain recall).
                + [
                    {
                        "ref": f"brain_entry:{e.get('id')}",
                        "version": None,
                        "content_hash": e.get("hash"),
                    }
                    for e in (packet.get("brain") or {}).get("entries") or []
                    if e.get("id")
                ],
            }
        if not who.is_human:
            raise ValidationFailed(
                "A model writes artifacts through a claimed run (run_id).", field="run_id"
            )
        who.require("artifacts.create", project_id)
        goal_id = None
        if project_id:
            goal_id = tx.one(schema.projects, project_id, "project")["goal_id"]
        return {
            "run_id": None,
            "task_id": None,
            "project_id": project_id,
            "goal_id": goal_id,
            "task_revision": None,
            "prompt_version": None,
            "inputs": [],
        }

    def _revisable(self, tx: Tx, who: Principal, artifact_id: str, type: str) -> dict[str, Any]:
        artifact = tx.one(schema.artifacts, artifact_id, "artifact")
        if artifact["type"] != type:
            raise ValidationFailed(f"This artifact is a {artifact['type']}, not a {type}.")
        if artifact["archived_at"]:
            raise Conflict("This artifact is archived.")
        if not who.is_human and artifact["created_by"] != who.actor_id:
            raise PermissionDenied(
                "Only the model that made an artifact, or a person, can add "
                "a version; create a new artifact instead."
            )
        return artifact

    def _cancel_pending(self, tx: Tx, who: Principal, artifact_id: str) -> None:
        table = schema.approvals
        for row in tx.rows(
            sa.select(table).where(
                table.c.subject_type == "artifact",
                table.c.subject_id == artifact_id,
                table.c.status == "pending",
            )
        ):
            tx.update(
                table,
                row,
                {
                    "status": "cancelled",
                    "decided_at": tx.now,
                    "decided_by": who.actor_id,
                    "decision_note": "superseded by a new version",
                },
            )
