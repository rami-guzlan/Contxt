"""One transaction, with the few operations services need and nothing clever.

Every write goes through `update`, which bumps `version` with a conditional UPDATE: if another
writer got there first the row count is zero and the caller gets a VersionConflict instead of
silently overwriting. Every state change appends its event with `emit` in the same transaction,
so the event log and the records can never disagree.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from workspace_core.clock import iso
from workspace_core.errors import NotFound, VersionConflict
from workspace_core.ids import new_id

from . import schema


class Tx:
    def __init__(self, conn: Connection, moment: datetime, workspace_id: str) -> None:
        self.conn = conn
        self.moment = moment
        self.now = iso(moment)
        self.workspace_id = workspace_id

    # ---------------------------------------------------------------- reads

    def get(self, table: sa.Table, ident: str) -> dict[str, Any] | None:
        row = self.conn.execute(sa.select(table).where(table.c.id == ident)).mappings().first()
        return dict(row) if row else None

    def one(self, table: sa.Table, ident: str, what: str) -> dict[str, Any]:
        row = self.get(table, ident)
        if row is None:
            raise NotFound(f"No {what} with id {ident}.", id=ident)
        return row

    def rows(self, statement: sa.Select[Any]) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(statement).mappings()]

    def first(self, statement: sa.Select[Any]) -> dict[str, Any] | None:
        row = self.conn.execute(statement).mappings().first()
        return dict(row) if row else None

    def scalar(self, statement: sa.Select[Any]) -> Any:
        return self.conn.execute(statement).scalar()

    # ---------------------------------------------------------------- writes

    def new_id(self, prefix: str) -> str:
        return new_id(prefix, self.moment)

    def insert(self, table: sa.Table, values: dict[str, Any]) -> dict[str, Any]:
        self.conn.execute(table.insert().values(**values))
        return dict(values)

    def update(
        self,
        table: sa.Table,
        row: dict[str, Any],
        values: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        current = int(row["version"])
        if expected_version is not None and int(expected_version) != current:
            raise VersionConflict(
                f"This record changed since you read it (version {expected_version}, now "
                f"{current}). Reload and try again.",
                id=row["id"],
                expected=expected_version,
                actual=current,
            )
        changes = dict(values, version=current + 1)
        if "updated_at" in table.c:
            changes["updated_at"] = self.now
        result = self.conn.execute(
            table.update()
            .where(table.c.id == row["id"], table.c.version == current)
            .values(**changes)
        )
        if result.rowcount != 1:
            raise VersionConflict(
                "This record was changed by someone else. Reload and try again.", id=row["id"]
            )
        return dict(row, **changes)

    def emit(
        self,
        type: str,
        *,
        actor_id: str,
        subject_type: str,
        subject_id: str,
        project_id: str | None = None,
        data: dict[str, Any] | None = None,
        reason: str | None = None,
        noise: bool = False,
    ) -> str:
        event_id = self.new_id("evt")
        self.conn.execute(
            schema.events.insert().values(
                id=event_id,
                workspace_id=self.workspace_id,
                at=self.now,
                actor_id=actor_id,
                type=type,
                subject_type=subject_type,
                subject_id=subject_id,
                project_id=project_id,
                reason=reason,
                data=data or {},
                noise=noise,
            )
        )
        return event_id
