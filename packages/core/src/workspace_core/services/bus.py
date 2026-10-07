"""The task bus: pull-based work for models (spec sections 09 and 10).

A model's scheduled check asks for its due work, claims a task for a bounded lease, reports
progress, writes artifacts, and completes the run. The server disposes: assignment, valid
transitions, leases, write permission and idempotency are enforced here, whatever the prompt
says. The run id is the fencing token: once a run has ended or its lease has run out, nothing
more can be written through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso
from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Event, Run, Task
from workspace_core.domain.states import RUN, TASK
from workspace_core.errors import Conflict, LeaseLost, NotFound, PermissionDenied, ValidationFailed

from . import lifecycle, packets
from .runtime import Runtime, recall, remember

EVENT_TYPES = ("progress", "evidence", "note", "context_used", "heartbeat", "blocker")
OUTCOMES = ("succeeded", "failed")


@dataclass(frozen=True)
class DueWork:
    tasks: list[Task]
    active_runs: list[Run]


@dataclass(frozen=True)
class Claim:
    run: Run
    packet: dict[str, Any]


def active_run(tx: Tx, who: Principal, run_id: str) -> dict[str, Any]:
    """The caller's live run, or the reason it can no longer be written."""
    run = tx.one(schema.task_runs, run_id, "run")
    if run["actor_id"] != who.actor_id:
        raise PermissionDenied("This run belongs to another actor.", run_id=run_id)
    if not RUN.is_active(run["status"]):
        raise LeaseLost(
            f"This run has ended ({run['status']}). Claim the task again to continue.",
            run_id=run_id,
            status=run["status"],
        )
    if run["lease_expires_at"] <= tx.now:
        raise LeaseLost(
            f"The lease on this run expired at {run['lease_expires_at']}. Claim "
            "the task again to continue.",
            run_id=run_id,
        )
    return run


