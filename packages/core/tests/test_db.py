import os
import sqlite3

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from workspace_core.db import migrate
from workspace_core.db.engine import Database, sqlite_url
from workspace_core.db.schema import metadata
from workspace_core.storage.objects import ObjectStore


def test_migrations_build_exactly_the_declared_schema(tmp_path):
    db = Database(sqlite_url(tmp_path / "ws.sqlite"))
    report = migrate.upgrade(db, backup_dir=str(tmp_path / "backups"))
    assert report.before is None and report.after == migrate.head_revision(db)
    assert report.backup is None  # nothing to back up on a fresh database
    with db.read() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    assert diff == []
    assert migrate.pending(db) == []
    again = migrate.upgrade(db, backup_dir=str(tmp_path / "backups"))
    assert not again.changed
    db.close()


def test_sqlite_runs_in_wal_mode_with_foreign_keys(tmp_path):
    db = Database(sqlite_url(tmp_path / "ws.sqlite"))
    migrate.upgrade(db)
    with db.read() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    db.close()


def test_writes_roll_back_on_error(tmp_path):
    db = Database(sqlite_url(tmp_path / "ws.sqlite"))
    migrate.upgrade(db)
    table = metadata.tables["workspaces"]
    row = {
        "id": "ws_1",
        "name": "x",
        "timezone": "UTC",
        "settings": {},
        "created_at": "t",
        "updated_at": "t",
        "version": 1,
    }
    try:
        with db.write() as conn:
            conn.execute(table.insert().values(**row))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with db.read() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(table)).scalar() == 0
    db.close()


def test_preflight_backup_is_a_consistent_copy(tmp_path):
    path = tmp_path / "ws.sqlite"
    db = Database(sqlite_url(path))
    migrate.upgrade(db)
    copy = migrate.backup_sqlite(db, str(tmp_path / "backups"), "pre-migrate-test")
    assert copy and os.path.exists(copy)
    conn = sqlite3.connect(copy)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"tasks", "events", "alembic_version"} <= tables
    db.close()


def test_preview_lists_the_sql_without_running_it(tmp_path):
    db = Database(sqlite_url(tmp_path / "ws.sqlite"))
    sql = migrate.preview_sql(db)
    assert "CREATE TABLE tasks" in sql
    assert migrate.current_revision(db) is None
    db.close()


def test_object_store_is_content_addressed(tmp_path):
    store = ObjectStore(str(tmp_path / "objects"))
    first = store.put(b"hello")
    second = store.put(b"hello")
    assert first.key == second.key and first.size == 5
    assert store.read(first.key) == b"hello"
    assert store.exists(first.key)
    assert not store.exists("0" * 64)
    other = store.put(b"world")
    assert other.key != first.key
    assert len(list(store.keys())) == 2


def test_migrations_match_the_schema_on_postgres(database_url):
    if not database_url:
        pytest.skip("set CONTXT_TEST_DATABASE_URL to check PostgreSQL")
    db = Database(database_url)
    try:
        migrate.upgrade(db)
        with db.read() as conn:
            assert compare_metadata(MigrationContext.configure(conn), metadata) == []
    finally:
        db.close()


def test_a_database_from_the_first_release_upgrades_with_its_data(tmp_path):
    from alembic import command

    db = Database(sqlite_url(tmp_path / "ws.sqlite"))
    cfg = migrate.config(db)
    with db.write() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
    with db.write() as conn:
        conn.exec_driver_sql(
            "INSERT INTO workspaces (id, name, timezone, settings, created_at, updated_at, "
            "version) VALUES ('ws_1', 'x', 'UTC', '{}', 't', 't', 1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO context_items (id, workspace_id, scope_kind, kind, title, body, "
            "shadow_status, labels, revision, provenance, created_by, created_at, updated_at, "
            "version) VALUES ('ctx_1', 'ws_1', 'workspace', 'note', 'Kept', 'Body', 'none', "
            "'[]', 1, '{}', 'act_1', 't', 't', 1)"
        )
    report = migrate.upgrade(db, backup_dir=str(tmp_path / "backups"))
    assert report.before == "0001" and report.after == migrate.head_revision(db)
    assert report.backup and os.path.exists(report.backup)
    with db.read() as conn:
        row = conn.exec_driver_sql("SELECT title, body, memory_state FROM context_items").one()
        assert tuple(row) == ("Kept", "Body", None)
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
    db.close()
