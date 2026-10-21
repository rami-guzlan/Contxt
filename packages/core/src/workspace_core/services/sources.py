"""Where each capture stands (Release 1 plan, M03): one status, read from what happened to it.

    captured -> analysis_pending (or retrying) -> awaiting_review -> indexing -> searchable

beside `excluded` (the person keeps it out), `failed` (transcription or the reading run
failed, with why), `nothing_kept` (the run found nothing durable, or every piece was skipped)
and `partial` (some kept pieces are searchable, some not yet). Kept is not searchable: a kept
entry is searchable only once the Brain's search index holds it.

The status is derived, never stored: the capture, its distillation requests and their
proposals, the decisions on them, and the index are each the record of their own part.
Exclusion is the one thing a person sets here; it is kept in the capture's provenance with
an event.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Task
from workspace_core.errors import Conflict, NotFound, ValidationFailed

from .context import open_to
from .distill import Distillation
from .runtime import Runtime

STAGES = ("captured", "analysis", "review", "accepted", "indexing", "searchable")
RUNNING = ("draft", "ready", "claimed", "in_progress", "review")
FAILED = ("failed", "blocked", "cancelled")
LABELS = {
    "captured": "Captured. Not read for the Brain yet.",
    "analysis_pending": "Being read for the Brain.",
    "retrying": "Being read again, by the same model.",
    "awaiting_review": "Waiting for your review.",
    "indexing": "Kept: indexing, not searchable yet.",
    "partial": "Kept: partly searchable.",
    "searchable": "Searchable.",
    "nothing_kept": "Read: nothing kept.",
    "excluded": "Excluded from the Brain.",
    "failed": "Failed.",
}
STAGE_OF = {
    "captured": "captured",
    "analysis_pending": "analysis",
    "retrying": "analysis",
    "failed": "analysis",
    "awaiting_review": "review",
    "nothing_kept": "review",
    "indexing": "indexing",
    "partial": "indexing",
    "searchable": "searchable",
    "excluded": "captured",
}


@dataclass(frozen=True)
class SourceStatus:
    item_id: str
    status: str
    label: str
    stage: str  # how far along STAGES it got
    detail: str = ""  # why it failed or was excluded, or what is partly done
    can_retry: bool = False
    waiting: int = 0  # proposals waiting for review
    kept: int = 0
    skipped: int = 0
    searchable: int = 0  # kept entries the index holds now
    task_id: str | None = None  # the latest request that read it
    proposal_ids: builtins.list[str] = field(default_factory=list)


class Sources:
    def __init__(self, rt: Runtime, distill: Distillation) -> None:
        self.rt = rt
        self.distill = distill

    # ---------------------------------------------------------------- status

    def status(self, who: Principal, item_ids: builtins.list[str]) -> dict[str, SourceStatus]:
        """Each capture's status, by id."""
        who.require("context.read")
        out = {}
        for item_id in dict.fromkeys(str(i) for i in item_ids if i):
            with self.rt.read() as tx:
                row = self._row(tx, who, item_id)
            out[item_id] = self._status(who, row)
        return out

    def _status(self, who: Principal, row: dict[str, Any]) -> SourceStatus:
        item_id = row["id"]
        excluded = (row["provenance"] or {}).get("excluded")
        if excluded:
            return _made(item_id, "excluded", detail=str(excluded.get("reason") or ""))
        if row["shadow_status"] == "failed":
            error = ((row["provenance"] or {}).get("transcription") or {}).get("error")
            return _made(
                item_id, "failed", detail=str(error or "It could not be read."), can_retry=True
            )
        if row["shadow_status"] in ("pending", "working"):
            return _made(item_id, "analysis_pending", detail="Transcribing on this computer.")
        requests = self.distill.requests(who, item_id=item_id, limit=20)
        if not requests:
            return _made(item_id, "captured")
        latest = requests[0]
        running = [r for r in requests if r.status in RUNNING]
        failed = [r for r in requests if r.status in FAILED]
        if running:
            return _made(
                item_id, "retrying" if failed else "analysis_pending", task_id=running[0].task_id
            )
        if failed and not any(r.status == "done" for r in requests):
            return _made(
                item_id,
                "failed",
                task_id=failed[0].task_id,
                can_retry=True,
                detail=failed[0].summary or "The model's run did not finish.",
            )
        proposals = [p for r in requests for p in r.proposals]
        waiting = [p for p in proposals if p.status == "pending"]
        kept = [p for p in proposals if p.status in ("approved", "closed")]
        skipped = [p for p in proposals if p.status == "rejected"]
        counts = {
            "waiting": len(waiting),
            "kept": len(kept),
            "skipped": len(skipped),
            "task_id": latest.task_id,
            "proposal_ids": [p.id for p in proposals],
        }
        if waiting:
            return _made(item_id, "awaiting_review", **counts)
        if not kept:
            return _made(item_id, "nothing_kept", **counts)
        entries = self._entries([p.id for p in kept])
        found = self.rt.brain.indexed(list(entries.values()))
        held = sum(1 for e in entries.values() if e in found)
        if held == len(kept):
            return _made(item_id, "searchable", searchable=held, **counts)
        if held:
            return _made(
                item_id,
                "partial",
                searchable=held,
                detail=f"{held} of {len(kept)} kept pieces searchable.",
                **counts,
            )
        return _made(item_id, "indexing", searchable=0, **counts)

    def _entries(self, proposal_ids: builtins.list[str]) -> dict[str, str]:
        """The entry each kept proposal became: as its approval recorded it, else the
        proposal's own id (a new entry is named by its proposal)."""
        events = schema.events
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(events.c.subject_id, events.c.data).where(
                    events.c.workspace_id == self.rt.workspace_id,
                    events.c.type == "brain.approved",
                    events.c.subject_id.in_(proposal_ids),
                )
            )
        named = {r["subject_id"]: (r["data"] or {}).get("note") for r in rows}
        return {p: str(named.get(p) or p) for p in proposal_ids}

    # ---------------------------------------------------------------- actions

    def retry(self, who: Principal, item_id: str) -> Task:
        """Read a capture again after its run failed, with the same model: a failure never
        moves the work to another provider."""
        if self.status(who, [item_id])[item_id].status != "failed":
            raise Conflict("Only a capture whose reading failed can be tried again.")
        requests = self.distill.requests(who, item_id=item_id, limit=20)
        failed = next(r for r in requests if r.status in FAILED)
        return self.distill.request(who, item_ids=[item_id], assignee_id=failed.assignee_id)

    def exclude(self, who: Principal, item_id: str, *, reason: str = "") -> SourceStatus:
        """Keep a capture out of the Brain: it is never read for it until included."""
        reason = " ".join(str(reason or "").split())[:200]
        if not reason:
            raise ValidationFailed("Say why it stays out, in a few words.", field="reason")
        self._set_excluded(who, item_id, {"reason": reason, "by": who.actor_id})
        return self.status(who, [item_id])[item_id]

    def include(self, who: Principal, item_id: str) -> SourceStatus:
        self._set_excluded(who, item_id, None)
        return self.status(who, [item_id])[item_id]

    def _set_excluded(self, who: Principal, item_id: str, value: dict[str, Any] | None) -> None:
        who.require("context.write")
        with self.rt.write() as tx:
            row = self._row(tx, who, item_id)
            provenance = dict(row["provenance"] or {})
            if value is None:
                if not provenance.pop("excluded", None):
                    raise Conflict("It is not excluded.")
            else:
                provenance["excluded"] = {**value, "at": tx.now}
            tx.update(schema.context_items, row, {"provenance": provenance})
            tx.emit(
                "capture.excluded" if value else "capture.included",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                reason=(value or {}).get("reason") or None,
                data={},
            )

    def _row(self, tx: Any, who: Principal, item_id: str) -> dict[str, Any]:
        row = tx.get(schema.context_items, str(item_id or ""))
        if row is None or row["workspace_id"] != self.rt.workspace_id or not open_to(tx, who, row):
            raise NotFound(f"No capture with id {item_id}.", id=item_id)
        return dict(row)


def _made(item_id: str, status: str, **fields: Any) -> SourceStatus:
    return SourceStatus(
        item_id=item_id, status=status, label=LABELS[status], stage=STAGE_OF[status], **fields
    )
