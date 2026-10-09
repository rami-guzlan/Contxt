"""The task packet: everything a model needs to do the work without reconstructing intent.

Resolved from the task definition, its pins and the Brain. At claim time
the packet is stored on the run, so the run's inputs never change afterwards: newer context
does not rewrite history (spec section 10), and the artifact records exactly which versions it
was built from.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.schedule import Schedule
from workspace_core.ports import BrainContext

from .runtime import Runtime

PACKET_SCHEMA = 1


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _context_item_input(tx: Tx, rt: Runtime, pin: dict[str, Any]) -> dict[str, Any]:
    ref = f"context_item:{pin['ref_id']}"
    item = tx.get(schema.context_items, pin["ref_id"])
    if item is None:
        return {"ref": ref, "missing": True, "note": pin["note"]}
    version = pin["pinned_version"] or item["revision"]
    title, body, object_key, content_hash = (
        item["title"],
        item["body"],
        item["object_key"],
        item["content_hash"],
    )
    if version != item["revision"]:
        revs = schema.context_item_revisions
        old = tx.first(
            sa.select(revs).where(revs.c.item_id == item["id"], revs.c.revision == version)
        )
        if old is None:
            return {"ref": ref, "missing": True, "version": version, "note": pin["note"]}
        title, body, object_key, content_hash = (
            old["title"],
            old["body"],
            old["object_key"],
            old["content_hash"],
        )
    text = body or ""
    if item["text_shadow"] and object_key == item["object_key"]:
        text = (text + "\n\n" + item["text_shadow"]).strip() if text else item["text_shadow"]
    text, clipped = _clip(text, rt.max_input_chars)
    out: dict[str, Any] = {
        "ref": ref,
        "type": item["kind"],
        "title": title,
        "version": version,
        "scope": item["scope_kind"] + (f":{item['scope_id']}" if item["scope_id"] else ""),
        "text": text,
        "content_hash": content_hash,
        "note": pin["note"],
    }
    if clipped:
        out["truncated"] = True
    if item["url"]:
        out["url"] = item["url"]
    if object_key:
        out["file"] = {"filename": item["filename"], "mime": item["mime"], "size": item["size"]}
    return out


def _artifact_input(tx: Tx, rt: Runtime, pin: dict[str, Any]) -> dict[str, Any]:
    ref = f"artifact:{pin['ref_id']}"
    artifact = tx.get(schema.artifacts, pin["ref_id"])
    if artifact is None:
        return {"ref": ref, "missing": True, "note": pin["note"]}
    number = pin["pinned_version"] or artifact["current_version"]
    versions = schema.artifact_versions
    version = tx.first(
        sa.select(versions).where(
            versions.c.artifact_id == artifact["id"], versions.c.number == number
        )
    )
    text, clipped = _clip((version or {}).get("preview_text") or "", rt.max_input_chars)
    out = {
        "ref": ref,
        "type": artifact["type"],
        "title": artifact["title"],
        "version": number,
        "status": artifact["status"],
        "text": text,
        "content_hash": (version or {}).get("content_hash"),
        "note": pin["note"],
    }
    if clipped:
        out["truncated"] = True
    return out


def _brain_input(rt: Runtime, pin: dict[str, Any]) -> dict[str, Any]:
    ref = f"brain_entry:{pin['ref_id']}"
    entry = rt.brain.entry(pin["ref_id"])
    if entry is None:
        return {"ref": ref, "missing": True, "note": pin["note"]}
    text, clipped = _clip(entry.text, rt.max_input_chars)
    out = {
        "ref": ref,
        "type": f"brain:{entry.kind}",
        "title": entry.title,
        "version": entry.revision,
        "scope": entry.scope,
        "text": text,
        "confidence": entry.confidence,
        "verified": entry.verified,
        "stale": entry.stale,
        "note": pin["note"],
    }
    if clipped:
        out["truncated"] = True
    return out


def _project_input(rt: Runtime, pin: dict[str, Any]) -> dict[str, Any]:
    """A project the Brain follows: what it is for, and where it stands now."""
    ref = f"brain_project:{pin['ref_id']}"
    found = rt.brain.project(pin["ref_id"])
    if found is None:
        return {"ref": ref, "missing": True, "note": pin["note"]}
    state = found.get("state") or {}
    parts = [str(found.get("summary") or "").strip()]
    for key, label in (
        ("status", "Status"),
        ("current", "Where it stands"),
        ("next", "Next"),
        ("blockers", "Blocked by"),
    ):
        value = " ".join(str(state.get(key) or "").split())
        if value:
            parts.append(f"{label}: {value}")
    if found.get("aliases"):
        parts.append("Also called: " + ", ".join(str(a) for a in found["aliases"]))
    text, clipped = _clip("\n".join(p for p in parts if p), rt.max_input_chars)
    out = {
        "ref": ref,
        "type": "brain:project",
        "title": str(found.get("title") or pin["ref_id"]),
        "text": text,
        "note": pin["note"],
    }
    if clipped:
        out["truncated"] = True
    return out


def _file_input(rt: Runtime, pin: dict[str, Any]) -> dict[str, Any]:
    """A document filed in the Brain, in full (as far as a run may read)."""
    ref = f"brain_file:{pin['ref_id']}"
    document = rt.brain.reference(pin["ref_id"])
    if document is None:
        return {"ref": ref, "missing": True, "note": pin["note"]}
    text, clipped = _clip(document.text, rt.max_input_chars)
    out = {
        "ref": ref,
        "type": "brain:file",
        "title": str(pin["ref_id"]).rsplit("/", 1)[-1],
        "text": text,
        "note": pin["note"],
    }
    if clipped:
        out["truncated"] = True
    return out


def resolve_inputs(tx: Tx, rt: Runtime, task_id: str) -> list[dict[str, Any]]:
    pins = tx.rows(
        sa.select(schema.task_pins)
        .where(schema.task_pins.c.task_id == task_id)
        .order_by(schema.task_pins.c.created_at)
    )
    inputs = []
    for pin in pins:
        if pin["ref_type"] == "context_item":
            inputs.append(_context_item_input(tx, rt, pin))
        elif pin["ref_type"] == "artifact":
            inputs.append(_artifact_input(tx, rt, pin))
        elif pin["ref_type"] == "brain_entry":
            inputs.append(_brain_input(rt, pin))
        elif pin["ref_type"] == "brain_project":
            inputs.append(_project_input(rt, pin))
        elif pin["ref_type"] == "brain_file":
            inputs.append(_file_input(rt, pin))
    return inputs


def review_notes(tx: Tx, task_id: str) -> list[dict[str, Any]]:
    """What the reviewer said about the previous run's output, for the next attempt."""
    runs = schema.task_runs
    last = tx.first(
        sa.select(runs.c.id).where(runs.c.task_id == task_id).order_by(runs.c.claimed_at.desc())
    )
    if last is None:
        return []
    table = schema.approvals
    rows = tx.rows(
        sa.select(table)
        .where(
            table.c.run_id == last["id"],
            table.c.status.in_(("changes_requested", "rejected")),
        )
        .order_by(table.c.decided_at)
    )
    return [
        {
            "artifact_id": r["subject_id"] if r["subject_type"] == "artifact" else None,
            "decision": r["status"],
            "note": r["decision_note"] or "",
            "version": r["subject_version"],
        }
        for r in rows
    ]


