"""Generate the next migration from changes to `schema.py`.

    uv run python -m workspace_core.db.revise "add task labels"

Builds a scratch database at the current head, compares it with the declared schema, and
writes `migrations/versions/<next>_<message>.py`. Review the file by hand before committing:
autogenerate misses renames and data migrations.
"""

from __future__ import annotations

import os
import sys
import tempfile

from alembic import command

from workspace_core.db import migrate
from workspace_core.db.engine import Database, sqlite_url


def main(argv: list[str] | None = None) -> int:
    message = " ".join(sys.argv[1:] if argv is None else argv).strip()
    if not message:
        print('usage: python -m workspace_core.db.revise "what changed"', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(sqlite_url(os.path.join(tmp, "revise.sqlite")))
        try:
            migrate.upgrade(db)
            head = migrate.head_revision(db)
            number = f"{int(head or 0) + 1:04d}"
            command.revision(migrate.config(db), message=message, autogenerate=True, rev_id=number)
        finally:
            db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
