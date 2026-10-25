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

# Work's workflows: steps run as one thing, on a schedule, by a button or from any AI
# (services/workflows.py). A workflow names a project the Brain follows by its id there (a plain
# reference: the Brain's projects are not rows here).
workflows = sa.Table(
    "workflows",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("description", sa.Text, nullable=False, server_default=""),
    sa.Column("project", sa.String(200), index=True),
    sa.Column("trigger", sa.JSON, nullable=False),  # {"schedule": a Schedule, "ai": bool}
    sa.Column("steps", sa.JSON, nullable=False),
    sa.Column("runner", sa.String(40), nullable=False, server_default="claude"),
    sa.Column("output", sa.JSON, nullable=False),
    sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
    sa.Column("next_due_at", TS, index=True),
    sa.Column("scope", sa.String(120), nullable=False, server_default=""),
    sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
    *_record(),
)

# One run of a workflow: where it is, and each step's state (its task or job, what it made,
# the versions it read). Runs are kept, never archived.
workflow_runs = sa.Table(
    "workflow_runs",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("workflow_id", ID, sa.ForeignKey("workflows.id"), nullable=False, index=True),
    # running | waiting (a check, or a step blocked) | done | failed | stopped
    sa.Column("status", sa.String(16), nullable=False, index=True),
    sa.Column("trigger", sa.String(16), nullable=False),  # now | schedule | ai
    sa.Column("due_at", TS),
    sa.Column("started_at", TS, nullable=False),
    sa.Column("finished_at", TS),
    sa.Column("step", sa.Integer, nullable=False, server_default="0"),
    sa.Column("steps", sa.JSON, nullable=False),
    sa.Column("revision", sa.Integer, nullable=False),  # the workflow's revision it ran
    sa.Column("request", sa.Text, nullable=False, server_default=""),
    sa.Column("note", sa.Text, nullable=False, server_default=""),
    *_record(archivable=False),
)

# A goal's strategy board, or a project's optional one (services/goals.py): its blocks in order,
# the columns, which blocks are collapsed and which your AIs can read, and the suggestions that
# wait for it (dismissed ones remembered). Presentation only: the goal itself, its journal and
# its shared plan live in the Brain.
goal_boards = sa.Table(
    "goal_boards",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("goal_id", sa.String(200), nullable=False, index=True),
    sa.Column("kind", sa.String(16), nullable=False, server_default="goal"),  # goal | project
    sa.Column("layout", sa.JSON, nullable=False),
    sa.Column("suggestions", sa.JSON, nullable=False),
    *_record(archivable=False),
)

# A project's agent orchestrators (services/orchestrators.py): a goal, the CLI and model it runs
# on, how it starts (from Gnomon, or from a connected AI too) and the agents it spawns, each with
# a profile from Agents, a role, how it works, its own CLI and model, and the connected tools it
# may use. Its slug is how a connected AI names it ("run promo-check").
orchestrators = sa.Table(
    "orchestrators",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False, index=True),
    sa.Column("slug", sa.String(80), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("goal", sa.Text, nullable=False, server_default=""),
    sa.Column("cli", sa.String(20), nullable=False),
    sa.Column("model", sa.String(60), nullable=False, server_default=""),
    sa.Column("trigger", sa.String(16), nullable=False, server_default="gnomon"),  # gnomon | ai
    sa.Column("sheet", sa.String(160), nullable=False),
    sa.Column("agents", sa.JSON, nullable=False),
    sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
    *_record(),
    sa.UniqueConstraint("project_id", "slug"),
)

# One run of an orchestrator: the spec it ran (a copy, so later edits leave it whole), its
# status, the steer, its own task, each agent's state and task, the trail of what the agents
# reported, the gates waiting for the owner's yes, and the final output pinned on top.
orchestrator_runs = sa.Table(
    "orchestrator_runs",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("orchestrator_id", ID, sa.ForeignKey("orchestrators.id"), nullable=False, index=True),
    sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False, index=True),
    sa.Column("status", sa.String(16), nullable=False, index=True),
    sa.Column("trigger", sa.String(16), nullable=False),  # gnomon | ai
    sa.Column("asked_by", sa.String(120), nullable=False, server_default=""),
    sa.Column("steer", sa.Text, nullable=False, server_default=""),
    sa.Column("task_id", ID, sa.ForeignKey("tasks.id")),
    sa.Column("spec", sa.JSON, nullable=False),
    sa.Column("agents", sa.JSON, nullable=False),
    sa.Column("trail", sa.JSON, nullable=False),
    sa.Column("gates", sa.JSON, nullable=False),
    sa.Column("final", sa.JSON),
    sa.Column("note", sa.Text, nullable=False, server_default=""),
    sa.Column("started_at", TS, nullable=False),
    sa.Column("finished_at", TS),
    *_record(archivable=False),
)

