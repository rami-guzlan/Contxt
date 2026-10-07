"""Tasks: complete, versioned work packets, and the human side of their lifecycle.

Every edit of the definition is a new revision with a snapshot; an edit of the instructions
also bumps the prompt version, so every artifact can say which prompt produced it.
"""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso
from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain import artifact_types
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Pin, Run, Task
from workspace_core.domain.schedule import Schedule, zone
from workspace_core.domain.states import RUN, TASK
from workspace_core.errors import NotFound, ValidationFailed

from . import packets
from .actors import actor_can_claim
from .runtime import Runtime

REVIEW_POLICIES = ("required", "auto")
PIN_TYPES = ("context_item", "artifact", "brain_entry", "brain_project", "brain_file")
# The tools a task can name as the way its results come back, instead of artifacts.
RESULT_TOOLS = ("propose_brain_entry", "save_digest", "save_skill_result", "propose_brain_skill")
DEFINITION_FIELDS = (
    "project_id",
    "title",
    "purpose",
    "instructions",
    "prompt_version",
    "assignee_id",
    "schedule",
    "timezone",
    "output_contract",
    "review_policy",
    "brain_request",
    "depends_on",
)
EDITABLE = (
    "project_id",
    "title",
    "purpose",
    "instructions",
    "assignee_id",
    "schedule",
    "timezone",
    "output_contract",
    "review_policy",
    "brain_request",
    "depends_on",
)


def normalize_contract(contract: dict[str, Any] | None) -> dict[str, Any]:
    contract = dict(contract or {})
    items = []
    for entry in contract.get("artifacts") or []:
        entry = dict(entry) if isinstance(entry, dict) else {"type": str(entry)}
        artifact_types.get(str(entry.get("type")))
        if "count" in entry:
            count = entry["count"]
            if not isinstance(count, int) or not 1 <= count <= 50:
                raise ValidationFailed(
                    "An output count is a whole number from 1 to 50.", field="output_contract"
                )
        items.append(entry)
    out: dict[str, Any] = {"artifacts": items}
    if contract.get("notes"):
        out["notes"] = str(contract["notes"])
    if contract.get("tool"):
        if contract["tool"] not in RESULT_TOOLS:
            raise ValidationFailed(
                f"A result tool is one of {', '.join(RESULT_TOOLS)}.", field="output_contract"
            )
        out["tool"] = str(contract["tool"])
    return out


def first_due(schedule: Schedule, timezone: str, now: datetime) -> str | None:
    """When a task that becomes ready now is first due. None: due immediately."""
    if schedule.kind == "manual":
        return None
    if schedule.kind == "once":
        assert schedule.at is not None
        moment = datetime.fromisoformat(schedule.at).replace(tzinfo=zone(timezone))
        return iso(moment)
    upcoming = schedule.next_after(now, timezone)
    return iso(upcoming) if upcoming else None


