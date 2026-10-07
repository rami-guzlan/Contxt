"""todo subject

A to-do can be about one thing: a Brain entry to update. It is done when that entry is
updated (an approved change, an edit, or a restore).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-05 23:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("subject_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("subject_id", sa.String(length=200), nullable=True))
        batch_op.create_index("ix_todos_subject", ["subject_type", "subject_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.drop_index("ix_todos_subject")
        batch_op.drop_column("subject_id")
        batch_op.drop_column("subject_type")
