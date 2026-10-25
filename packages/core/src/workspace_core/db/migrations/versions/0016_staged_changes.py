"""staged changes

Heartbeat learning's staging buffer: every change a beat read, with its old and new value, its
relevance to the owner's goal and what the filters said, then what the distill made of it.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-25 18:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staged_changes",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("connector_id", sa.String(length=240), nullable=False),
        sa.Column("item_id", sa.String(length=400), nullable=False),
        sa.Column("field", sa.String(length=120), server_default="text", nullable=False),
        sa.Column("title", sa.Text(), server_default="", nullable=False),
        sa.Column("url", sa.Text(), server_default="", nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.String(length=32), nullable=True),
        sa.Column("seen_at", sa.String(length=32), nullable=False),
        sa.Column("beat_id", sa.String(length=40), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("filter", sa.Text(), server_default="", nullable=False),
        sa.Column("unclear", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.JSON(), nullable=True),
        sa.Column("proposal_id", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_staged_changes_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staged_changes")),
    )
    for column in ("connector_id", "seen_at", "status"):
        op.create_index(op.f(f"ix_staged_changes_{column}"), "staged_changes", [column])


def downgrade() -> None:
    for column in ("status", "seen_at", "connector_id"):
        op.drop_index(op.f(f"ix_staged_changes_{column}"), table_name="staged_changes")
    op.drop_table("staged_changes")
