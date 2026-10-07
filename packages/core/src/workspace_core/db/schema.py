"""The relational schema. SQLite by default; the same tables run on PostgreSQL.

Conventions:
- ids are typed ULIDs (`task_01J...`), text;
- timestamps are UTC ISO 8601 text with fixed width, so comparisons and ordering work the same
  on every backend;
- every mutable record has `version` (optimistic concurrency), `created_by`, `created_at`,
  `updated_at` and, where it can be archived, `archived_at`;
- events are append-only and ordered by `seq`.

Change this file only together with a new Alembic revision in `migrations/versions/`.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

metadata = sa.MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

ID = sa.String(40)
TS = sa.String(32)


def _id() -> sa.Column[str]:
    return sa.Column("id", ID, primary_key=True)


def _record(*, archivable: bool = True) -> list[sa.Column[Any]]:
    columns: list[sa.Column[Any]] = [
        sa.Column("created_by", ID, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    ]
    if archivable:
        columns.append(sa.Column("archived_at", TS))
    return columns


workspaces = sa.Table(
    "workspaces",
    metadata,
    _id(),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
    sa.Column("settings", sa.JSON, nullable=False),
    sa.Column("created_at", TS, nullable=False),
    sa.Column("updated_at", TS, nullable=False),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
)

actors = sa.Table(
    "actors",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("kind", sa.String(16), nullable=False),  # human | model | system
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("provider", sa.String(64)),  # claude-code, chatgpt, codex, ollama, ...
    sa.Column("description", sa.Text),
    sa.Column("last_seen_at", TS),
    sa.Column("disabled_at", TS),
    sa.Column("created_at", TS, nullable=False),
    sa.Column("updated_at", TS, nullable=False),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
)

credentials = sa.Table(
    "credentials",
    metadata,
    _id(),
    sa.Column("actor_id", ID, sa.ForeignKey("actors.id"), nullable=False, index=True),
    sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
    sa.Column("token_hint", sa.String(16), nullable=False),
    sa.Column("label", sa.String(200)),
    sa.Column("actions", sa.JSON, nullable=False),
    sa.Column("projects", sa.JSON),  # null: every project
    sa.Column("created_by", ID, nullable=False),
    sa.Column("created_at", TS, nullable=False),
    sa.Column("last_used_at", TS),
    sa.Column("revoked_at", TS),
)

goals = sa.Table(
    "goals",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("outcome", sa.Text, nullable=False, server_default=""),
    sa.Column("why", sa.Text, nullable=False, server_default=""),  # why it matters
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("target_date", sa.String(10)),
    sa.Column("provenance", sa.JSON, nullable=False),
    sa.Column("metrics", sa.JSON),  # the numbers that measure it; null reads as none
    *_record(),
)

projects = sa.Table(
    "projects",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("goal_id", ID, sa.ForeignKey("goals.id"), index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("summary", sa.Text, nullable=False, server_default=""),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("brain_ref", sa.String(200)),  # the Brain's matching project (Focus) note
    sa.Column("provenance", sa.JSON, nullable=False),
    *_record(),
)

tasks = sa.Table(
    "tasks",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("project_id", ID, sa.ForeignKey("projects.id"), index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("purpose", sa.Text, nullable=False, server_default=""),
    sa.Column("instructions", sa.Text, nullable=False, server_default=""),
    sa.Column("prompt_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("assignee_id", ID, sa.ForeignKey("actors.id"), index=True),
    sa.Column("schedule", sa.JSON, nullable=False),
    sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
    sa.Column("next_due_at", TS, index=True),
    sa.Column("output_contract", sa.JSON, nullable=False),
    sa.Column("review_policy", sa.String(16), nullable=False, server_default="required"),
    sa.Column("brain_request", sa.Text),  # optional wording for the Brain query
    sa.Column("status", sa.String(16), nullable=False, index=True),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("depends_on", ID, sa.ForeignKey("tasks.id")),
    sa.Column("template", sa.String(100)),
    sa.Column("current_run_id", ID),
    sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
    sa.Column("provenance", sa.JSON, nullable=False),
    *_record(),
)

task_revisions = sa.Table(
    "task_revisions",
    metadata,
    sa.Column("task_id", ID, sa.ForeignKey("tasks.id"), primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("definition", sa.JSON, nullable=False),
    sa.Column("created_by", ID, nullable=False),
    sa.Column("created_at", TS, nullable=False),
)

task_pins = sa.Table(
    "task_pins",
    metadata,
    _id(),
    sa.Column("task_id", ID, sa.ForeignKey("tasks.id"), nullable=False, index=True),
    # context_item | artifact | brain_entry | brain_project | brain_file
    sa.Column("ref_type", sa.String(32), nullable=False),
    sa.Column("ref_id", sa.String(200), nullable=False),
    sa.Column("pinned_version", sa.Integer),  # null: the latest version when a run starts
    sa.Column("note", sa.Text),
    sa.Column("created_by", ID, nullable=False),
    sa.Column("created_at", TS, nullable=False),
    sa.UniqueConstraint("task_id", "ref_type", "ref_id"),
)

task_runs = sa.Table(
    "task_runs",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("task_id", ID, sa.ForeignKey("tasks.id"), nullable=False, index=True),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("occurrence", sa.String(64), nullable=False),  # due time, or "manual"
    sa.Column("status", sa.String(16), nullable=False, index=True),
    sa.Column("actor_id", ID, sa.ForeignKey("actors.id"), nullable=False, index=True),
    sa.Column("task_revision", sa.Integer, nullable=False),
    sa.Column("claimed_at", TS, nullable=False),
    sa.Column("lease_expires_at", TS, nullable=False),
    sa.Column("started_at", TS),
    sa.Column("finished_at", TS),
    sa.Column("packet", sa.JSON, nullable=False),
    sa.Column("outcome", sa.JSON, nullable=False),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
)

context_items = sa.Table(
    "context_items",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("scope_kind", sa.String(16), nullable=False),
    sa.Column("scope_id", sa.String(40)),
    sa.Column("kind", sa.String(16), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("body", sa.Text, nullable=False, server_default=""),
    sa.Column("url", sa.Text),
    sa.Column("object_key", sa.String(100)),
    sa.Column("filename", sa.String(300)),
    sa.Column("mime", sa.String(200)),
    sa.Column("size", sa.Integer),
    sa.Column("content_hash", sa.String(64), index=True),
    sa.Column("text_shadow", sa.Text),
    sa.Column("shadow_status", sa.String(16), nullable=False, server_default="none"),
    sa.Column("idea_state", sa.String(16)),
    sa.Column("memory_state", sa.String(16)),  # project memory: suggested | kept
    sa.Column("labels", sa.JSON, nullable=False),
    sa.Column("source_label", sa.String(200)),
    sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
    sa.Column("last_referenced_at", TS),
    sa.Column("provenance", sa.JSON, nullable=False),
    *_record(),
    sa.Index("ix_context_items_scope", "scope_kind", "scope_id"),
)

context_item_revisions = sa.Table(
    "context_item_revisions",
    metadata,
    sa.Column("item_id", ID, sa.ForeignKey("context_items.id"), primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("object_key", sa.String(100)),
    sa.Column("content_hash", sa.String(64)),
    sa.Column("created_by", ID, nullable=False),
    sa.Column("created_at", TS, nullable=False),
    # A doc's, sheet's or canvas's version: its name ("Sent to Sam", "AI: tightened"), and
    # whether it is closed to the saves that follow (an AI edit, a restore, a named version).
    sa.Column("label", sa.String(300)),
    sa.Column("sealed", sa.Boolean, nullable=False, server_default=sa.false()),
)

# A change a model proposes to a doc, sheet or canvas, waiting for a person to accept it (a
# version by that model) or discard it.
work_suggestions = sa.Table(
    "work_suggestions",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("item_id", ID, sa.ForeignKey("context_items.id"), nullable=False, index=True),
    sa.Column("run_id", ID, index=True),  # the AI panel request's run, when it came from one
    sa.Column("actor_id", ID, sa.ForeignKey("actors.id"), nullable=False),
    sa.Column("base_revision", sa.Integer, nullable=False),  # the version it was made from
    sa.Column("title", sa.String(300)),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("note", sa.Text, nullable=False, server_default=""),
    sa.Column("status", sa.String(16), nullable=False, index=True),  # pending|accepted|discarded
    sa.Column("created_at", TS, nullable=False),
    sa.Column("decided_by", ID),
    sa.Column("decided_at", TS),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
)

meetings = sa.Table(
    "meetings",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("held_on", sa.String(10), index=True),  # the day it was held, YYYY-MM-DD
    sa.Column("attendees", sa.JSON, nullable=False),
    sa.Column("project_id", ID, sa.ForeignKey("projects.id"), index=True),  # mostly about
    sa.Column("item_id", ID),  # its transcript: a working-context item in scope meeting:<id>
    sa.Column("summary", sa.Text, nullable=False, server_default=""),
    sa.Column("task_id", ID),  # the latest request to pull its notes
    sa.Column("processed_at", TS),  # when a model last filed its notes
    sa.Column("provenance", sa.JSON, nullable=False),
    *_record(),
)

todos = sa.Table(
    "todos",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("project_id", ID, sa.ForeignKey("projects.id"), index=True),
    sa.Column("meeting_id", ID, sa.ForeignKey("meetings.id"), index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("notes", sa.Text, nullable=False, server_default=""),
    sa.Column("owner", sa.String(200)),  # a name as people say it; not always a workspace user
    sa.Column("due_on", sa.String(10), index=True),
    sa.Column("status", sa.String(16), nullable=False, index=True),  # suggested | open | done
    sa.Column("source_quote", sa.Text),
    sa.Column("completed_at", TS),
    # The AI work doing this to-do, when it was handed to a model ("Ask AI"). A plain
    # reference, like meetings.task_id.
    sa.Column("task_id", ID, index=True),
    # What the to-do is about, when it is about one thing: a Brain entry to update
    # (subject_type "brain_entry"). Plain references; the to-do is done when that entry is.
    sa.Column("subject_type", sa.String(32)),
    sa.Column("subject_id", sa.String(200)),
    sa.Column("provenance", sa.JSON, nullable=False),
    *_record(),  # archived: dismissed (a suggestion) or removed
    sa.Index("ix_todos_subject", "subject_type", "subject_id"),
)

artifacts = sa.Table(
    "artifacts",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("goal_id", ID, sa.ForeignKey("goals.id"), index=True),
    sa.Column("project_id", ID, sa.ForeignKey("projects.id"), index=True),
    sa.Column("task_id", ID, sa.ForeignKey("tasks.id"), index=True),
    sa.Column("run_id", ID, sa.ForeignKey("task_runs.id")),
    sa.Column("type", sa.String(32), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("status", sa.String(16), nullable=False, index=True),
    sa.Column("current_version", sa.Integer, nullable=False, server_default="1"),
    *_record(),
)

artifact_versions = sa.Table(
    "artifact_versions",
    metadata,
    _id(),
    sa.Column("artifact_id", ID, sa.ForeignKey("artifacts.id"), nullable=False, index=True),
    sa.Column("number", sa.Integer, nullable=False),
    sa.Column("object_key", sa.String(100), nullable=False),
    sa.Column("filename", sa.String(300), nullable=False),
    sa.Column("mime", sa.String(200), nullable=False),
    sa.Column("size", sa.Integer, nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("preview_text", sa.Text),
    sa.Column("run_id", ID, sa.ForeignKey("task_runs.id")),
    sa.Column("task_revision", sa.Integer),
    sa.Column("prompt_version", sa.Integer),
    sa.Column("inputs", sa.JSON, nullable=False),  # pinned inputs and their versions
    sa.Column("context_used", sa.JSON, nullable=False),  # what the producer says it used
    sa.Column("note", sa.Text),
    sa.Column("created_by", ID, nullable=False),
    sa.Column("created_at", TS, nullable=False),
    sa.UniqueConstraint("artifact_id", "number"),
)

approvals = sa.Table(
    "approvals",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("subject_type", sa.String(32), nullable=False),  # artifact | task
    sa.Column("subject_id", ID, nullable=False, index=True),
    sa.Column("subject_version", sa.Integer),
    sa.Column("project_id", ID),
    sa.Column("task_id", ID),
    sa.Column("run_id", ID),
    sa.Column("status", sa.String(24), nullable=False, index=True),
    sa.Column("reason", sa.Text, nullable=False, server_default=""),
    sa.Column("requested_by", ID, nullable=False),
    sa.Column("requested_at", TS, nullable=False),
    sa.Column("decided_by", ID),
    sa.Column("decided_at", TS),
    sa.Column("decision_note", sa.Text),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
)

exports = sa.Table(
    "exports",
    metadata,
    _id(),
    sa.Column("artifact_id", ID, sa.ForeignKey("artifacts.id"), nullable=False, index=True),
    sa.Column("artifact_version", sa.Integer, nullable=False),
    sa.Column("destination", sa.String(64), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("result", sa.JSON, nullable=False),
    sa.Column("created_by", ID, nullable=False),
    sa.Column("created_at", TS, nullable=False),
)

events = sa.Table(
    "events",
    metadata,
    sa.Column("seq", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("id", ID, nullable=False, unique=True),
    sa.Column("workspace_id", ID, nullable=False),
    sa.Column("at", TS, nullable=False),
    sa.Column("actor_id", ID, nullable=False, index=True),
    sa.Column("type", sa.String(64), nullable=False, index=True),
    sa.Column("subject_type", sa.String(32), nullable=False),
    sa.Column("subject_id", sa.String(200), nullable=False),
    sa.Column("project_id", ID, index=True),
    sa.Column("reason", sa.Text),
    sa.Column("data", sa.JSON, nullable=False),
    sa.Column("noise", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Index("ix_events_subject", "subject_type", "subject_id"),
    sqlite_autoincrement=True,
)

idempotency_keys = sa.Table(
    "idempotency_keys",
    metadata,
    sa.Column("actor_id", ID, primary_key=True),
    sa.Column("key", sa.String(200), primary_key=True),
    sa.Column("operation", sa.String(64), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result_type", sa.String(32), nullable=False),
    sa.Column("result_id", sa.String(200), nullable=False),
    sa.Column("created_at", TS, nullable=False),
)
