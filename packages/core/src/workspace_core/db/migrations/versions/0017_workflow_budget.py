"""workflow budget

A workflow's budget for a whole run (Release 1 plan, section 11): at most this many tokens and
this much cost. Each step's own budget is kept with the step.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-26 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflows") as batch:
        batch.add_column(sa.Column("budget", sa.JSON(), server_default="{}", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("workflows") as batch:
        batch.drop_column("budget")