# An orchestrator's auto Context sheet: one cell per thing found (What), with its value, its
# source and the agent that found it, as of the run that filled it last.
orchestrator_cells = sa.Table(
    "orchestrator_cells",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("orchestrator_id", ID, sa.ForeignKey("orchestrators.id"), nullable=False, index=True),
    sa.Column("run_id", ID, sa.ForeignKey("orchestrator_runs.id"), nullable=False),
    sa.Column("what", sa.String(200), nullable=False),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("source", sa.String(300), nullable=False),
    sa.Column("agent", sa.String(120), nullable=False),
    *_record(archivable=False),
    sa.UniqueConstraint("orchestrator_id", "what"),
)

# The heartbeat (apps/server heartbeat): the connectors it reads, read-only, through the CLIs on
# this computer. Only names, kinds and the read-only tool names are kept: never a credential,
# an environment value or a token from the CLI's own configuration.
heartbeat_connectors = sa.Table(
    "heartbeat_connectors",
    metadata,
    sa.Column("id", sa.String(240), primary_key=True),  # <cli>:<server name>, or scout
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("cli", sa.String(40), nullable=False),  # claude | codex | gnomon
    sa.Column("how", sa.String(16), nullable=False),  # mcp | computer | folder | n8n | memory
    sa.Column("cadence_minutes", sa.Integer),  # its own, when slower than the heartbeat's
    sa.Column("feeds", sa.JSON, nullable=False),  # region ids
    sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("cursor", sa.Text),
    sa.Column("last_read_at", TS),
    sa.Column("last_items", sa.Integer, nullable=False, server_default="0"),
    # ok | off | unhealthy_sign_in | provider_limit | cannot_confirm_read_only | error
    sa.Column("status", sa.String(32), nullable=False, server_default="off"),
    sa.Column("status_line", sa.Text, nullable=False, server_default=""),
    sa.Column("tools", sa.JSON, nullable=False),  # the read-only tools, by name
    sa.Column("found_in", sa.String(400), nullable=False, server_default=""),
    sa.Column("present", sa.Boolean, nullable=False, server_default=sa.true()),
    # An n8n read: the workflow as approved (checked read-only), its id in n8n, and the hash
    # of the secret it sends with what it posts (never the secret itself).
    sa.Column("workflow", sa.JSON),
    sa.Column("workflow_id", sa.String(64)),
    sa.Column("secret_hash", sa.String(64)),
    # A fix the knowledge agent suggested after its workflow failed: {workflow, why}, waiting
    # for the owner to keep or skip it.
    sa.Column("workflow_fix", sa.JSON),
    # A memory read (how "memory"): what the owner asked it to look for, in their words.
    sa.Column("ask", sa.Text),
    *_record(archivable=False),
)

# What n8n workflows posted, waiting for the next beat: it reads them like any read (a beat
# that takes them marks them with its id; a beat that stopped leaves them for the next).
heartbeat_inbox = sa.Table(
    "heartbeat_inbox",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("connector_id", sa.String(240), nullable=False, index=True),
    sa.Column("item", sa.JSON, nullable=False),
    sa.Column("received_at", TS, nullable=False),
    sa.Column("beat_id", ID),
)

# One beat: what it read, what it changed, what waits and what it held back, and what it used.
heartbeat_beats = sa.Table(
    "heartbeat_beats",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("status", sa.String(16), nullable=False, index=True),  # running | done | failed
    sa.Column("trigger", sa.String(16), nullable=False),  # now | schedule | ai
    sa.Column("started_at", TS, nullable=False, index=True),
    sa.Column("finished_at", TS),
    sa.Column("connectors", sa.JSON, nullable=False),  # [{id, name, items, status}]
    sa.Column("items", sa.Integer, nullable=False, server_default="0"),
    sa.Column("changes", sa.Integer, nullable=False, server_default="0"),
    sa.Column("waits", sa.Integer, nullable=False, server_default="0"),
    sa.Column("held", sa.Integer, nullable=False, server_default="0"),
    sa.Column("tokens", sa.Integer),  # None: no CLI said what it used
    sa.Column("tokens_unknown", sa.Integer, nullable=False, server_default="0"),
    sa.Column("duration_ms", sa.Integer),
    sa.Column("errors", sa.JSON, nullable=False),
    sa.Column("details", sa.JSON, nullable=False),  # plain lines: what it did
    *_record(archivable=False),
)

