"""Versioned migrations, applied automatically on startup, with a preflight backup.

`upgrade()` brings a database to the latest revision. When an existing SQLite database has
pending revisions, it first copies the database next to the other backups with the SQLite
backup API, so a failed or unwanted upgrade can be rolled back by restoring that file.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from workspace_core.db.engine import Database

SCRIPT_LOCATION = "workspace_core.db:migrations"


@dataclass
class MigrationReport:
    before: str | None
    after: str | None
    pending: list[str] = field(default_factory=list)
    backup: str | None = None

    @property
    def changed(self) -> bool:
        return self.before != self.after


def config(db: Database) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", SCRIPT_LOCATION)
    cfg.set_main_option("sqlalchemy.url", db.url.replace("%", "%%"))
    return cfg


def current_revision(db: Database) -> str | None:
    with db.read() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head_revision(db: Database) -> str | None:
    return ScriptDirectory.from_config(config(db)).get_current_head()


def pending(db: Database) -> list[str]:
    script = ScriptDirectory.from_config(config(db))
    current = current_revision(db)
    revisions = list(script.iterate_revisions("head", current))
    return [rev.revision for rev in reversed(revisions)]


def backup_sqlite(db: Database, backup_dir: str, label: str) -> str | None:
    path = db.sqlite_path
    if not path or not os.path.exists(path):
        return None
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = os.path.join(backup_dir, f"{label}-{stamp}.sqlite")
    source = sqlite3.connect(path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def upgrade(db: Database, backup_dir: str | None = None) -> MigrationReport:
    before = current_revision(db)
    todo = pending(db)
    report = MigrationReport(before=before, after=before, pending=todo)
    if not todo:
        return report
    if before is not None and backup_dir:
        report.backup = backup_sqlite(db, backup_dir, f"pre-migrate-{before}")
    cfg = config(db)
    with db.write() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    report.after = current_revision(db)
    return report


def preview_sql(db: Database) -> str:
    """The SQL the pending revisions would run, without running it."""
    import io

    buffer = io.StringIO()
    cfg = config(db)
    cfg.output_buffer = buffer
    current = current_revision(db)
    command.upgrade(cfg, f"{current or 'base'}:head", sql=True)
    return buffer.getvalue()
