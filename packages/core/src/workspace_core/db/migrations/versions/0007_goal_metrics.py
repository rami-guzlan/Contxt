"""goal metrics

A goal can be measured by numbers: each reads a sheet's column (a total over the rows that
pass a filter) or is typed by hand, and has a target. Kept as JSON on the goal.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06 02:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A plain ADD COLUMN, so it previews offline; null reads as no numbers.
    op.add_column("goals", sa.Column("metrics", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("goals", schema=None) as batch_op:
        batch_op.drop_column("metrics")
