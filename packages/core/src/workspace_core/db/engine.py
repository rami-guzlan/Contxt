"""Database access: one engine, write transactions and read transactions.

SQLite (the default) runs in WAL mode with foreign keys on. Write transactions start with
BEGIN IMMEDIATE, so the API server and the worker serialize their writes instead of failing a
lock upgrade halfway through; reads start with a plain deferred BEGIN and never block writers.
PostgreSQL uses ordinary transactions; every contested write in the services is a conditional
UPDATE, which is atomic on both backends.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine


def sqlite_url(path: str) -> str:
    return "sqlite:///" + os.path.abspath(path).replace("\\", "/")


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return sa.create_engine(url, pool_pre_ping=True)
    memory = url in ("sqlite://", "sqlite:///:memory:")
    engine = sa.create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=sa.pool.StaticPool if memory else None,
    )

    @sa.event.listens_for(engine, "connect")
    def _connect(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # the begin listener issues BEGIN itself
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        if not memory:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    @sa.event.listens_for(engine, "begin")
    def _begin(conn: Connection) -> None:
        mode = conn.get_execution_options().get("sqlite_begin", "IMMEDIATE")
        conn.exec_driver_sql(f"BEGIN {mode}")

    return engine


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = make_engine(url)

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @property
    def sqlite_path(self) -> str | None:
        if not self.is_sqlite or self.url in ("sqlite://", "sqlite:///:memory:"):
            return None
        return self.url.split("sqlite:///", 1)[1]

    @contextmanager
    def write(self) -> Iterator[Connection]:
        with self.engine.connect() as conn, conn.begin():
            yield conn

    @contextmanager
    def read(self) -> Iterator[Connection]:
        with self.engine.connect() as base:
            conn = base.execution_options(sqlite_begin="DEFERRED")
            with conn.begin():
                yield conn

    def close(self) -> None:
        self.engine.dispose()
