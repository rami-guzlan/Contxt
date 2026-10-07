# 1. One repository, a Python backend and a TypeScript web app

Date: 2026-09-28. Status: accepted.

## Context

The specification asks for one repository that is the product (`git clone`, `cp .env.example
.env`, `docker compose up -d`) with `apps/web`, `apps/server`, `packages/core`,
`packages/connectors`, `packages/brain`, templates, Docker profiles, scripts and docs. It
leaves the exact frameworks open. The Brain engine that becomes `packages/brain` already exists
in Python, standard library only, with optional local embeddings.

## Decision

- **Backend in Python 3.12+**: FastAPI for the REST API (OpenAPI for free), SQLAlchemy 2 Core
  for SQL that runs on SQLite and PostgreSQL, Alembic for versioned migrations. The core keeps
  its dependencies to SQLAlchemy, Alembic and tzdata.
- **Web app in TypeScript**: React with Vite, tested with Vitest and Testing Library.
- **Tooling**: a uv workspace for the Python packages (one lockfile), npm workspaces for the
  web app, ruff for lint and format, mypy for types, pytest for tests, GitHub Actions for CI.

## Consequences

The Brain is imported in-process, with no service boundary to maintain. Contributors need
both uv and Node. AI and data tooling, which is mostly Python, plugs in without a bridge.
