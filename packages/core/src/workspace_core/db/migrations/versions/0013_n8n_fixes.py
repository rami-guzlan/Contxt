"""n8n fixes

A fix the knowledge agent suggested for an n8n read whose workflow failed, waiting for the
owner to keep or skip it.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-24 18:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("workflow_fix", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.drop_column("workflow_fix")
