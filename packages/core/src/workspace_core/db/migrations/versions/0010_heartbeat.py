"""heartbeat

The heartbeat's connectors (names, kinds and read-only tool names, never a credential), its
beats, the lines it wrote into each region, the items each connector has shown, each region's
headline, the writes the owner undid, and one lock per Brain.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-23 12:00:00.000000
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _record() -> list[Any]:
    return [
        sa.Column("created_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    ]


def _workspace(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"], ["workspaces.id"], name=op.f(f"fk_{table}_workspace_id_workspaces")
    )


def upgrade() -> None:
    op.create_table(
        "heartbeat_connectors",
        sa.Column("id", sa.String(length=240), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("cli", sa.String(length=40), nullable=False),
        sa.Column("how", sa.String(length=16), nullable=False),
        sa.Column("cadence_minutes", sa.Integer(), nullable=True),
        sa.Column("feeds", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("last_read_at", sa.String(length=32), nullable=True),
        sa.Column("last_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="off", nullable=False),
        sa.Column("status_line", sa.Text(), server_default="", nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("found_in", sa.String(length=400), server_default="", nullable=False),
        sa.Column("present", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_record(),
        _workspace("heartbeat_connectors"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_connectors")),
    )
    op.create_table(
        "heartbeat_beats",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.String(length=32), nullable=False),
        sa.Column("finished_at", sa.String(length=32), nullable=True),
        sa.Column("connectors", sa.JSON(), nullable=False),
        sa.Column("items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("changes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("waits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("held", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("tokens_unknown", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        *_record(),
        _workspace("heartbeat_beats"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_beats")),
    )
    op.create_index(op.f("ix_heartbeat_beats_status"), "heartbeat_beats", ["status"])
    op.create_index(op.f("ix_heartbeat_beats_started_at"), "heartbeat_beats", ["started_at"])
    op.create_table(
        "heartbeat_lines",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("beat_id", sa.String(length=40), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("project", sa.String(length=200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("connector_id", sa.String(length=240), nullable=False),
        sa.Column("cli", sa.String(length=40), nullable=False),
        sa.Column("item_id", sa.String(length=400), nullable=False),
        sa.Column("item_at", sa.String(length=32), nullable=True),
        sa.Column("wrote", sa.Text(), server_default="", nullable=False),
        sa.Column("write", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("proposal_id", sa.String(length=200), nullable=True),
        sa.Column("checkpoint_id", sa.String(length=200), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), server_default="", nullable=False),
        *_record(),
        _workspace("heartbeat_lines"),
        sa.ForeignKeyConstraint(
            ["beat_id"],
            ["heartbeat_beats.id"],
            name=op.f("fk_heartbeat_lines_beat_id_heartbeat_beats"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_lines")),
    )
    op.create_index(op.f("ix_heartbeat_lines_beat_id"), "heartbeat_lines", ["beat_id"])
    op.create_index(op.f("ix_heartbeat_lines_region"), "heartbeat_lines", ["region"])
    op.create_table(
        "heartbeat_seen",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("connector_id", sa.String(length=240), nullable=False),
        sa.Column("item_id", sa.String(length=400), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("beat_id", sa.String(length=40), nullable=False),
        sa.Column("seen_at", sa.String(length=32), nullable=False),
        _workspace("heartbeat_seen"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_seen")),
        sa.UniqueConstraint(
            "connector_id",
            "item_id",
            "digest",
            name=op.f("uq_heartbeat_seen_connector_id_item_id_digest"),
        ),
    )
    op.create_index(op.f("ix_heartbeat_seen_connector_id"), "heartbeat_seen", ["connector_id"])
    op.create_table(
        "heartbeat_regions",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("headline", sa.Text(), server_default="", nullable=False),
        sa.Column("headline_at", sa.String(length=32), nullable=True),
        sa.Column("projects", sa.JSON(), nullable=False),
        *_record(),
        _workspace("heartbeat_regions"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_regions")),
    )
    op.create_table(
        "heartbeat_suppressions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workspace_id", sa.String(length=40), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("line_id", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        _workspace("heartbeat_suppressions"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_suppressions")),
        sa.UniqueConstraint("fingerprint", name=op.f("uq_heartbeat_suppressions_fingerprint")),
    )
    op.create_table(
        "heartbeat_locks",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("beat_id", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_heartbeat_locks")),
    )


def downgrade() -> None:
    op.drop_table("heartbeat_locks")
    op.drop_table("heartbeat_suppressions")
    op.drop_table("heartbeat_regions")
    op.drop_index(op.f("ix_heartbeat_seen_connector_id"), table_name="heartbeat_seen")
    op.drop_table("heartbeat_seen")
    op.drop_index(op.f("ix_heartbeat_lines_region"), table_name="heartbeat_lines")
    op.drop_index(op.f("ix_heartbeat_lines_beat_id"), table_name="heartbeat_lines")
    op.drop_table("heartbeat_lines")
    op.drop_index(op.f("ix_heartbeat_beats_started_at"), table_name="heartbeat_beats")
    op.drop_index(op.f("ix_heartbeat_beats_status"), table_name="heartbeat_beats")
    op.drop_table("heartbeat_beats")
    op.drop_table("heartbeat_connectors")
