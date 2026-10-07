"""The MCP tools a model uses for the AI work the app starts: take a task, read what it
needs, propose to the Brain, finish (spec section 16).

Each tool is a thin call into the Workspace facade. Identity comes from the authenticated
credential; no tool takes an actor, and none can reach another model's queue. A person's notes
reach a model only pinned to its own task: search never finds them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.errors import ValidationFailed
from workspace_core.workspace import Workspace

from . import render

Handler = Callable[[Workspace, Principal, dict[str, Any]], tuple[str, dict[str, Any]]]

KEY = {
    "type": "string",
    "description": "Optional idempotency key: a retry with the same key "
    "returns the first result instead of doing the work twice.",
}
RUN = {"type": "string", "description": "The run_id returned by claim_task."}
PAGE = 40000  # characters of one working item per get_context_item call


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Handler
    action: str  # the permission the tool needs at minimum

    def listing(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "inputSchema": self.schema}


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _str(args: dict[str, Any], key: str, required: bool = False) -> str | None:
    value = args.get(key)
    if value is None or value == "":
        if required:
            raise ValidationFailed(f"`{key}` is required.", field=key)
        return None
    return str(value)


# ---------------------------------------------------------------------- handlers


def get_due_tasks(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    due = ws.bus.due(who, limit=int(args.get("limit") or 20))
    tasks = [t.to_dict() for t in due.tasks]
    runs = [
        {k: r.to_dict()[k] for k in ("id", "task_id", "attempt", "status", "lease_expires_at")}
        for r in due.active_runs
    ]
    return render.due(tasks, runs), {"tasks": tasks, "active_runs": runs}


def claim_task(ws: Workspace, who: Principal, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    lease = args.get("lease_seconds")
    claim = ws.bus.claim(
        who,
        str(_str(args, "task_id", True)),
        lease_seconds=int(lease) if lease else None,
        idempotency_key=_str(args, "idempotency_key"),
    )
    return render.packet(claim.packet), {"run": claim.run.to_dict(), "packet": claim.packet}


def get_task_packet(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    packet = ws.bus.packet(who, task_id=_str(args, "task_id"), run_id=_str(args, "run_id"))
    return render.packet(packet), {"packet": packet}


def append_task_event(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    event = ws.bus.append(
        who,
        str(_str(args, "run_id", True)),
        type=str(_str(args, "type", True)),
        message=str(args.get("message") or ""),
        data=args.get("data") if isinstance(args.get("data"), dict) else None,
        idempotency_key=_str(args, "idempotency_key"),
    )
    text = f"Recorded {event.type}."
    if event.type == "run.heartbeat":
        text = f"Lease renewed until {event.data.get('lease_expires_at')}."
    elif event.type == "task.blocked":
        text = "The task is blocked; a person will see your reason. Move to other work."
    return text, {"event": event.to_dict()}


def complete_task(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    run = ws.bus.complete(
        who,
        str(_str(args, "run_id", True)),
        summary=str(args.get("summary") or ""),
        outcome=str(args.get("outcome") or "succeeded"),
        idempotency_key=_str(args, "idempotency_key"),
        left_out=args.get("left_out") if isinstance(args.get("left_out"), list) else None,
    )
    task = ws.tasks.get(who, run.task_id)
    after = {
        "review": "It is waiting for a person's review.",
        "done": "The task is done.",
        "failed": "The task is marked failed.",
    }
    return (
        f"Run {run.id} closed and the lease released. "
        f"{after.get(task.status, f'The task is {task.status}.')}",
        {"run": run.to_dict(), "task_status": task.status},
    )


def search_context(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    query = str(_str(args, "query", True))
    limit = int(args.get("limit") or 8)
    items = ws.context.search(
        who,
        query,
        scope=_str(args, "scope"),
        limit=limit,
        include_archived=bool(args.get("include_archived")),
    )
    hits = ws.brain.search(who, query, limit) if who.can("brain.read") else []
    lines = []
    for item in items:
        snippet = " ".join((item.body or item.text_shadow or "").split())[:160]
        lines.append(
            f"- [working] {item.title} (context_item:{item.id}, {item.scope}, "
            f"version {item.revision}): {snippet}"
        )
    for hit in hits:
        lines.append(f"- [brain] {hit.title} (brain_entry:{hit.id}, {hit.scope}): {hit.summary}")
    text = (
        "\n".join(lines) + "\n\nOpen one with get_context_item or get_brain_entry."
        if lines
        else f"Nothing matches {query!r}. Try other words."
    )
    return text, {
        "context_items": [i.to_dict() for i in items],
        "brain_entries": [asdict(h) for h in hits],
    }


def get_context_item(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    item = ws.context.get(who, str(_str(args, "item_id", True)).removeprefix("context_item:"))
    text = item.body or ""
    if item.text_shadow:
        text += ("\n\n" if text else "") + f"Text of {item.filename}:\n{item.text_shadow}"
    try:
        offset = max(0, int(args.get("offset") or 0))
    except (TypeError, ValueError) as exc:
        raise ValidationFailed("offset is a whole number.", field="offset") from exc
    chunk = text[offset : offset + PAGE]
    end = offset + len(chunk)
    parts = [
        f"# {item.title}",
        f"context_item:{item.id}, {item.kind}, {item.scope}, version {item.revision}",
        "",
    ]
    if item.url:
        parts.append(f"Link: {item.url}")
    if chunk:
        parts.append(chunk)
    more = end < len(text)
    if more or offset:
        parts += [
            "",
            f"(characters {offset} to {end} of {len(text)}"
            + (f"; call get_context_item again with offset={end} for the rest)" if more else ")"),
        ]
    about = {k: v for k, v in item.to_dict().items() if k not in ("body", "text_shadow")}
    return "\n".join(parts), {
        "item": about,
        "text": chunk,
        "offset": offset,
        "next_offset": end if more else None,
        "length": len(text),
    }


def get_brain_entry(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    entry_id = str(_str(args, "entry_id", True)).removeprefix("brain_entry:")
    entry = ws.brain.entry(who, entry_id)
    if entry is None:
        raise ValidationFailed(f"No Brain entry {entry_id} is visible.", field="entry_id")
    head = f"# {entry.title}\nbrain_entry:{entry.id}, {entry.kind}, {entry.scope}"
    if entry.stale:
        head += "\nWarning: marked stale."
    return f"{head}\n\n{entry.text}", {"entry": asdict(entry)}


def get_brain_skill(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    name = str(_str(args, "name", True))
    skill = ws.brain.skill(who, name)
    if skill is None:
        raise ValidationFailed(f"No Brain procedure {name} is visible.", field="name")
    return skill.text, {"skill": asdict(skill)}


def get_brain_reference(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    path = str(_str(args, "path", True))
    document = ws.brain.reference(who, path)
    if document is None:
        raise ValidationFailed(f"No Brain reference {path} is visible.", field="path")
    return document.text, {"reference": asdict(document)}


def propose_brain_entry(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    result = ws.brain.propose(
        who,
        title=str(_str(args, "title", True)),
        statement=str(_str(args, "statement", True)),
        kind=str(args.get("kind") or "fact"),
        scope=_str(args, "scope"),
        evidence=str(args.get("evidence") or ""),
        sources=[str(s) for s in args.get("sources") or []],
        run_id=_str(args, "run_id"),
        idempotency_key=_str(args, "idempotency_key"),
        replaces=_ids(args, "replaces"),
        contradicts=_ids(args, "contradicts"),
        topic=_str(args, "topic"),
        revises=_str(args, "revises"),
        summary=_str(args, "summary"),
        goal=_str(args, "goal"),
        project=_str(args, "project"),
    )
    return result.message, {"proposal": asdict(result)}


def save_digest(ws: Workspace, who: Principal, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    digest = ws.captures.save_digest(
        who,
        run_id=str(_str(args, "run_id", True)),
        item_id=str(_str(args, "item_id", True)),
        summary=str(_str(args, "summary", True)),
        points=list(args.get("points") or []),
        decisions=list(args.get("decisions") or []),
        actions=list(args.get("actions") or []),
        questions=list(args.get("questions") or []),
        people=list(args.get("people") or []),
        about=str(args.get("about") or ""),
        new_project=str(args.get("new_project") or ""),
        off_goal=str(args.get("off_goal") or ""),
    )
    return (
        f"Saved the digest ({len(digest['points'])} key points). It is shown beside the item; "
        "now complete the task.",
        {"digest": digest},
    )


def save_skill_result(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    saved = ws.skills.save_result(
        who,
        run_id=str(_str(args, "run_id", True)),
        title=str(args.get("title") or ""),
        text=str(_str(args, "text", True)),
    )
    return (
        f"Saved \u201c{saved['title']}\u201d (version {saved['version']}). It shows on the "
        "skill's page; now complete the task.",
        {"result": saved},
    )


def propose_brain_skill(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    edits = args.get("edits")
    if edits is not None and not isinstance(edits, list):
        raise ValidationFailed("edits is a list of {find, replace}.", field="edits")
    result = ws.skills.propose(
        who,
        run_id=str(_str(args, "run_id", True)),
        body=_str(args, "body"),
        edits=edits,
        target=_str(args, "target"),
        name=_str(args, "name"),
        category=_str(args, "category"),
        description=_str(args, "description"),
        when_to_use=_str(args, "when_to_use"),
        triggers=_strings(args, "triggers"),
        artifacts=_strings(args, "artifacts"),
        loads=_strings(args, "loads"),
        reason=str(args.get("reason") or ""),
    )
    text = result.message
    if result.status == "pending":
        text += " Now complete the task."
    return text, {"proposal": asdict(result)}


def _strings(args: dict[str, Any], name: str) -> list[str] | None:
    """A list of short texts, given as a list or (as some clients send one) a single string."""
    value = args.get(name)
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    raise ValidationFailed(f"{name} is a list of short texts.", field=name)


def _ids(args: dict[str, Any], name: str) -> list[str] | None:
    """Entry ids, given as a list or (as some clients send one) a single string."""
    value = args.get(name)
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    raise ValidationFailed(f"{name} is a list of entry ids.", field=name)


# ---------------------------------------------------------------------- registry

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "get_due_tasks",
            "Work assigned to you that is ready and due now, most overdue first, plus runs "
            "you still hold. Start every scheduled check here.",
            _obj({"limit": {"type": "integer", "minimum": 1, "maximum": 50}}),
            get_due_tasks,
            "tasks.claim",
        ),
        Tool(
            "claim_task",
            "Claim one due task for a bounded lease. Returns the run_id and the full task "
            "packet: purpose, instructions, pinned inputs, Brain context, output contract. "
            "A refused claim means someone else has it or it is not due: skip it.",
            _obj(
                {
                    "task_id": {"type": "string"},
                    "lease_seconds": {"type": "integer", "minimum": 30, "maximum": 14400},
                    "idempotency_key": KEY,
                },
                ["task_id"],
            ),
            claim_task,
            "tasks.claim",
        ),
        Tool(
            "get_task_packet",
            "The packet of your run (exactly as it was at claim time), or the packet a task "
            "would get now.",
            _obj({"run_id": RUN, "task_id": {"type": "string"}}),
            get_task_packet,
            "tasks.read",
        ),
        Tool(
            "append_task_event",
            "Add to your run: progress (starts the work), evidence, note, context_used "
            "(data.refs), heartbeat (renews the lease; data.lease_seconds optional) or "
            "blocker (a concrete reason a person must act on; ends the run).",
            _obj(
                {
                    "run_id": RUN,
                    "type": {
                        "type": "string",
                        "enum": [
                            "progress",
                            "evidence",
                            "note",
                            "context_used",
                            "heartbeat",
                            "blocker",
                        ],
                    },
                    "message": {"type": "string"},
                    "data": {"type": "object"},
                    "idempotency_key": KEY,
                },
                ["run_id", "type"],
            ),
            append_task_event,
            "runs.write",
        ),
        Tool(
            "complete_task",
            "Close your run and release the lease. outcome is succeeded (default) or failed. "
            "The task then waits for review, is done, or is marked failed.",
            _obj(
                {
                    "run_id": RUN,
                    "summary": {"type": "string"},
                    "outcome": {"type": "string", "enum": ["succeeded", "failed"]},
                    "left_out": {
                        "type": "array",
                        "description": "When the task pulls context: what you considered and "
                        "did not propose, each with why, so the person can still pull it.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "statement": {"type": "string"},
                                "why": {"type": "string"},
                            },
                            "required": ["statement"],
                        },
                    },
                    "idempotency_key": KEY,
                },
                ["run_id"],
            ),
            complete_task,
            "runs.write",
        ),
        Tool(
            "search_context",
            "Search the Brain's long-term entries, and working material you can see, in your "
            "own words. A person's notes are not searchable: they reach you pinned to a task.",
            _obj(
                {
                    "query": {"type": "string"},
                    "scope": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                    "include_archived": {"type": "boolean"},
                },
                ["query"],
            ),
            search_context,
            "context.read",
        ),
        Tool(
            "get_context_item",
            "Read one pinned input (a note, a document) in full, 40,000 characters at a time: "
            "a longer one says which offset to ask for next.",
            _obj(
                {
                    "item_id": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                },
                ["item_id"],
            ),
            get_context_item,
            "context.read",
        ),
        Tool(
            "get_brain_entry",
            "Read one long-term Brain entry in full.",
            _obj({"entry_id": {"type": "string"}}, ["entry_id"]),
            get_brain_entry,
            "brain.read",
        ),
        Tool(
            "get_brain_skill",
            "Read one of the Brain's procedures (skills) in full, with what it loads. Packets "
            "list the candidates for a task under 'Skill candidates'.",
            _obj({"name": {"type": "string"}}, ["name"]),
            get_brain_skill,
            "brain.read",
        ),
        Tool(
            "get_brain_reference",
            "Read a long reference document the Brain holds (a path such as "
            "references/style-guide.md).",
            _obj({"path": {"type": "string"}}, ["path"]),
            get_brain_reference,
            "brain.read",
        ),
        Tool(
            "propose_brain_entry",
            "Propose durable, long-term context (a fact, rule, preference or decision that "
            "will still matter next month). It waits for a person's approval. Quote the "
            "evidence and name the sources (refs). Check the Brain first (search_context): "
            "when it replaces an entry, say so with replaces; when it contradicts one and you "
            "cannot tell which is current, say so with contradicts. During a task, pass its "
            "run_id so the proposal is credited to that task (a distillation request asks for "
            "exactly this).",
            _obj(
                {
                    "title": {
                        "type": "string",
                        "description": "A few plain words naming what it is about, as someone "
                        "would search for it; no internal jargon.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "One line in plain words, at most 200 characters, "
                        "saying what it holds, so a reader scanning a list knows whether to "
                        "open it. Not the statement's first sentence cut short.",
                    },
                    "statement": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["fact", "rule", "preference", "decision", "procedure"],
                    },
                    "scope": {"type": "string"},
                    "evidence": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Refs it came from (context_item:<id>), and brain:<entry "
                        "id> for entries you checked it against.",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Where it belongs, as area/topic (for example "
                        "company/offers): where related entries already live.",
                    },
                    "replaces": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ids of entries this one replaces: they are archived "
                        "when it is approved, so it must say everything they said that still "
                        "holds.",
                    },
                    "contradicts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ids of entries this one contradicts when the sources "
                        "do not settle which is current. A person decides.",
                    },
                    "revises": {
                        "type": "string",
                        "description": "The id of one existing entry this is a new text for "
                        "(a change to that entry, not a new one). The statement is the entry's "
                        "whole new text.",
                    },
                    "goal": {
                        "type": "string",
                        "description": "The owner's goal it serves, in a few words, from their "
                        "goals for the Brain.",
                    },
                    "project": {
                        "type": "string",
                        "description": "The id of the active project it belongs to: it is kept "
                        "with that project.",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "The run_id from claim_task, when proposing as part of "
                        "a task.",
                    },
                    "idempotency_key": KEY,
                },
                ["title", "statement"],
            ),
            propose_brain_entry,
            "brain.propose",
        ),
        Tool(
            "save_digest",
            "Save the digest of the item a digest task reads (its template is digest): a short "
            "summary, its key points each marked by how it fits what the Brain holds now, and "
            "the decisions, actions, open questions and people in it. It is shown beside the "
            "item; nothing reaches the Brain from it.",
            _obj(
                {
                    "run_id": RUN,
                    "item_id": {
                        "type": "string",
                        "description": "The id of the pinned item (context_item:<id> without "
                        "the prefix).",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Two or three plain sentences: what it is and what "
                        "came of it.",
                    },
                    "points": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "fit": {
                                    "type": "string",
                                    "enum": ["new", "repeats", "updates", "clashes"],
                                },
                                "entry": {
                                    "type": "string",
                                    "description": "The Brain entry it repeats, updates or "
                                    "clashes with.",
                                },
                                "why": {"type": "string"},
                                "serves": {
                                    "type": "string",
                                    "description": "The project it moves forward, or "
                                    '"goals" when it serves what the Brain is for without one.',
                                },
                            },
                            "required": ["text", "fit"],
                        },
                    },
                    "decisions": {"type": "array", "items": {"type": "string"}},
                    "actions": {"type": "array", "items": {"type": "string"}},
                    "questions": {"type": "array", "items": {"type": "string"}},
                    "people": {"type": "array", "items": {"type": "string"}},
                },
                ["run_id", "item_id", "summary"],
            ),
            save_digest,
            "runs.write",
        ),
        Tool(
            "save_skill_result",
            "Save what a skill run made (a task whose template is skill): a short title and "
            "the whole result as Markdown, ready to use. It is shown on the skill's page; "
            "saved again in the same run, it becomes a new version of the same result.",
            _obj(
                {
                    "run_id": RUN,
                    "title": {"type": "string", "description": "A few words naming it."},
                    "text": {
                        "type": "string",
                        "description": "The whole result as Markdown: the post, the outline, "
                        "the email; for a run that made files, each file and what it is.",
                    },
                },
                ["run_id", "text"],
            ),
            save_skill_result,
            "runs.write",
        ),
        Tool(
            "propose_brain_skill",
            "Propose a skill from a task whose template is skill-draft: a new version of one "
            "(target: its name, the change as edits) or a new skill (name, category, "
            "description and body). It waits in Review for a person; nothing changes until "
            "they approve it.",
            _obj(
                {
                    "run_id": RUN,
                    "target": {
                        "type": "string",
                        "description": "The skill this is a new version of. Leave out for a "
                        "new skill.",
                    },
                    "name": {
                        "type": "string",
                        "description": "A new skill's name: lowercase words joined by hyphens.",
                    },
                    "category": {"type": "string", "description": "A new skill's group."},
                    "description": {
                        "type": "string",
                        "description": "What it makes and when to use it, in a sentence or two.",
                    },
                    "when_to_use": {"type": "string"},
                    "triggers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Short phrases a person says to ask for it.",
                    },
                    "artifacts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "What it makes: post, email, pdf, docx, pptx.",
                    },
                    "loads": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The Brain topics (brand/voice) and references/ "
                        "documents it reads.",
                    },
                    "edits": {
                        "type": "array",
                        "maxItems": 30,
                        "description": "A change to an existing skill: passages quoted exactly "
                        "from its procedure, each with what replaces it. Applied in order to "
                        "the skill as it is now; each passage must occur once.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string"},
                                "replace": {"type": "string"},
                            },
                            "required": ["find", "replace"],
                        },
                    },
                    "body": {
                        "type": "string",
                        "description": "The whole procedure as Markdown, without frontmatter: "
                        "for a new skill (starting with its '# /<name>' heading), or when most "
                        "of an existing one changes.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "What changed and why, in a sentence or two.",
                    },
                },
                ["run_id"],
            ),
            propose_brain_skill,
            "brain.propose",
        ),
    )
}


def visible(who: Principal) -> list[Tool]:
    return [tool for tool in TOOLS.values() if who.can(tool.action)]
