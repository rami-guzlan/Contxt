"""Markdown a model reads: run packets and short tool results."""

from __future__ import annotations

from typing import Any


def packet(p: dict[str, Any]) -> str:
    """A run's packet as a model-readable brief, with the exact calls to finish it."""
    task, run = p.get("task") or {}, p.get("run")
    purpose = p.get("purpose") or {}
    lines = [f"# Run: {task.get('title')}", ""]
    ids = f"task_id: {task.get('id')} (revision {task.get('revision')})"
    if run:
        ids += (
            f"\nrun_id: {run['id']} (attempt {run['attempt']}, lease until "
            f"{run['lease_expires_at']})"
        )
    lines += [ids, ""]
    if purpose.get("project") or purpose.get("text"):
        lines.append("## Purpose")
        if purpose.get("project"):
            project = purpose["project"]
            lines.append(
                f"Project: {project['title']}"
                + (f": {project['summary']}" if project.get("summary") else "")
            )
        if purpose.get("text"):
            lines.append(purpose["text"])
        lines.append("")
    instructions = p.get("instructions") or {}
    lines += [
        f"## Instructions (prompt version {instructions.get('prompt_version')})",
        instructions.get("text") or "(none)",
        "",
    ]
    notes = p.get("review_notes") or []
    if notes:
        lines.append("## Review notes from the last attempt")
        for note in notes:
            where = (
                f" on artifact {note['artifact_id']} v{note['version']}"
                if note.get("artifact_id")
                else ""
            )
            lines.append(f"- {note['decision'].replace('_', ' ')}{where}: {note['note']}")
        lines.append("")
    inputs = p.get("inputs") or []
    if inputs:
        lines.append("## Pinned inputs")
        for item in inputs:
            if item.get("missing"):
                lines.append(f"### {item['ref']} (missing)")
                continue
            head = f"### {item.get('title')} ({item['ref']}, version {item.get('version')})"
            lines.append(head)
            if item.get("note"):
                lines.append(f"Why it is pinned: {item['note']}")
            if item.get("url"):
                lines.append(f"Link: {item['url']}")
            if item.get("file"):
                file = item["file"]
                lines.append(
                    f"File: {file.get('filename')} ({file.get('mime')}, {file.get('size')} bytes)"
                )
            if item.get("stale"):
                lines.append("Warning: this Brain entry is marked stale.")
            if item.get("text"):
                lines += ["", item["text"]]
            if item.get("truncated"):
                lines.append("(truncated; open it with get_context_item for the rest)")
            lines.append("")
    brain = p.get("brain") or {}
    if brain.get("text"):
        lines += ["## Long-term context from the Brain", brain["text"].strip(), ""]
    elif brain.get("note"):
        lines += ["## Long-term context", brain["note"], ""]
    contract = p.get("output_contract") or {}
    lines.append("## Output contract")
    for artifact in contract.get("artifacts") or []:
        count = f"{artifact['count']} x " if artifact.get("count") else ""
        extra = f": {artifact['notes']}" if artifact.get("notes") else ""
        lines.append(f"- {count}{artifact['type']}{extra}")
    if contract.get("notes"):
        lines.append(contract["notes"])
    if not contract.get("artifacts") and not contract.get("notes"):
        lines.append("- Nothing to save; report the outcome in complete_task.")
    review = (
        "a person reviews the results"
        if p.get("review_policy") == "required"
        else "completes without review"
    )
    lines.append(f"Review: {review}.")
    lines.append("")
    if run:
        tool = contract.get("tool")
        steps = [f'{tool}(run_id="{run["id"]}", ...), as the instructions say'] if tool else []
        steps.append(f'complete_task(run_id="{run["id"]}", summary="...")')
        lines += ["## Finish", *(f"{n}. {step}" for n, step in enumerate(steps, 1))]
        lines.append(
            f'If blocked: append_task_event(run_id="{run["id"]}", type="blocker", '
            'message="what a person must do")'
        )
    return "\n".join(lines).strip() + "\n"


def due(tasks: list[dict[str, Any]], runs: list[dict[str, Any]]) -> str:
    lines = []
    if tasks:
        lines.append(f"{len(tasks)} run(s) due for you, most overdue first:")
        for t in tasks:
            due_at = t.get("next_due_at") or "now"
            lines.append(
                f"- {t['title']} (task_id {t['id']}, due {due_at}, review {t['review_policy']})"
            )
        lines.append("")
        lines.append('Claim one with claim_task(task_id=..., idempotency_key="<task_id>:<due>").')
    else:
        lines.append("No work is due for you right now.")
    if runs:
        lines.append("")
        lines.append("You still hold these runs (finish or they expire):")
        for r in runs:
            lines.append(
                f"- run_id {r['id']} (task_id {r['task_id']}), lease until {r['lease_expires_at']}"
            )
    return "\n".join(lines)
