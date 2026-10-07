# workspace-core

The domain model and application services of the workspace, with no web framework, no model
provider and no Brain implementation inside. Adapters (the REST API, the MCP endpoint, the CLI,
the worker) call one facade, `Workspace`, and nothing else.

```
ids.py, clock.py, errors.py     typed ids, injectable time, the error vocabulary
domain/                         records, state machines, schedules, permissions, artifact types
db/                             SQLAlchemy tables, SQLite/Postgres engines, Alembic migrations
storage/                        content-addressed file store
services/                       the application layer: one module per aggregate
ports.py                        what the core needs from outside (the Brain, text extraction)
workspace.py                    the facade adapters use
```

Rules the code keeps:

1. Every state change is one transaction that also appends its domain event.
2. Only the transitions in `domain/states.py` are possible, whoever asks.
3. Every mutable row carries a version; a write against a stale version is refused.
4. The acting identity always comes from the authenticated credential, never a parameter.
5. Consequential writes accept an idempotency key; a retry returns the first result.
