"""project memory

Working-context items of kind "memory" hold what one project has settled; a model suggests
them and a person keeps them. `memory_state` says which: suggested or kept.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29 15:28:08.848921
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("context_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("memory_state", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("context_items", schema=None) as batch_op:
        batch_op.drop_column("memory_state")
