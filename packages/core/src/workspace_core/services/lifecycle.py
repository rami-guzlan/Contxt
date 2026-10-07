"""Task lifecycle steps shared by the bus (models) and approvals (people)."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso, parse_iso
from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.schedule import Schedule
from workspace_core.domain.states import ARTIFACT, TASK


def finish_cycle(tx: Tx, task: dict[str, Any], actor_id: str) -> dict[str, Any]:
    """Mark the task done and, for recurring work, set when it is next due."""
    TASK.check(task["status"], "done")
    changes: dict[str, Any] = {"status": "done"}
    schedule = Schedule.from_dict(task["schedule"])
    if schedule.recurring:
        base = parse_iso(task["next_due_at"]) if task["next_due_at"] else tx.moment
        upcoming = schedule.next_after(base, task["timezone"])
        # Missed occurrences are skipped, never piled up: the next one is in the future.
        while upcoming is not None and upcoming <= tx.moment:
            upcoming = schedule.next_after(upcoming, task["timezone"])
        changes["next_due_at"] = iso(upcoming) if upcoming else None
    task = tx.update(schema.tasks, task, changes)
    tx.emit(
        "task.done",
        actor_id=actor_id,
        subject_type="task",
        subject_id=task["id"],
        project_id=task["project_id"],
        data={"next_due_at": task["next_due_at"]},
    )
    return task


def open_review(
    tx: Tx, task: dict[str, Any], run: dict[str, Any], actor_id: str, summary: str
) -> None:
    """Put every unreviewed artifact from this run in front of a person."""
    artifacts, approvals = schema.artifacts, schema.approvals
    produced = tx.rows(
        sa.select(artifacts).where(
            artifacts.c.run_id == run["id"], artifacts.c.archived_at.is_(None)
        )
    )
    versions = schema.artifact_versions
    revised = tx.rows(
        sa.select(artifacts)
        .join(versions, versions.c.artifact_id == artifacts.c.id)
        .where(versions.c.run_id == run["id"])
    )
    seen: set[str] = set()
    subjects = []
    for row in produced + revised:
        if row["id"] not in seen:
            seen.add(row["id"])
            subjects.append(row)
    opened = 0
    for artifact in subjects:
        pending = tx.first(
            sa.select(approvals.c.id).where(
                approvals.c.subject_type == "artifact",
                approvals.c.subject_id == artifact["id"],
                approvals.c.status == "pending",
            )
        )
        if pending or artifact["status"] not in ("draft",):
            continue
        request_artifact_review(tx, artifact, actor_id, summary, task, run["id"])
        opened += 1
    has_pending = tx.first(
        sa.select(approvals.c.id).where(
            approvals.c.task_id == task["id"],
            approvals.c.run_id == run["id"],
            approvals.c.status == "pending",
        )
    )
    if not has_pending and not opened:
        # Nothing to look at but the run itself: the person closes it.
        tx.insert(
            approvals,
            {
                "id": tx.new_id("appr"),
                "workspace_id": tx.workspace_id,
                "subject_type": "task",
                "subject_id": task["id"],
                "subject_version": task["revision"],
                "project_id": task["project_id"],
                "task_id": task["id"],
                "run_id": run["id"],
                "status": "pending",
                "reason": summary or "The run finished without artifacts.",
                "requested_by": actor_id,
                "requested_at": tx.now,
                "decided_by": None,
                "decided_at": None,
                "decision_note": None,
                "version": 1,
            },
        )


def request_artifact_review(
    tx: Tx,
    artifact: dict[str, Any],
    actor_id: str,
    reason: str,
    task: dict[str, Any] | None,
    run_id: str | None,
) -> dict[str, Any]:
    if artifact["status"] != "in_review":
        ARTIFACT.check(artifact["status"], "in_review")
        artifact = tx.update(schema.artifacts, artifact, {"status": "in_review"})
    row = tx.insert(
        schema.approvals,
        {
            "id": tx.new_id("appr"),
            "workspace_id": tx.workspace_id,
            "subject_type": "artifact",
            "subject_id": artifact["id"],
            "subject_version": artifact["current_version"],
            "project_id": artifact["project_id"],
            "task_id": task["id"] if task else artifact["task_id"],
            "run_id": run_id,
            "status": "pending",
            "reason": reason or "",
            "requested_by": actor_id,
            "requested_at": tx.now,
            "decided_by": None,
            "decided_at": None,
            "decision_note": None,
            "version": 1,
        },
    )
    tx.emit(
        "approval.requested",
        actor_id=actor_id,
        subject_type="artifact",
        subject_id=artifact["id"],
        project_id=artifact["project_id"],
        data={"approval_id": row["id"], "version": artifact["current_version"]},
        reason=reason or None,
    )
    return row


def settle_review(tx: Tx, task: dict[str, Any], actor_id: str) -> dict[str, Any]:
    """When nothing on the task's latest run is still pending, move the task on."""
    if task["status"] != "review" or not task["current_run_id"]:
        return task
    table = schema.approvals
    decided = tx.rows(
        sa.select(table.c.status).where(
            table.c.task_id == task["id"], table.c.run_id == task["current_run_id"]
        )
    )
    statuses = [r["status"] for r in decided]
    if "pending" in statuses:
        return task
    if "changes_requested" in statuses:
        task = tx.update(schema.tasks, task, {"status": "ready"})
        tx.emit(
            "task.ready",
            actor_id=actor_id,
            subject_type="task",
            subject_id=task["id"],
            project_id=task["project_id"],
            reason="changes requested",
        )
        return task
    if "approved" in statuses or not statuses:
        return finish_cycle(tx, task, actor_id)
    task = tx.update(schema.tasks, task, {"status": "failed"})
    tx.emit(
        "task.failed",
        actor_id=actor_id,
        subject_type="task",
        subject_id=task["id"],
        project_id=task["project_id"],
        reason="every result was rejected",
    )
    return task
