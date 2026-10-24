"""orchestrators

A project's agent orchestrators, their runs (agents, trail, gates, final output) and each one's
auto Context sheet.

Revision ID: 0011
Revises: 0009
Create Date: 2026-10-23 12:00:00.000000
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _record() -> list[sa.Column[Any]]:
    return [
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "orchestrators",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("goal", sa.Text(), server_default="", nullable=False),
        sa.Column("cli", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=60), server_default="", nullable=False),
        sa.Column("trigger", sa.String(length=16), server_default="gnomon", nullable=False),
        sa.Column("sheet", sa.String(length=160), nullable=False),
        sa.Column("agents", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        *_record(),
        sa.Column("archived_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_orchestrators_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_orchestrators_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orchestrators")),
        sa.UniqueConstraint("project_id", "slug", name=op.f("uq_orchestrators_project_id_slug")),
    )
    op.create_index(
        op.f("ix_orchestrators_project_id"), "orchestrators", ["project_id"], unique=False
    )
    op.create_table(
        "orchestrator_runs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("orchestrator_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("asked_by", sa.String(length=120), server_default="", nullable=False),
        sa.Column("steer", sa.Text(), server_default="", nullable=False),
        sa.Column("task_id", sa.String(length=40), nullable=True),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("agents", sa.JSON(), nullable=False),
        sa.Column("trail", sa.JSON(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=False),
        sa.Column("final", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("started_at", sa.String(length=32), nullable=False),
        sa.Column("finished_at", sa.String(length=32), nullable=True),
        *_record(),
        sa.ForeignKeyConstraint(
            ["orchestrator_id"],
            ["orchestrators.id"],
            name=op.f("fk_orchestrator_runs_orchestrator_id_orchestrators"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_orchestrator_runs_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_orchestrator_runs_task_id_tasks")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_orchestrator_runs_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orchestrator_runs")),
    )
    for column in ("orchestrator_id", "project_id", "status"):
        op.create_index(
            op.f(f"ix_orchestrator_runs_{column}"), "orchestrator_runs", [column], unique=False
        )
    op.create_table(
        "orchestrator_cells",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("orchestrator_id", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.String(length=40), nullable=False),
        sa.Column("what", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=300), nullable=False),
        sa.Column("agent", sa.String(length=120), nullable=False),
        *_record(),
        sa.ForeignKeyConstraint(
            ["orchestrator_id"],
            ["orchestrators.id"],
            name=op.f("fk_orchestrator_cells_orchestrator_id_orchestrators"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["orchestrator_runs.id"],
            name=op.f("fk_orchestrator_cells_run_id_orchestrator_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_orchestrator_cells_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orchestrator_cells")),
        sa.UniqueConstraint(
            "orchestrator_id", "what", name=op.f("uq_orchestrator_cells_orchestrator_id_what")
        ),
    )
    op.create_index(
        op.f("ix_orchestrator_cells_orchestrator_id"),
        "orchestrator_cells",
        ["orchestrator_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_orchestrator_cells_orchestrator_id"), table_name="orchestrator_cells")
    op.drop_table("orchestrator_cells")
    for column in ("orchestrator_id", "project_id", "status"):
        op.drop_index(op.f(f"ix_orchestrator_runs_{column}"), table_name="orchestrator_runs")
    op.drop_table("orchestrator_runs")
    op.drop_index(op.f("ix_orchestrators_project_id"), table_name="orchestrators")
    op.drop_table("orchestrators")
