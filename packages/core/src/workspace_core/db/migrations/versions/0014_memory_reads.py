"""memory reads

What the owner asked a CLI's memory read to look for, in their own words: a read of what
Claude Code, Codex or Gemini CLI keeps on the person (its memory files and recent chats).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-25 20:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ask", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.drop_column("ask")
