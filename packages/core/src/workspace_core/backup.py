"""One archive with the database, the files and a manifest; and its restore.

The archive is a plain zip anyone can inspect: `manifest.json`, one JSON Lines file per table,
the stored objects under their hashes, and optionally the Brain vault (its runtime cache is
left out). Rows are written in a backend-neutral form, so a SQLite backup restores into
PostgreSQL and back. Restore verifies every object hash and never writes into a workspace that
already has data.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from typing import Any

import sqlalchemy as sa

from workspace_core import __version__
from workspace_core.clock import iso
from workspace_core.db import migrate, schema
from workspace_core.db.engine import Database, sqlite_url
from workspace_core.errors import Conflict
from workspace_core.storage.objects import ObjectStore
from workspace_core.workspace import Workspace

FORMAT = 1
SKIP_DIRS = {".brain", ".git", "__pycache__"}


def _vault_files(root: str) -> list[str]:
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            out.append(os.path.relpath(os.path.join(base, name), root).replace("\\", "/"))
    return sorted(out)


def backup(ws: Workspace, out_path: str, *, brain_vault: str | None = None) -> dict[str, Any]:
    tables: dict[str, int] = {}
    keys = sorted(set(ws.rt.objects.keys()))
    total = 0
    tmp_path = out_path + ".partial"
    revision = migrate.current_revision(ws.rt.db)
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
        # One read transaction: every table comes from the same snapshot.
        with ws.rt.db.read() as conn:
            for table in schema.metadata.sorted_tables:
                rows = [dict(r) for r in conn.execute(sa.select(table)).mappings()]
                tables[table.name] = len(rows)
                lines = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
                archive.writestr(f"tables/{table.name}.jsonl", lines)
        for key in keys:
            data = ws.rt.objects.read(key)
            total += len(data)
            archive.writestr(f"objects/{key[:2]}/{key[2:4]}/{key}", data)
        brain_files = []
        if brain_vault and os.path.isdir(brain_vault):
            brain_files = _vault_files(brain_vault)
            for rel in brain_files:
                archive.write(os.path.join(brain_vault, rel), f"brain/{rel}")
        info = ws.info()
        manifest = {
            "format": FORMAT,
            "created_at": iso(ws.rt.clock.now()),
            "app": {"name": "contxt", "core_version": __version__},
            "schema_revision": revision,
            "workspace": {"id": info.id, "name": info.name, "timezone": info.timezone},
            "tables": tables,
            "objects": {"count": len(keys), "bytes": total, "keys": keys},
            "brain": {
                "included": bool(brain_files),
                "source": brain_vault,
                "files": len(brain_files),
            },
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    os.replace(tmp_path, out_path)
    return manifest


def restore(
    archive_path: str,
    data_dir: str,
    *,
    database_url: str | None = None,
    brain_dir: str | None = None,
) -> dict[str, Any]:
    data_dir = os.path.abspath(data_dir)
    db_path = os.path.join(data_dir, "workspace.sqlite")
    if database_url is None and os.path.exists(db_path):
        raise Conflict(f"{data_dir} already holds a workspace; restore into an empty folder.")
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != FORMAT:
            raise Conflict(f"Unsupported backup format {manifest.get('format')}.")
        for key in manifest["objects"]["keys"]:
            data = archive.read(f"objects/{key[:2]}/{key[2:4]}/{key}")
            if hashlib.sha256(data).hexdigest() != key:
                raise Conflict(
                    f"Object {key} in the archive does not match its hash; the "
                    "archive is damaged or was changed."
                )
        os.makedirs(data_dir, exist_ok=True)
        db = Database(database_url or sqlite_url(db_path))
        try:
            migrate.upgrade(db)
            with db.read() as conn:
                existing = conn.execute(
                    sa.select(sa.func.count()).select_from(schema.workspaces)
                ).scalar()
            if existing:
                raise Conflict("The target database already holds a workspace.")
            counts: dict[str, int] = {}
            with db.write() as conn:
                deferred: list[tuple[str, str]] = []
                for table in schema.metadata.sorted_tables:
                    name = f"tables/{table.name}.jsonl"
                    rows = (
                        [
                            json.loads(line)
                            for line in archive.read(name).decode("utf-8").splitlines()
                            if line.strip()
                        ]
                        if name in archive.namelist()
                        else []
                    )
                    columns = set(table.c.keys())
                    for row in rows:
                        unknown = set(row) - columns
                        if unknown:
                            raise Conflict(
                                f"{table.name} has columns this version does not "
                                f"know: {sorted(unknown)}. Upgrade first."
                            )
                        if table.name == "tasks" and row.get("depends_on"):
                            deferred.append((row["id"], row["depends_on"]))
                            row = dict(row, depends_on=None)
                        conn.execute(table.insert().values(**row))
                    counts[table.name] = len(rows)
                for task_id, depends_on in deferred:
                    conn.execute(
                        schema.tasks.update()
                        .where(schema.tasks.c.id == task_id)
                        .values(depends_on=depends_on)
                    )
        finally:
            db.close()
        store = ObjectStore(os.path.join(data_dir, "objects"))
        for key in manifest["objects"]["keys"]:
            store.put(archive.read(f"objects/{key[:2]}/{key[2:4]}/{key}"))
        restored_brain = 0
        if brain_dir and manifest.get("brain", {}).get("included"):
            for info in archive.infolist():
                if info.filename.startswith("brain/") and not info.is_dir():
                    rel = info.filename[len("brain/") :]
                    target = os.path.abspath(os.path.join(brain_dir, rel))
                    if not target.startswith(os.path.abspath(brain_dir) + os.sep):
                        raise Conflict(f"Unsafe path in archive: {info.filename}")
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as handle:
                        handle.write(archive.read(info.filename))
                    restored_brain += 1
    return {
        "tables": counts,
        "objects": len(manifest["objects"]["keys"]),
        "brain_files": restored_brain,
        "manifest": manifest,
    }
