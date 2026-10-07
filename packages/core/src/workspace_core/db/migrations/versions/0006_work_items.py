"""work items

Docs, sheets and canvases are working-context items. Their versions can carry a name and be
sealed (an AI edit, a restore or a named version closes a version to the saves after it), and
a model's proposed change waits in `work_suggestions` for a person to accept or discard.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06 01:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ALTER TABLE ADD COLUMN on every backend: no table rebuild, so it also previews
    # offline (the SQL preview before a migration runs).
    op.add_column(
        "context_item_revisions", sa.Column("label", sa.String(length=300), nullable=True)
    )
    op.add_column(
        "context_item_revisions",
        sa.Column("sealed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "work_suggestions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("item_id", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.String(length=40), nullable=True),
        sa.Column("actor_id", sa.String(length=40), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("decided_by", sa.String(length=40), nullable=True),
        sa.Column("decided_at", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["actors.id"], name=op.f("fk_work_suggestions_actor_id_actors")
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["context_items.id"],
            name=op.f("fk_work_suggestions_item_id_context_items"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_work_suggestions_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_suggestions")),
    )
    op.create_index(
        op.f("ix_work_suggestions_item_id"), "work_suggestions", ["item_id"], unique=False
    )
    op.create_index(
        op.f("ix_work_suggestions_run_id"), "work_suggestions", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_work_suggestions_status"), "work_suggestions", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_work_suggestions_status"), table_name="work_suggestions")
    op.drop_index(op.f("ix_work_suggestions_run_id"), table_name="work_suggestions")
    op.drop_index(op.f("ix_work_suggestions_item_id"), table_name="work_suggestions")
    op.drop_table("work_suggestions")

    with op.batch_alter_table("context_item_revisions", schema=None) as batch_op:
        batch_op.drop_column("sealed")
        batch_op.drop_column("label")
