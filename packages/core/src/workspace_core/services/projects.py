"""Workspace projects: the boundary that tasks, working context and model access are scoped to.

The projects people see are the Brain's (its Focus items, `Brain.projects`): what they are
for, where they stand, their files and their progress. These rows remain the task bus's own
boundary underneath (a distillation request, a model's grant, a working item can name one),
and each can point at its Brain project (`brain_ref`).
"""

from __future__ import annotations

import builtins
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Project
from workspace_core.domain.states import PROJECT
from workspace_core.errors import ValidationFailed

from .runtime import Runtime


def _title(value: str | None) -> str:
    title = " ".join(str(value or "").split())
    if not title:
        raise ValidationFailed("A title is required.", field="title")
    if len(title) > 300:
        raise ValidationFailed("Titles are at most 300 characters.", field="title")
    return title


class Projects:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def create(
        self,
        who: Principal,
        *,
        title: str,
        summary: str = "",
        brain_ref: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Project:
        who.require("projects.write")
        with self.rt.write() as tx:
            row = tx.insert(
                schema.projects,
                {
                    "id": tx.new_id("proj"),
                    "workspace_id": self.rt.workspace_id,
                    "goal_id": None,
                    "title": _title(title),
                    "summary": summary or "",
                    "status": PROJECT.initial,
                    "brain_ref": brain_ref,
                    "provenance": provenance or {},
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                    "updated_at": tx.now,
                    "version": 1,
                    "archived_at": None,
                },
            )
            tx.emit(
                "project.created",
                actor_id=who.actor_id,
                subject_type="project",
                subject_id=row["id"],
                project_id=row["id"],
                data={"title": row["title"]},
            )
        return Project.from_row(row)

    def get(self, who: Principal, project_id: str) -> Project:
        who.require("projects.read", project_id)
        with self.rt.read() as tx:
            return Project.from_row(tx.one(schema.projects, project_id, "project"))

    def list(self, who: Principal, *, include_archived: bool = False) -> builtins.list[Project]:
        who.require("projects.read")
        table = schema.projects
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id)
        if not include_archived:
            query = query.where(table.c.archived_at.is_(None))
        with self.rt.read() as tx:
            rows = tx.rows(query.order_by(table.c.created_at))
        return [Project.from_row(r) for r in rows if who.sees_project(r["id"])]

    def find_by_brain_ref(self, who: Principal, brain_ref: str) -> Project | None:
        table = schema.projects
        with self.rt.read() as tx:
            row = tx.first(sa.select(table).where(table.c.brain_ref == brain_ref))
        return Project.from_row(row) if row and who.sees_project(row["id"]) else None

    def update(
        self,
        who: Principal,
        project_id: str,
        *,
        expected_version: int | None = None,
        title: str | None = None,
        summary: str | None = None,
        status: str | None = None,
        brain_ref: str | None = None,
    ) -> Project:
        who.require("projects.write", project_id)
        with self.rt.write() as tx:
            row = tx.one(schema.projects, project_id, "project")
            changes: dict[str, Any] = {}
            if title is not None:
                changes["title"] = _title(title)
            if summary is not None:
                changes["summary"] = summary
            if brain_ref is not None:
                changes["brain_ref"] = brain_ref or None
            if status is not None and status != row["status"]:
                PROJECT.check(row["status"], status)
                changes["status"] = status
                changes["archived_at"] = tx.now if status == "archived" else None
            row = tx.update(schema.projects, row, changes, expected_version=expected_version)
            tx.emit(
                "project.updated",
                actor_id=who.actor_id,
                subject_type="project",
                subject_id=project_id,
                project_id=project_id,
                data={"fields": sorted(changes)},
            )
        return Project.from_row(row)
