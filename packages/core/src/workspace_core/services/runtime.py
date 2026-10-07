"""What every service shares: the database, time, file storage and outside ports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import Clock
from workspace_core.db import schema
from workspace_core.db.engine import Database
from workspace_core.db.tx import Tx
from workspace_core.domain.policy import Principal
from workspace_core.errors import IdempotencyMismatch
from workspace_core.ports import BrainPort, NoBrain, TextExtractor
from workspace_core.storage.objects import ObjectStore


@dataclass
class Runtime:
    db: Database
    clock: Clock
    objects: ObjectStore
    workspace_id: str = ""
    brain: BrainPort = field(default_factory=NoBrain)
    extractor: TextExtractor | None = None
    lease_seconds: int = 900
    max_lease_seconds: int = 4 * 3600
    max_input_chars: int = 20000

    @contextmanager
    def write(self) -> Iterator[Tx]:
        with self.db.write() as conn:
            yield Tx(conn, self.clock.now(), self.workspace_id)

    @contextmanager
    def read(self) -> Iterator[Tx]:
        with self.db.read() as conn:
            yield Tx(conn, self.clock.now(), self.workspace_id)


def request_hash(request: dict[str, Any]) -> str:
    text = json.dumps(request, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def recall(
    tx: Tx, who: Principal, key: str | None, operation: str, request: dict[str, Any]
) -> str | None:
    """The id this key already produced for the same request, if any."""
    if not key:
        return None
    table = schema.idempotency_keys
    row = tx.first(sa.select(table).where(table.c.actor_id == who.actor_id, table.c.key == key))
    if row is None:
        return None
    if row["operation"] != operation or row["request_hash"] != request_hash(request):
        raise IdempotencyMismatch(
            f"Idempotency key {key!r} was already used for a different request.",
            key=key,
            operation=row["operation"],
        )
    return str(row["result_id"])


def remember(
    tx: Tx,
    who: Principal,
    key: str | None,
    operation: str,
    request: dict[str, Any],
    result_type: str,
    result_id: str,
) -> None:
    if not key:
        return
    tx.insert(
        schema.idempotency_keys,
        {
            "actor_id": who.actor_id,
            "key": key,
            "operation": operation,
            "request_hash": request_hash(request),
            "result_type": result_type,
            "result_id": result_id,
            "created_at": tx.now,
        },
    )