# What a beat wrote into a region: one line per write (or per item it only noted), with its
# source, the write and the proposal or undo point that holds it.
heartbeat_lines = sa.Table(
    "heartbeat_lines",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("beat_id", ID, sa.ForeignKey("heartbeat_beats.id"), nullable=False, index=True),
    sa.Column("region", sa.String(120), nullable=False, index=True),
    sa.Column("project", sa.String(200)),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("connector_id", sa.String(240), nullable=False),
    sa.Column("cli", sa.String(40), nullable=False),
    sa.Column("item_id", sa.String(400), nullable=False),  # connector:<id>:<item id>
    sa.Column("item_at", TS),
    sa.Column("wrote", sa.Text, nullable=False, server_default=""),
    sa.Column("write", sa.JSON, nullable=False),
    sa.Column("reason", sa.Text, nullable=False, server_default=""),
    # noted | applied | waiting | held | refused | undone
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("proposal_id", sa.String(200)),
    sa.Column("checkpoint_id", sa.String(200)),
    sa.Column("fingerprint", sa.String(64), nullable=False, server_default=""),
    *_record(archivable=False),
)

# The items each connector has shown, by id and content: the same item twice is not new.
heartbeat_seen = sa.Table(
    "heartbeat_seen",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("connector_id", sa.String(240), nullable=False, index=True),
    sa.Column("item_id", sa.String(400), nullable=False),
    sa.Column("digest", sa.String(64), nullable=False),
    sa.Column("beat_id", ID, nullable=False),
    sa.Column("seen_at", TS, nullable=False),
    sa.UniqueConstraint("connector_id", "item_id", "digest"),
)

# Each region's live headline and its projects' status lines.
heartbeat_regions = sa.Table(
    "heartbeat_regions",
    metadata,
    sa.Column("id", sa.String(120), primary_key=True),  # the Brain area's id
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("headline", sa.Text, nullable=False, server_default=""),
    sa.Column("headline_at", TS),
    sa.Column("projects", sa.JSON, nullable=False),  # {project id: {status, at}}
    *_record(archivable=False),
)

# Writes the owner undid: the next beat does not make them again.
heartbeat_suppressions = sa.Table(
    "heartbeat_suppressions",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
    sa.Column("line_id", ID, nullable=False),
    sa.Column("created_at", TS, nullable=False),
)

# One beat at a time per Brain: the holder and when its hold runs out (a stale lock expires).
heartbeat_locks = sa.Table(
    "heartbeat_locks",
    metadata,
    _id(),  # the workspace's id: one Brain each
    sa.Column("beat_id", ID, nullable=False),
    sa.Column("expires_at", TS, nullable=False),
)

# The Test Bench (Release 1 plan, 15.5): each answer a bench run got, one row per panel, with
# what it used and what it was built from; and its scores, by the grader and by the person.
bench_runs = sa.Table(
    "bench_runs",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("batch", ID, nullable=False),  # the bench run or suite run it was part of
    sa.Column("suite", sa.String(64)),  # with `test`, the saved test it answered
    sa.Column("test", sa.String(64)),
    sa.Column("request", sa.Text, nullable=False),
    sa.Column("project", sa.String(200)),
    sa.Column("mode", sa.String(16), nullable=False),  # none | full | custom
    sa.Column("included", sa.JSON, nullable=False),  # custom's include and exclude (ids)
    sa.Column("sections", sa.JSON, nullable=False),  # the packet sections it was sent
    sa.Column("runner", sa.String(40), nullable=False),
    sa.Column("model", sa.String(120)),
    sa.Column("tokens_in", sa.Integer),
    sa.Column("tokens_out", sa.Integer),
    sa.Column("cost", sa.Float),
    sa.Column("ms", sa.Integer),
    sa.Column("measured", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("brain_version", sa.String(40), nullable=False, server_default=""),
    sa.Column("packet_hash", sa.String(64), nullable=False, server_default=""),
    sa.Column("output", sa.Text, nullable=False, server_default=""),
    sa.Column("error", sa.Text),
    sa.Column("grade_error", sa.Text),  # why the grader gave no score
    sa.Column("created_at", TS, nullable=False),
    sa.Index("ix_bench_runs_batch", "batch"),
)

bench_scores = sa.Table(
    "bench_scores",
    metadata,
    _id(),
    sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("run_id", ID, sa.ForeignKey("bench_runs.id"), nullable=False),
    sa.Column("by", sa.String(16), nullable=False),  # model | human
    sa.Column("overall", sa.Integer, nullable=False),  # 1 to 5
    sa.Column("criteria", sa.JSON, nullable=False),  # [{criterion, result: met|part|missed}]
    sa.Column("reason", sa.Text, nullable=False, server_default=""),
    sa.Column("thumbs", sa.String(8)),  # up | down, from a person
    sa.Column("edits", sa.String(8)),  # none | light | heavy, from a person
    sa.Column("note", sa.Text, nullable=False, server_default=""),
    sa.Column("grader", sa.String(120)),  # the model that graded
    sa.Column("created_at", TS, nullable=False),
    sa.Index("ix_bench_scores_run", "run_id"),
)
