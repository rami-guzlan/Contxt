# 3. SQLite by default, PostgreSQL compatible, files by content hash

Date: 2026-09-28. Status: accepted.

## Decision

- **SQLite in WAL mode** is the default database, in the data directory. Write transactions
  begin with `BEGIN IMMEDIATE`, so the API server and the worker serialize writes instead of
  failing a lock upgrade; reads use deferred transactions and never block writers.
- **PostgreSQL** works through `CONTXT_DATABASE_URL` with the same tables. Every contested
  write is a conditional `UPDATE ... WHERE version = :seen`, atomic on both backends.
- **Timestamps are UTC ISO 8601 text** of fixed width, so ordering and comparison behave
  identically everywhere; ids are typed ULIDs (`task_01J...`), which sort by creation time.
- **Migrations are Alembic revisions applied automatically on startup.** An existing SQLite
  database is copied with the SQLite backup API before pending revisions run. A test fails
  if the migrations and `schema.py` disagree.
- **File bytes live in a content-addressed store** (`objects/<sha256>`): written once,
  immutable, shared by every item or version that refers to them.
- **Backups are plain zips**: a manifest, one JSON Lines file per table, the objects, and
  optionally the Brain vault. Rows are backend-neutral, so a backup moves between SQLite and
  PostgreSQL.

## Consequences

A fresh install needs no database server. Full-text search starts as portable lexical
matching behind the services; SQLite FTS5 or PostgreSQL text search can replace it without
changing callers.