class Bus:
    def __init__(self, rt: Runtime, system_actor_id: str) -> None:
        self.rt = rt
        self.system_actor_id = system_actor_id

    # ---------------------------------------------------------------- the pull queue

    def due(self, who: Principal, limit: int = 20) -> DueWork:
        """Work assigned to the caller that is ready and due now, plus its live runs."""
        who.require("tasks.claim")
        self.schedule_due()
        tasks, runs = schema.tasks, schema.task_runs
        with self.rt.write() as tx:
            rows = tx.rows(
                sa.select(tasks)
                .where(
                    tasks.c.assignee_id == who.actor_id,
                    tasks.c.status == "ready",
                    tasks.c.archived_at.is_(None),
                    sa.or_(tasks.c.next_due_at.is_(None), tasks.c.next_due_at <= tx.now),
                )
                .order_by(sa.func.coalesce(tasks.c.next_due_at, tasks.c.created_at))
            )
            ready = [
                r for r in rows if who.sees_project(r["project_id"]) and self._dependency_met(tx, r)
            ][:limit]
            live = tx.rows(
                sa.select(runs)
                .where(runs.c.actor_id == who.actor_id, runs.c.status.in_(sorted(RUN.active)))
                .order_by(runs.c.claimed_at)
            )
            tx.conn.execute(
                schema.actors.update()
                .where(schema.actors.c.id == who.actor_id)
                .values(last_seen_at=tx.now)
            )
            tx.emit(
                "bus.polled",
                actor_id=who.actor_id,
                subject_type="actor",
                subject_id=who.actor_id,
                data={"due": len(ready), "active": len(live)},
                noise=True,
            )
        return DueWork(
            tasks=[Task.from_row(r) for r in ready], active_runs=[Run.from_row(r) for r in live]
        )

    def claim(
        self,
        who: Principal,
        task_id: str,
        *,
        lease_seconds: int | None = None,
        idempotency_key: str | None = None,
    ) -> Claim:
        request = {"task_id": task_id, "lease_seconds": lease_seconds}
        self.schedule_due()
        with self.rt.write() as tx:
            prior = recall(tx, who, idempotency_key, "tasks.claim", request)
            if prior:
                run = tx.one(schema.task_runs, prior, "run")
                return Claim(run=Run.from_row(run), packet=run["packet"])
            task = tx.one(schema.tasks, task_id, "task")
            who.require("tasks.claim", task["project_id"])
            if task["assignee_id"] != who.actor_id:
                raise PermissionDenied(
                    "This task is assigned to someone else; it is not in your queue.",
                    task_id=task_id,
                )
            if task["status"] != "ready":
                raise Conflict(
                    f"This task is not available to claim: it is "
                    f"{task['status'].replace('_', ' ')}.",
                    status=task["status"],
                )
            if task["next_due_at"] and task["next_due_at"] > tx.now:
                raise Conflict(
                    f"This task is not due until {task['next_due_at']}.", due_at=task["next_due_at"]
                )
            if not self._dependency_met(tx, task):
                raise Conflict(
                    "This task waits for another task to finish first.",
                    depends_on=task["depends_on"],
                )
            seconds = max(
                30, min(int(lease_seconds or self.rt.lease_seconds), self.rt.max_lease_seconds)
            )
            run_id = tx.new_id("run")
            attempt = int(task["attempts"]) + 1
            task = tx.update(
                schema.tasks,
                task,
                {"status": "claimed", "current_run_id": run_id, "attempts": attempt},
            )
            run = {
                "id": run_id,
                "workspace_id": self.rt.workspace_id,
                "task_id": task_id,
                "attempt": attempt,
                "occurrence": task["next_due_at"] or "manual",
                "status": RUN.initial,
                "actor_id": who.actor_id,
                "task_revision": task["revision"],
                "claimed_at": tx.now,
                "lease_expires_at": iso(tx.moment + timedelta(seconds=seconds)),
                "started_at": None,
                "finished_at": None,
                "outcome": {},
                "version": 1,
            }
            run["packet"] = packets.resolve(tx, self.rt, task, run)
            tx.insert(schema.task_runs, run)
            self._touch_inputs(tx, run["packet"])
            tx.emit(
                "task.claimed",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=task_id,
                project_id=task["project_id"],
                data={
                    "run_id": run_id,
                    "attempt": attempt,
                    "lease_expires_at": run["lease_expires_at"],
                },
            )
            remember(tx, who, idempotency_key, "tasks.claim", request, "run", run_id)
        self._count_brain_use(run_id, run["packet"])
        return Claim(run=Run.from_row(run), packet=run["packet"])

    def _count_brain_use(self, run_id: str, packet: dict[str, Any]) -> None:
        """Tell the Brain which entries this run was handed, so their use counts AI work
        too. Counting never stands in the way of the work: a Brain that cannot record it
        loses the count, not the claim."""
        entries = (packet.get("brain") or {}).get("entries") or []
        if not entries:
            return
        try:
            self.rt.brain.record_use(run_id, entries)
        except Exception:  # noqa: BLE001 - see above
            return

    def run(self, who: Principal, run_id: str) -> Run:
        with self.rt.read() as tx:
            row = tx.one(schema.task_runs, run_id, "run")
            if row["actor_id"] != who.actor_id:
                task = tx.one(schema.tasks, row["task_id"], "task")
                who.require("tasks.read", task["project_id"])
        return Run.from_row(row)

    def packet(
        self, who: Principal, *, task_id: str | None = None, run_id: str | None = None
    ) -> dict[str, Any]:
        """The packet of a run (as stored at claim time), or the caller's live run on a task."""
        runs = schema.task_runs
        with self.rt.read() as tx:
            if run_id:
                row = tx.one(runs, run_id, "run")
            elif task_id:
                live = tx.first(
                    sa.select(runs)
                    .where(
                        runs.c.task_id == task_id,
                        runs.c.actor_id == who.actor_id,
                        runs.c.status.in_(sorted(RUN.active)),
                    )
                    .order_by(runs.c.claimed_at.desc())
                )
                if live is None:
                    task = tx.one(schema.tasks, task_id, "task")
                    who.require("tasks.read", task["project_id"])
                    return packets.resolve(tx, self.rt, task)
                row = live
            else:
                raise ValidationFailed("Give a run_id or a task_id.")
            if row["actor_id"] != who.actor_id:
                task = tx.one(schema.tasks, row["task_id"], "task")
                who.require("tasks.read", task["project_id"])
            return dict(row["packet"])

    # ---------------------------------------------------------------- run writes

    def append(
        self,
        who: Principal,
        run_id: str,
        *,
        type: str,
        message: str = "",
        data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Event:
        if type not in EVENT_TYPES:
            raise ValidationFailed(
                f"Event type must be one of {', '.join(EVENT_TYPES)}.", field="type"
            )
        message = str(message or "").strip()
        if type == "blocker" and not message:
            raise ValidationFailed(
                "A blocker needs a concrete reason a person can act on.", field="message"
            )
        request = {"run_id": run_id, "type": type, "message": message, "data": data}
        with self.rt.write() as tx:
            prior = recall(tx, who, idempotency_key, "runs.append", request)
            if prior:
                return self._event(tx, prior)
            run = active_run(tx, who, run_id)
            task = tx.one(schema.tasks, run["task_id"], "task")
            who.require("runs.write", task["project_id"])
            payload = {"run_id": run_id, "message": message, **(data or {})}
            if type == "heartbeat":
                seconds = int((data or {}).get("lease_seconds") or self.rt.lease_seconds)
                seconds = max(30, min(seconds, self.rt.max_lease_seconds))
                expires = iso(tx.moment + timedelta(seconds=seconds))
                tx.update(schema.task_runs, run, {"lease_expires_at": expires})
                event_id = tx.emit(
                    "run.heartbeat",
                    actor_id=who.actor_id,
                    subject_type="run",
                    subject_id=run_id,
                    project_id=task["project_id"],
                    data={"lease_expires_at": expires},
                    noise=True,
                )
            elif type == "blocker":
                RUN.check(run["status"], "blocked")
                tx.update(
                    schema.task_runs,
                    run,
                    {"status": "blocked", "finished_at": tx.now, "outcome": {"blocked": message}},
                )
                TASK.check(task["status"], "blocked")
                tx.update(schema.tasks, task, {"status": "blocked"})
                event_id = tx.emit(
                    "task.blocked",
                    actor_id=who.actor_id,
                    subject_type="task",
                    subject_id=task["id"],
                    project_id=task["project_id"],
                    data=payload,
                    reason=message,
                )
            else:
                if type == "progress" and run["status"] == "claimed":
                    RUN.check("claimed", "in_progress")
                    tx.update(
                        schema.task_runs, run, {"status": "in_progress", "started_at": tx.now}
                    )
                    TASK.check(task["status"], "in_progress")
                    tx.update(schema.tasks, task, {"status": "in_progress"})
                if type == "context_used":
                    self._touch_refs(tx, [str(r) for r in (data or {}).get("refs") or []])
                event_id = tx.emit(
                    f"run.{type}",
                    actor_id=who.actor_id,
                    subject_type="run",
                    subject_id=run_id,
                    project_id=task["project_id"],
                    data=payload,
                )
            remember(tx, who, idempotency_key, "runs.append", request, "event", event_id)
            return self._event(tx, event_id)

    def complete(
        self,
        who: Principal,
        run_id: str,
        *,
        summary: str = "",
        outcome: str = "succeeded",
        idempotency_key: str | None = None,
    ) -> Run:
        """Close the run and release the lease; the task moves to review, done or failed."""
        if outcome not in OUTCOMES:
            raise ValidationFailed("Outcome is 'succeeded' or 'failed'.", field="outcome")
        request = {"run_id": run_id, "summary": summary, "outcome": outcome}
        with self.rt.write() as tx:
            prior = recall(tx, who, idempotency_key, "runs.complete", request)
            if prior:
                return Run.from_row(tx.one(schema.task_runs, prior, "run"))
            run = active_run(tx, who, run_id)
            task = tx.one(schema.tasks, run["task_id"], "task")
            who.require("runs.write", task["project_id"])
            final = "completed" if outcome == "succeeded" else "failed"
            RUN.check(run["status"], final)
            run = tx.update(
                schema.task_runs,
                run,
                {
                    "status": final,
                    "finished_at": tx.now,
                    "outcome": {"result": outcome, "summary": summary},
                },
            )
            tx.emit(
                "run.completed" if final == "completed" else "run.failed",
                actor_id=who.actor_id,
                subject_type="run",
                subject_id=run_id,
                project_id=task["project_id"],
                data={"summary": summary},
            )
            if final == "failed":
                TASK.check(task["status"], "failed")
                task = tx.update(schema.tasks, task, {"status": "failed"})
                tx.emit(
                    "task.failed",
                    actor_id=who.actor_id,
                    subject_type="task",
                    subject_id=task["id"],
                    project_id=task["project_id"],
                    reason=summary or None,
                )
            else:
                pending = tx.first(
                    sa.select(schema.approvals.c.id).where(
                        schema.approvals.c.task_id == task["id"],
                        schema.approvals.c.run_id == run_id,
                        schema.approvals.c.status == "pending",
                    )
                )
                if task["review_policy"] == "auto" and not pending:
                    lifecycle.finish_cycle(tx, task, who.actor_id)
                else:
                    TASK.check(task["status"], "review")
                    task = tx.update(schema.tasks, task, {"status": "review"})
                    tx.emit(
                        "task.review",
                        actor_id=who.actor_id,
                        subject_type="task",
                        subject_id=task["id"],
                        project_id=task["project_id"],
                        data={"run_id": run_id, "summary": summary},
                    )
                    lifecycle.open_review(tx, task, run, who.actor_id, summary)
                    lifecycle.settle_review(tx, task, who.actor_id)
            remember(tx, who, idempotency_key, "runs.complete", request, "run", run_id)
        return Run.from_row(run)

    # ---------------------------------------------------------------- the clock's side

    def expire_leases(self) -> list[Run]:
        """End runs whose lease ran out and put their tasks back in the queue."""
        runs = schema.task_runs
        expired = []
        with self.rt.write() as tx:
            rows = tx.rows(
                sa.select(runs).where(
                    runs.c.status.in_(sorted(RUN.active)), runs.c.lease_expires_at < tx.now
                )
            )
            for run in rows:
                run = tx.update(schema.task_runs, run, {"status": "expired", "finished_at": tx.now})
                task = tx.one(schema.tasks, run["task_id"], "task")
                if task["current_run_id"] == run["id"] and TASK.is_active(task["status"]):
                    tx.update(schema.tasks, task, {"status": "ready"})
                tx.emit(
                    "run.lease_expired",
                    actor_id=self.system_actor_id,
                    subject_type="run",
                    subject_id=run["id"],
                    project_id=task["project_id"],
                    data={"task_id": task["id"], "actor_id": run["actor_id"]},
                )
                expired.append(Run.from_row(run))
        return expired

    def schedule_due(self) -> list[Task]:
        """Recurring tasks whose next occurrence has arrived become ready again."""
        tasks = schema.tasks
        woke = []
        with self.rt.write() as tx:
            rows = tx.rows(
                sa.select(tasks).where(
                    tasks.c.status == "done",
                    tasks.c.next_due_at.is_not(None),
                    tasks.c.next_due_at <= tx.now,
                    tasks.c.archived_at.is_(None),
                )
            )
            for task in rows:
                task = tx.update(schema.tasks, task, {"status": "ready", "attempts": 0})
                tx.emit(
                    "task.due",
                    actor_id=self.system_actor_id,
                    subject_type="task",
                    subject_id=task["id"],
                    project_id=task["project_id"],
                    data={"due_at": task["next_due_at"]},
                )
                woke.append(Task.from_row(task))
        return woke

    # ---------------------------------------------------------------- internals

    def _dependency_met(self, tx: Tx, task: dict[str, Any]) -> bool:
        if not task["depends_on"]:
            return True
        other = tx.get(schema.tasks, task["depends_on"])
        return other is not None and other["status"] in ("done", "archived")

    def _event(self, tx: Tx, event_id: str) -> Event:
        row = tx.first(sa.select(schema.events).where(schema.events.c.id == event_id))
        if row is None:
            raise NotFound(f"No event {event_id}.")
        return Event.from_row(row)

    def _touch_inputs(self, tx: Tx, packet: dict[str, Any]) -> None:
        self._touch_refs(tx, [str(i.get("ref")) for i in packet.get("inputs", [])])

    def _touch_refs(self, tx: Tx, refs: list[str]) -> None:
        ids = [r.split(":", 1)[1] for r in refs if r.startswith("context_item:")]
        if ids:
            table = schema.context_items
            tx.conn.execute(
                table.update().where(table.c.id.in_(ids)).values(last_referenced_at=tx.now)
            )
