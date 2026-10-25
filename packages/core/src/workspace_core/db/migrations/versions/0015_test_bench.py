"""test bench

The Test Bench's answers, one row per panel with what it used and what it was built from,
and their scores by the grader and by the person (Release 1 plan, 15.5).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-25 23:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _workspace(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"], ["workspaces.id"], name=op.f(f"fk_{table}_workspace_id_workspaces")
    )


def upgrade() -> None:
    op.create_table(
        "bench_runs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("batch", sa.String(length=40), nullable=False),
        sa.Column("suite", sa.String(length=64), nullable=True),
        sa.Column("test", sa.String(length=64), nullable=True),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("project", sa.String(length=200), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("included", sa.JSON(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("runner", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("ms", sa.Integer(), nullable=True),
        sa.Column("measured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("brain_version", sa.String(length=40), server_default="", nullable=False),
        sa.Column("packet_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column("output", sa.Text(), server_default="", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("grade_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        _workspace("bench_runs"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bench_runs")),
    )
    with op.batch_alter_table("bench_runs", schema=None) as batch_op:
        batch_op.create_index("ix_bench_runs_batch", ["batch"], unique=False)
    op.create_table(
        "bench_scores",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.String(length=40), nullable=False),
        sa.Column("by", sa.String(length=16), nullable=False),
        sa.Column("overall", sa.Integer(), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("thumbs", sa.String(length=8), nullable=True),
        sa.Column("edits", sa.String(length=8), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("grader", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        _workspace("bench_scores"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["bench_runs.id"], name=op.f("fk_bench_scores_run_id_bench_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bench_scores")),
    )
    with op.batch_alter_table("bench_scores", schema=None) as batch_op:
        batch_op.create_index("ix_bench_scores_run", ["run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("bench_scores", schema=None) as batch_op:
        batch_op.drop_index("ix_bench_scores_run")
    op.drop_table("bench_scores")
    with op.batch_alter_table("bench_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_bench_runs_batch")
    op.drop_table("bench_runs")
