"""goal why and todo work

A goal says why it matters. A to-do can be handed to an AI model: `task_id` is the work doing
it, and the to-do completes when that work is done.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05 20:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("goals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("why", sa.Text(), server_default="", nullable=False))

    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=40), nullable=True))
        batch_op.create_index(batch_op.f("ix_todos_task_id"), ["task_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_todos_task_id"))
        batch_op.drop_column("task_id")

    with op.batch_alter_table("goals", schema=None) as batch_op:
        batch_op.drop_column("why")
