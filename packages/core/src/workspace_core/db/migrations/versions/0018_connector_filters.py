"""connector filters

What the owner wants a connector's read to leave out: words, comma separated. An item whose
title or text names one is not kept. What to look for (`ask`) now applies to any read.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28 09:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("skip", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.drop_column("skip")
