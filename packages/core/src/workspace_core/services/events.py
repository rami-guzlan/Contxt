"""The activity view over the append-only event log: meaningful actions, not polling noise."""

from __future__ import annotations

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Event

from .runtime import Runtime


class Events:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def activity(
        self,
        who: Principal,
        *,
        project_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        actor_id: str | None = None,
        types: list[str] | None = None,
        include_noise: bool = False,
        before_seq: int | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Newest first. Heartbeats and polls are hidden unless asked for."""
        who.require("events.read", project_id)
        table = schema.events
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id)
        if project_id:
            query = query.where(table.c.project_id == project_id)
        if subject_type:
            query = query.where(table.c.subject_type == subject_type)
        if subject_id:
            query = query.where(table.c.subject_id == subject_id)
        if actor_id:
            query = query.where(table.c.actor_id == actor_id)
        if types:
            query = query.where(table.c.type.in_(types))
        if not include_noise:
            query = query.where(table.c.noise.is_(False))
        if before_seq:
            query = query.where(table.c.seq < before_seq)
        with self.rt.read() as tx:
            rows = tx.rows(query.order_by(table.c.seq.desc()).limit(min(limit, 500)))
        return [Event.from_row(r) for r in rows if who.sees_project(r["project_id"])]
