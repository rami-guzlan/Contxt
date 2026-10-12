"""goal boards

Each goal's strategy board (and a project's optional one): the blocks, the columns, what your
AIs can read, and the suggestions that wait for it.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-10 18:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goal_boards",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("goal_id", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="goal", nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_goal_boards_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goal_boards")),
    )
    op.create_index(op.f("ix_goal_boards_goal_id"), "goal_boards", ["goal_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_goal_boards_goal_id"), table_name="goal_boards")
    op.drop_table("goal_boards")