def resolve(
    tx: Tx, rt: Runtime, task: dict[str, Any], run: dict[str, Any] | None = None
) -> dict[str, Any]:
    project = tx.get(schema.projects, task["project_id"]) if task["project_id"] else None
    assignee = tx.get(schema.actors, task["assignee_id"]) if task["assignee_id"] else None
    schedule = Schedule.from_dict(task["schedule"])
    request = task["brain_request"] or "\n".join(
        part for part in (task["title"], task["purpose"], task["instructions"]) if part
    )
    if task["template"] == "challenge":
        # Blind: the beliefs under test are in the instructions, only as claims; a brief would
        # hand them over as what the Brain holds true.
        brain = BrainContext(
            available=False,
            reason="Left out on purpose: test the claims in the instructions on their merits.",
        )
    else:
        brain = rt.brain.context(request)
    packet: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "task": {"id": task["id"], "title": task["title"], "revision": task["revision"]},
        "purpose": {
            "text": task["purpose"],
            "project": {
                "id": project["id"],
                "title": project["title"],
                "summary": project["summary"],
            }
            if project
            else None,
        },
        "instructions": {"text": task["instructions"], "prompt_version": task["prompt_version"]},
        "assignee": {
            "id": assignee["id"],
            "name": assignee["name"],
            "provider": assignee["provider"],
        }
        if assignee
        else None,
        "timing": {
            "schedule": schedule.to_dict(),
            "timezone": task["timezone"],
            "describe": schedule.describe(task["timezone"]),
            "due_at": task["next_due_at"],
        },
        "inputs": resolve_inputs(tx, rt, task["id"]),
        "brain": {
            "available": brain.available,
            "text": brain.text,
            "entry_ids": list(brain.entry_ids),
            # the version of each entry the run is handed, for its outputs' lineage
            "entries": [dict(e) for e in brain.entries],
            "note": brain.reason,
        },
        "output_contract": task["output_contract"],
        "review_policy": task["review_policy"],
        "review_notes": review_notes(tx, task["id"]),
    }
    if run is not None:
        packet["run"] = {
            "id": run["id"],
            "attempt": run["attempt"],
            "occurrence": run["occurrence"],
            "lease_expires_at": run["lease_expires_at"],
        }
    return packet
