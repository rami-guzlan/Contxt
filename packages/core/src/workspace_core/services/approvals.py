"""Approvals: every consequential result lands on a human decision surface.

A model (or a person) opens an approval; only a person decides it. Deciding applies to the
subject (an artifact version, or a task run without artifacts) and then settles the task's
review: approved work is done, changes requested send the task back with the note, and
rejected work fails the attempt.
"""

from __future__ import annotations

import builtins
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Approval
from workspace_core.domain.states import APPROVAL, ARTIFACT
from workspace_core.errors import Conflict, PermissionDenied, ValidationFailed

from . import lifecycle
from .runtime import Runtime, recall, remember

DECISIONS = ("approved", "rejected", "changes_requested")
SUBJECTS = ("artifact", "task")


class Approvals:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def list(
        self,
        who: Principal,
        *,
        status: str | None = "pending",
        project_id: str | None = None,
        limit: int = 200,
    ) -> builtins.list[Approval]:
        table = schema.approvals
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id)
        if status:
            query = query.where(table.c.status == status)
        if project_id:
            query = query.where(table.c.project_id == project_id)
        with self.rt.read() as tx:
            rows = tx.rows(query.order_by(table.c.requested_at.desc()).limit(limit))
        return [Approval.from_row(r) for r in rows if who.sees_project(r["project_id"])]

    def get(self, who: Principal, approval_id: str) -> Approval:
        with self.rt.read() as tx:
            row = tx.one(schema.approvals, approval_id, "approval")
        who.require("artifacts.read", row["project_id"])
        return Approval.from_row(row)

    def request(
        self,
        who: Principal,
        *,
        subject_type: str,
        subject_id: str,
        run_id: str | None = None,
        reason: str = "",
        idempotency_key: str | None = None,
    ) -> Approval:
        if subject_type not in SUBJECTS:
            raise ValidationFailed("Approvals are for an artifact or a task.", field="subject_type")
        request = {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "run_id": run_id,
            "reason": reason,
        }
        with self.rt.write() as tx:
            prior = recall(tx, who, idempotency_key, "approvals.request", request)
            if prior:
                return Approval.from_row(tx.one(schema.approvals, prior, "approval"))
            table = schema.approvals
            if subject_type == "artifact":
                artifact = tx.one(schema.artifacts, subject_id, "artifact")
                who.require("approvals.request", artifact["project_id"])
                if not who.is_human and artifact["created_by"] != who.actor_id:
                    raise PermissionDenied("A model can ask for review of its own work only.")
                existing = tx.first(
                    sa.select(table).where(
                        table.c.subject_type == "artifact",
                        table.c.subject_id == subject_id,
                        table.c.subject_version == artifact["current_version"],
                        table.c.status == "pending",
                    )
                )
                if existing:
                    return Approval.from_row(existing)
                if artifact["status"] in ("approved", "exported"):
                    raise Conflict("This version is already approved.")
                task = tx.get(schema.tasks, artifact["task_id"]) if artifact["task_id"] else None
                run = run_id or artifact["run_id"] or (task or {}).get("current_run_id")
                if run_id:
                    owner = tx.one(schema.task_runs, run_id, "run")["actor_id"]
                    if owner != who.actor_id and not who.is_human:
                        raise PermissionDenied("That run belongs to another actor.")
                row = lifecycle.request_artifact_review(
                    tx, artifact, who.actor_id, reason, task, run
                )
            else:
                task = tx.one(schema.tasks, subject_id, "task")
                who.require("approvals.request", task["project_id"])
                row = tx.insert(
                    table,
                    {
                        "id": tx.new_id("appr"),
                        "workspace_id": self.rt.workspace_id,
                        "subject_type": "task",
                        "subject_id": subject_id,
                        "subject_version": task["revision"],
                        "project_id": task["project_id"],
                        "task_id": subject_id,
                        "run_id": run_id or task["current_run_id"],
                        "status": "pending",
                        "reason": reason or "",
                        "requested_by": who.actor_id,
                        "requested_at": tx.now,
                        "decided_by": None,
                        "decided_at": None,
                        "decision_note": None,
                        "version": 1,
                    },
                )
                tx.emit(
                    "approval.requested",
                    actor_id=who.actor_id,
                    subject_type="task",
                    subject_id=subject_id,
                    project_id=task["project_id"],
                    data={"approval_id": row["id"]},
                    reason=reason or None,
                )
            remember(tx, who, idempotency_key, "approvals.request", request, "approval", row["id"])
        return Approval.from_row(row)

    def decide(
        self,
        who: Principal,
        approval_id: str,
        *,
        decision: str,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> Approval:
        if decision not in DECISIONS:
            raise ValidationFailed(f"Decision is one of {', '.join(DECISIONS)}.", field="decision")
        with self.rt.write() as tx:
            row = tx.one(schema.approvals, approval_id, "approval")
            who.require("approvals.decide", row["project_id"])
            APPROVAL.check(row["status"], decision)
            if decision == "changes_requested" and not (note or "").strip():
                raise ValidationFailed(
                    "Say what should change, so the next pass can act on it.", field="note"
                )
            row = tx.update(
                schema.approvals,
                row,
                {
                    "status": decision,
                    "decided_by": who.actor_id,
                    "decided_at": tx.now,
                    "decision_note": note,
                },
                expected_version=expected_version,
            )
            if row["subject_type"] == "artifact":
                self._apply_to_artifact(tx, who, row, decision)
            tx.emit(
                "approval.decided",
                actor_id=who.actor_id,
                subject_type=row["subject_type"],
                subject_id=row["subject_id"],
                project_id=row["project_id"],
                data={
                    "approval_id": approval_id,
                    "decision": decision,
                    "version": row["subject_version"],
                },
                reason=note or None,
            )
            if row["task_id"]:
                task = tx.get(schema.tasks, row["task_id"])
                if task:
                    lifecycle.settle_review(tx, task, who.actor_id)
        return Approval.from_row(row)

    def review_artifact(
        self, who: Principal, artifact_id: str, *, decision: str, note: str | None = None
    ) -> Approval:
        """Decide on an artifact's current version directly (opening the approval if needed)."""
        if decision not in DECISIONS:
            raise ValidationFailed(f"Decision is one of {', '.join(DECISIONS)}.", field="decision")
        with self.rt.read() as tx:
            artifact = tx.one(schema.artifacts, artifact_id, "artifact")
            table = schema.approvals
            pending = tx.first(
                sa.select(table.c.id).where(
                    table.c.subject_type == "artifact",
                    table.c.subject_id == artifact_id,
                    table.c.subject_version == artifact["current_version"],
                    table.c.status == "pending",
                )
            )
        who.require("approvals.decide", artifact["project_id"])
        approval_id = (
            pending["id"]
            if pending
            else self.request(
                who, subject_type="artifact", subject_id=artifact_id, reason="Reviewed directly"
            ).id
        )
        return self.decide(who, approval_id, decision=decision, note=note)

    def _apply_to_artifact(
        self, tx: Any, who: Principal, approval: dict[str, Any], decision: str
    ) -> None:
        artifact = tx.one(schema.artifacts, approval["subject_id"], "artifact")
        if approval["subject_version"] != artifact["current_version"]:
            raise Conflict(
                "A newer version of this artifact exists; review that one.",
                current_version=artifact["current_version"],
            )
        target = {"approved": "approved", "rejected": "rejected", "changes_requested": "draft"}[
            decision
        ]
        if artifact["status"] != target:
            ARTIFACT.check(artifact["status"], target)
            tx.update(schema.artifacts, artifact, {"status": target})
        tx.emit(
            f"artifact.{decision}",
            actor_id=who.actor_id,
            subject_type="artifact",
            subject_id=artifact["id"],
            project_id=artifact["project_id"],
            data={"version": artifact["current_version"]},
        )