class Tasks:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    # ---------------------------------------------------------------- queries

    def get(self, who: Principal, task_id: str) -> Task:
        with self.rt.read() as tx:
            row = tx.one(schema.tasks, task_id, "task")
        who.require("tasks.read", row["project_id"])
        return Task.from_row(row)

    def list(
        self,
        who: Principal,
        *,
        project_id: str | None = None,
        status: str | builtins.list[str] | None = None,
        assignee_id: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> builtins.list[Task]:
        who.require("tasks.read", project_id)
        table = schema.tasks
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id)
        if project_id:
            query = query.where(table.c.project_id == project_id)
        if status:
            statuses = [status] if isinstance(status, str) else list(status)
            query = query.where(table.c.status.in_(statuses))
        if assignee_id:
            query = query.where(table.c.assignee_id == assignee_id)
        if not include_archived:
            query = query.where(table.c.archived_at.is_(None))
        with self.rt.read() as tx:
            rows = tx.rows(query.order_by(table.c.updated_at.desc()).limit(limit))
        return [Task.from_row(r) for r in rows if who.sees_project(r["project_id"])]

    def revisions(self, who: Principal, task_id: str) -> builtins.list[dict[str, Any]]:
        self.get(who, task_id)
        table = schema.task_revisions
        with self.rt.read() as tx:
            return tx.rows(
                sa.select(table).where(table.c.task_id == task_id).order_by(table.c.revision)
            )

    def runs(self, who: Principal, task_id: str) -> builtins.list[Run]:
        self.get(who, task_id)
        table = schema.task_runs
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table)
                .where(table.c.task_id == task_id)
                .order_by(table.c.claimed_at.desc())
            )
        return [Run.from_row(r) for r in rows]

    def pins(self, who: Principal, task_id: str) -> builtins.list[Pin]:
        self.get(who, task_id)
        table = schema.task_pins
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table).where(table.c.task_id == task_id).order_by(table.c.created_at)
            )
        return [Pin.from_row(r) for r in rows]

    def preview_packet(self, who: Principal, task_id: str) -> dict[str, Any]:
        """Exactly what the assignee would receive if it claimed the task now."""
        with self.rt.read() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.read", row["project_id"])
            return packets.resolve(tx, self.rt, row)

    # ---------------------------------------------------------------- definition

    def create(
        self,
        who: Principal,
        *,
        title: str,
        project_id: str | None = None,
        purpose: str = "",
        instructions: str = "",
        assignee_id: str | None = None,
        schedule: dict[str, Any] | None = None,
        timezone: str | None = None,
        output_contract: dict[str, Any] | None = None,
        review_policy: str = "required",
        brain_request: str | None = None,
        depends_on: str | None = None,
        template: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Task:
        who.require("tasks.write", project_id)
        with self.rt.write() as tx:
            row = self.create_in(
                tx,
                who,
                title=title,
                project_id=project_id,
                purpose=purpose,
                instructions=instructions,
                assignee_id=assignee_id,
                schedule=schedule,
                timezone=timezone,
                output_contract=output_contract,
                review_policy=review_policy,
                brain_request=brain_request,
                depends_on=depends_on,
                template=template,
                provenance=provenance,
            )
        return Task.from_row(row)

    def create_in(
        self,
        tx: Tx,
        who: Principal,
        *,
        title: str,
        project_id: str | None = None,
        purpose: str = "",
        instructions: str = "",
        assignee_id: str | None = None,
        schedule: dict[str, Any] | None = None,
        timezone: str | None = None,
        output_contract: dict[str, Any] | None = None,
        review_policy: str = "required",
        brain_request: str | None = None,
        depends_on: str | None = None,
        template: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a task inside the caller's write; the caller checks permission."""
        values = self._validated(
            tx,
            {
                "project_id": project_id,
                "title": title,
                "purpose": purpose,
                "instructions": instructions,
                "assignee_id": assignee_id,
                "schedule": schedule,
                "timezone": timezone,
                "output_contract": output_contract,
                "review_policy": review_policy,
                "brain_request": brain_request,
                "depends_on": depends_on,
            },
        )
        row = tx.insert(
            schema.tasks,
            {
                **values,
                "id": tx.new_id("task"),
                "workspace_id": self.rt.workspace_id,
                "prompt_version": 1,
                "next_due_at": None,
                "status": TASK.initial,
                "attempts": 0,
                "template": template,
                "current_run_id": None,
                "revision": 1,
                "provenance": provenance or {},
                "created_by": who.actor_id,
                "created_at": tx.now,
                "updated_at": tx.now,
                "version": 1,
                "archived_at": None,
            },
        )
        self._snapshot(tx, who, row)
        tx.emit(
            "task.created",
            actor_id=who.actor_id,
            subject_type="task",
            subject_id=row["id"],
            project_id=project_id,
            data={"title": row["title"], "assignee_id": row["assignee_id"]},
        )
        return row

    def update(
        self, who: Principal, task_id: str, *, expected_version: int | None = None, **changes: Any
    ) -> Task:
        unknown = set(changes) - set(EDITABLE)
        if unknown:
            raise ValidationFailed(f"These task fields cannot be edited: {sorted(unknown)}.")
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", row["project_id"])
            if "project_id" in changes:
                who.require("tasks.write", changes["project_id"])
            merged = {field: row[field] for field in EDITABLE}
            merged.update(changes)
            values = self._validated(tx, merged, task_id=task_id)
            diff = {k: v for k, v in values.items() if v != row[k]}
            if not diff:
                return Task.from_row(row)
            if "instructions" in diff:
                diff["prompt_version"] = row["prompt_version"] + 1
            if row["status"] == "ready" and ({"schedule", "timezone"} & set(diff)):
                diff["next_due_at"] = first_due(
                    Schedule.from_dict(values["schedule"]), values["timezone"], tx.moment
                )
            diff["revision"] = row["revision"] + 1
            row = tx.update(schema.tasks, row, diff, expected_version=expected_version)
            self._snapshot(tx, who, row)
            tx.emit(
                "task.updated",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=row["project_id"],
                data={
                    "fields": sorted(k for k in diff if k != "revision"),
                    "revision": row["revision"],
                },
            )
        return Task.from_row(row)

    def pin(
        self,
        who: Principal,
        task_id: str,
        *,
        ref_type: str,
        ref_id: str,
        version: int | None = None,
        note: str | None = None,
    ) -> Pin:
        if ref_type not in PIN_TYPES:
            raise ValidationFailed(
                f"Pins refer to one of {', '.join(PIN_TYPES)}.", field="ref_type"
            )
        with self.rt.write() as tx:
            task = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", task["project_id"])
            self._check_ref(tx, ref_type, ref_id, version)
            table = schema.task_pins
            existing = tx.first(
                sa.select(table).where(
                    table.c.task_id == task_id,
                    table.c.ref_type == ref_type,
                    table.c.ref_id == ref_id,
                )
            )
            if existing:
                tx.conn.execute(
                    table.update()
                    .where(table.c.id == existing["id"])
                    .values(pinned_version=version, note=note)
                )
                row = dict(existing, pinned_version=version, note=note)
            else:
                row = tx.insert(
                    table,
                    {
                        "id": tx.new_id("pin"),
                        "task_id": task_id,
                        "ref_type": ref_type,
                        "ref_id": ref_id,
                        "pinned_version": version,
                        "note": note,
                        "created_by": who.actor_id,
                        "created_at": tx.now,
                    },
                )
            tx.emit(
                "task.pinned",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=task["project_id"],
                data={"ref": f"{ref_type}:{ref_id}", "version": version},
            )
        return Pin.from_row(row)

    def unpin(self, who: Principal, task_id: str, pin_id: str) -> None:
        with self.rt.write() as tx:
            task = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", task["project_id"])
            pin = tx.one(schema.task_pins, pin_id, "pin")
            if pin["task_id"] != task_id:
                raise NotFound(f"No pin {pin_id} on task {task_id}.")
            tx.conn.execute(schema.task_pins.delete().where(schema.task_pins.c.id == pin_id))
            tx.emit(
                "task.unpinned",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=task["project_id"],
                data={"ref": f"{pin['ref_type']}:{pin['ref_id']}"},
            )

    # ---------------------------------------------------------------- lifecycle

    def mark_ready(self, who: Principal, task_id: str) -> Task:
        """Draft, blocked or failed work becomes claimable (once due)."""
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", row["project_id"])
            row = self.ready_in(tx, who, row)
        return Task.from_row(row)

    def ready_in(self, tx: Tx, who: Principal, row: dict[str, Any]) -> dict[str, Any]:
        """Make a task ready inside the caller's write; the caller checks permission."""
        task_id = row["id"]
        TASK.check(row["status"], "ready")
        changes: dict[str, Any] = {"status": "ready"}
        if row["status"] == "draft":
            if not row["assignee_id"]:
                raise ValidationFailed(
                    "Assign the task to a model or person first.", field="assignee_id"
                )
            if not row["instructions"].strip():
                raise ValidationFailed("Write the instructions first.", field="instructions")
            changes["next_due_at"] = first_due(
                Schedule.from_dict(row["schedule"]), row["timezone"], tx.moment
            )
            changes["attempts"] = 0
        row = tx.update(schema.tasks, row, changes)
        tx.emit(
            "task.ready",
            actor_id=who.actor_id,
            subject_type="task",
            subject_id=task_id,
            project_id=row["project_id"],
            data={"due_at": row["next_due_at"]},
        )
        return row

    def return_to_draft(self, who: Principal, task_id: str) -> Task:
        return self._move(who, task_id, "draft", "task.drafted")

    def cancel(self, who: Principal, task_id: str, reason: str = "") -> Task:
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", row["project_id"])
            TASK.check(row["status"], "cancelled")
            self._end_active_run(tx, row, "cancelled")
            row = tx.update(schema.tasks, row, {"status": "cancelled"})
            tx.emit(
                "task.cancelled",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=row["project_id"],
                reason=reason or None,
            )
        return Task.from_row(row)

    def archive(self, who: Principal, task_id: str) -> Task:
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", row["project_id"])
            TASK.check(row["status"], "archived")
            row = tx.update(schema.tasks, row, {"status": "archived", "archived_at": tx.now})
            tx.emit(
                "task.archived",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=row["project_id"],
            )
        return Task.from_row(row)

    def restore(self, who: Principal, task_id: str) -> Task:
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", row["project_id"])
            TASK.check(row["status"], "draft")
            row = tx.update(schema.tasks, row, {"status": "draft", "archived_at": None})
            tx.emit(
                "task.restored",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=row["project_id"],
            )
        return Task.from_row(row)

    def complete_review(self, who: Principal, task_id: str) -> Task:
        """Close a review by hand, without deciding every open approval."""
        return self._move(who, task_id, "done", "task.done")

    # ---------------------------------------------------------------- internals

    def _move(self, who: Principal, task_id: str, target: str, event: str) -> Task:
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.write", row["project_id"])
            TASK.check(row["status"], target)
            row = tx.update(schema.tasks, row, {"status": target})
            tx.emit(
                event,
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=row["project_id"],
            )
        return Task.from_row(row)

    def _end_active_run(self, tx: Tx, task: dict[str, Any], status: str) -> None:
        if not task["current_run_id"]:
            return
        run = tx.get(schema.task_runs, task["current_run_id"])
        if run and RUN.is_active(run["status"]):
            RUN.check(run["status"], status)
            tx.update(schema.task_runs, run, {"status": status, "finished_at": tx.now})

    def _validated(
        self, tx: Tx, values: dict[str, Any], task_id: str | None = None
    ) -> dict[str, Any]:
        out = dict(values)
        title = " ".join(str(values.get("title") or "").split())
        if not title:
            raise ValidationFailed("A task needs a title.", field="title")
        out["title"] = title
        out["purpose"] = str(values.get("purpose") or "")
        out["instructions"] = str(values.get("instructions") or "")
        project_id = values.get("project_id")
        if project_id:
            project = tx.one(schema.projects, project_id, "project")
            if project["archived_at"]:
                raise ValidationFailed("That project is archived.", field="project_id")
        assignee_id = values.get("assignee_id")
        if assignee_id:
            actor = tx.get(schema.actors, assignee_id)
            if actor is None or actor["disabled_at"]:
                raise ValidationFailed(
                    "Assign the task to a connected model or a person.", field="assignee_id"
                )
            if actor["kind"] == "model" and not actor_can_claim(tx, assignee_id, project_id):
                raise ValidationFailed(
                    f"{actor['name']} has no credential that can claim work in this project.",
                    field="assignee_id",
                )
        workspace = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        out["timezone"] = values.get("timezone") or workspace["timezone"]
        zone(out["timezone"])
        out["schedule"] = Schedule.from_dict(values.get("schedule")).to_dict()
        out["output_contract"] = normalize_contract(values.get("output_contract"))
        if values.get("review_policy") not in REVIEW_POLICIES:
            raise ValidationFailed("Review policy is 'required' or 'auto'.", field="review_policy")
        out["brain_request"] = values.get("brain_request") or None
        depends_on = values.get("depends_on")
        if depends_on:
            if depends_on == task_id:
                raise ValidationFailed("A task cannot wait for itself.", field="depends_on")
            tx.one(schema.tasks, depends_on, "task")
        out["depends_on"] = depends_on or None
        return out

    def _snapshot(self, tx: Tx, who: Principal, row: dict[str, Any]) -> None:
        tx.insert(
            schema.task_revisions,
            {
                "task_id": row["id"],
                "revision": row["revision"],
                "definition": {field: row[field] for field in DEFINITION_FIELDS},
                "created_by": who.actor_id,
                "created_at": tx.now,
            },
        )

    def _check_ref(self, tx: Tx, ref_type: str, ref_id: str, version: int | None) -> None:
        if ref_type == "context_item":
            item = tx.one(schema.context_items, ref_id, "working-context item")
            if version is not None and not 1 <= version <= item["revision"]:
                raise ValidationFailed(
                    f"That item has versions 1 to {item['revision']}.", field="version"
                )
        elif ref_type == "artifact":
            artifact = tx.one(schema.artifacts, ref_id, "artifact")
            if version is not None and not 1 <= version <= artifact["current_version"]:
                raise ValidationFailed(
                    f"That artifact has versions 1 to {artifact['current_version']}.",
                    field="version",
                )
        elif ref_type == "brain_project":
            if self.rt.brain.project(ref_id) is None:
                raise NotFound(f"The Brain follows no project {ref_id}.")
        elif ref_type == "brain_file":
            if self.rt.brain.reference(ref_id) is None:
                raise NotFound(f"The Brain holds no document {ref_id}.")
        elif self.rt.brain.entry(ref_id) is None:
            raise NotFound(f"No Brain entry {ref_id}.")
