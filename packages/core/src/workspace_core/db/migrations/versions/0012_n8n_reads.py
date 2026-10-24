"""n8n reads

A connector the heartbeat reads through an n8n workflow: the workflow as approved, its id in
n8n and the hash of the secret it posts with; and the inbox of what workflows posted, waiting
for the next beat.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-24 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("workflow", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("workflow_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("secret_hash", sa.String(length=64), nullable=True))
    op.create_table(
        "heartbeat_inbox",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("connector_id", sa.String(length=240), nullable=False),
        sa.Column("item", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.String(length=32), nullable=False),
        sa.Column("beat_id", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_heartbeat_inbox_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_inbox")),
    )
    op.create_index(op.f("ix_heartbeat_inbox_connector_id"), "heartbeat_inbox", ["connector_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_heartbeat_inbox_connector_id"), table_name="heartbeat_inbox")
    op.drop_table("heartbeat_inbox")
    with op.batch_alter_table("heartbeat_connectors", schema=None) as batch_op:
        batch_op.drop_column("secret_hash")
        batch_op.drop_column("workflow_id")
        batch_op.drop_column("workflow")
