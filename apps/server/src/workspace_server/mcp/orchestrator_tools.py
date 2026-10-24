"""The app's MCP tools for agent orchestrators (AGENTS.md 8b, MCP Tools.md "Agent
orchestrators"): list, get, save, run and the timeline for any connected AI; context, spawn,
sheet_fill and finish for a run's orchestrator; agent_context and report for its agents; and
outputs_save, where a run's output lands in the project's Outputs.

Who calls is told by the run's own credential (orchestration.py), never by an argument.
"""

from __future__ import annotations

from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, ValidationFailed
from workspace_core.workspace import Workspace

from .tools import Tool, _obj, _str

# Set by the app when it starts: runs orchestrators and starts each one's CLIs.
ORCHESTRATION: Any = None


def _orc(who: Principal, action: str) -> Any:
    who.require(action)
    if ORCHESTRATION is None:
        raise Conflict("Agent orchestrators are not running here.")
    return ORCHESTRATION


def _quote(args: dict[str, Any]) -> str:
    said = args.get("confirmed_by_user")
    quote = str((said or {}).get("quote") or "").strip() if isinstance(said, dict) else ""
    if not quote:
        raise ValidationFailed(
            "Ask the owner first, in one plain sentence. When they agree, call again with "
            'confirmed_by_user: {"quote": "<their exact words>"}.',
            field="confirmed_by_user",
            status="needs_user_confirmation",
        )
    return quote


def _line(o: dict[str, Any]) -> str:
    run = o.get("latest_run") or {}
    agents = ", ".join(f"{a['profile']} (owns {a['short']})" for a in o["agents"]) or "no agents"
    state = f"; last run {run['id']}: {run['shown']}" if run else "; not run yet"
    goal = o["goal"] or "none yet"
    return f"- {o['slug']} ({o['id']}): {o['name']}. Goal: {goal}. {agents}{state}"


def _reports(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {r['profile']}: {r['title']} ({r['output_id']}). {r['summary']}" for r in items
    )


def _action(args: dict[str, Any]) -> dict[str, Any] | None:
    action = args.get("action")
    return action if isinstance(action, dict) and action else None


def _list(args: dict[str, Any], key: str) -> list[Any] | None:
    value = args.get(key)
    return value if isinstance(value, list) else None


def _gated(done: dict[str, Any], plain: str) -> tuple[str, dict[str, Any]]:
    if done.get("status") == "needs_user_confirmation":
        return (
            f"needs_user_confirmation: “{done['gate']['what']}” waits for the owner's yes in "
            "Gnomon. Do not do it: it runs after the yes, in a run of its own. Report waiting.",
            done,
        )
    return plain, done


# ---------------------------------------------------------------------- any connected AI


def orchestrators_list(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    found = _orc(who, "tasks.read").overview(who, str(_str(args, "project", True)))
    lines = [_line(o) for o in found["orchestrators"]]
    return "\n".join(lines) or "This project has no orchestrators yet.", found


def orchestrators_get(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    orc = _orc(who, "tasks.read")
    pid = orc.project_id(who, str(_str(args, "project", True)))
    if pid is None:
        raise NotFound("This project has no orchestrators yet.")
    found: dict[str, Any] = orc.core.find(who, pid, str(_str(args, "orchestrator", True)))
    return _line(found), found


def orchestrators_save(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    orc = _orc(who, "tasks.claim")
    _quote(args)
    spec = args.get("spec")
    if not isinstance(spec, dict):
        raise ValidationFailed("spec is an object: name, goal, cli, model, agents.", field="spec")
    saved: dict[str, Any] = orc.save(
        ws.owner(),
        str(_str(args, "project", True)),
        spec,
        orchestrator_id=_str(args, "orchestrator_id"),
    )
    return f"Saved {saved['name']} ({saved['slug']}). New agent profiles are in Agents.", saved


def orchestrators_run(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    orc = _orc(who, "tasks.claim")
    run: dict[str, Any] = orc.run(
        ws.owner(),
        str(_str(args, "project", True)),
        str(_str(args, "orchestrator", True)),
        steer=str(args.get("steer") or ""),
        trigger="ai",
        asked_by=who.name,
    )
    if run["shown"] == "stopped":
        return f"Run {run['id']} stopped: {run['note']}", run
    return (
        f"Started run {run['id']} of {run['spec']['name']}. It is the same run and timeline "
        "the owner sees in Gnomon; anything that spends, posts or is customer-facing waits "
        "for their yes there.",
        run,
    )


def orchestrators_timeline(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    orc = _orc(who, "tasks.read")
    pid = orc.project_id(who, str(_str(args, "project", True)))
    events = orc.core.timeline(who, pid, run_id=_str(args, "run_id")) if pid else []
    lines = [f"- {e['at']} {e['kind']}: {e['text']}" for e in events[:60]]
    return "\n".join(lines) or "Nothing yet.", {"events": events}


# ---------------------------------------------------------------------- a run's orchestrator


def orchestrators_context(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    found: dict[str, Any] = _orc(who, "runs.write").context(
        who, str(_str(args, "run_id", True)), wait=bool(args.get("wait"))
    )
    agents = "\n".join(
        f"- {a['id']}: {a['profile']}, {a['state']}. Role: {a['role']} Works by {a['works_by']}."
        for a in found["agents"]
    )
    text = (
        f"Run {found['run_id']} of {found['name']}: {found['status']}.\nGoal: {found['goal']}\n"
        + (f"Steer: {found['steer']}\n" if found["steer"] else "")
        + f"Agents:\n{agents}\nReports:\n{_reports(found['reports']) or '- none yet'}\n"
        + f"Sheet: {found['sheet']}\n{found['rules']}"
    )
    return text, found


def orchestrators_spawn(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    agent_id = str(_str(args, "agent_id", True))
    done: dict[str, Any] = _orc(who, "runs.write").spawn(
        who, str(_str(args, "run_id", True)), agent_id, str(args.get("brief") or "")
    )
    note = (done["run"]["agents"].get(agent_id) or {}).get("note") or ""
    text = {
        "working": "Spawned. It works on its own CLI and reports back; wait for it with "
        "orchestrators_context and wait set to true.",
        "waiting": f"It could not start from here and waits for the owner: {note}",
        "stopped": f"It could not start: {note}",
    }.get(str(done["state"]), "Spawned.")
    return text, done


def orchestrators_sheet_fill(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    done: dict[str, Any] = _orc(who, "runs.write").fill(
        who, str(_str(args, "run_id", True)), _list(args, "rows") or []
    )
    return f"Filled {done['filled']} cells in {done['sheet']}.", done


def orchestrators_finish(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    done: dict[str, Any] = _orc(who, "runs.write").finish(
        who,
        str(_str(args, "run_id", True)),
        output_id=str(_str(args, "final_output_id", True)),
        summary=str(args.get("summary") or ""),
        sources=_list(args, "sources"),
        action=_action(args),
    )
    return _gated(done, "Pinned as the run's final output. Now complete your task.")


# ---------------------------------------------------------------------- a spawned agent


def orchestrators_agent_context(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    found: dict[str, Any] = _orc(who, "runs.write").agent_context(
        who, str(_str(args, "run_id", True)), str(_str(args, "agent_id", True))
    )
    act = found["approved_action"]
    text = (
        f"You are {found['profile']}. Your role: {found['role']}\nHow you work: {found['how']}\n"
        f"The run's goal: {found['goal']}\n"
        + (f"Steer: {found['steer']}\n" if found["steer"] else "")
        + (f"Your brief: {found['brief']}\n" if found["brief"] else "")
        + (f"The approved action, and only this: {act['what']}\n" if act else "")
        + f"What the others reported:\n{_reports(found['inputs']) or '- nothing yet'}\n"
        + found["rules"]
    )
    return text, found


def orchestrators_report(
    ws: Workspace, who: Principal, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    done: dict[str, Any] = _orc(who, "runs.write").report(
        who,
        str(_str(args, "run_id", True)),
        str(_str(args, "agent_id", True)),
        output_id=str(_str(args, "output_id", True)),
        summary=str(args.get("summary") or ""),
        sources=_list(args, "sources"),
        action=_action(args),
    )
    return _gated(done, "Reported. Now complete your task.")


def outputs_save(ws: Workspace, who: Principal, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    who.require("runs.write")
    saved = ws.skills.save_result(
        who,
        run_id=str(_str(args, "run_id", True)),
        title=str(args.get("title") or ""),
        text=str(_str(args, "text", True)),
    )
    output_id = saved["artifact_id"]
    return (
        f"Saved “{saved['title']}” as {output_id} (version {saved['version']}), a draft in the "
        "project's Outputs. Pass its output_id to orchestrators_report or orchestrators_finish.",
        {"output_id": output_id, **saved},
    )


ACTION = {
    "type": "object",
    "description": "What would spend, post or be customer-facing: kind (spend | post | "
    "customer_facing), what (exactly), tools (full names of the connected tools it needs), "
    "approve_label (the yes button, such as “Yes, post it”), and agent_id at finish.",
}
STRINGS = {"type": "array", "items": {"type": "string"}}

TOOLS: list[Tool] = [
    Tool(
        "orchestrators_list",
        "The agent orchestrators of one of the owner's projects: each one's slug, goal, agents "
        "and latest run.",
        _obj({"project": {"type": "string", "description": "The project's id."}}, ["project"]),
        orchestrators_list,
        "tasks.read",
    ),
    Tool(
        "orchestrators_get",
        "One orchestrator by its slug or id: goal, CLI and model, agents (profile, role, works "
        "by, CLI, model), sheet and latest run.",
        _obj(
            {"project": {"type": "string"}, "orchestrator": {"type": "string"}},
            ["project", "orchestrator"],
        ),
        orchestrators_get,
        "tasks.read",
    ),
    Tool(
        "orchestrators_save",
        "Create or change an orchestrator in a project. Needs the owner's yes: ask in one plain "
        "sentence, then pass confirmed_by_user with their exact words. A new agent profile "
        "(new_profile true) is saved to Agents too.",
        _obj(
            {
                "project": {"type": "string"},
                "orchestrator_id": {"type": "string"},
                "spec": {
                    "type": "object",
                    "description": "name, goal, cli (claude | codex | gemini), model, trigger "
                    "(gnomon | ai), agents [{id, profile, new_profile, role, works_by "
                    "(computer | mcp | files), cli, model, tools}]",
                },
                "confirmed_by_user": {
                    "type": "object",
                    "properties": {"quote": {"type": "string"}},
                },
            },
            ["project", "spec", "confirmed_by_user"],
        ),
        orchestrators_save,
        "tasks.claim",
    ),
    Tool(
        "orchestrators_run",
        "Run an orchestrator the owner lets your AI start (“run promo-check, focus on paid”), "
        "with an optional steer. Its CLI starts on the owner's computer: the same run and "
        "timeline they see in Gnomon.",
        _obj(
            {
                "project": {"type": "string"},
                "orchestrator": {"type": "string", "description": "Its slug or id."},
                "steer": {"type": "string"},
            },
            ["project", "orchestrator"],
        ),
        orchestrators_run,
        "tasks.claim",
    ),
    Tool(
        "orchestrators_timeline",
        "What a project's runs did, newest first: plan, spawns, reports, sheet fills, "
        "proposals, approvals and the final.",
        _obj({"project": {"type": "string"}, "run_id": {"type": "string"}}, ["project"]),
        orchestrators_timeline,
        "tasks.read",
    ),
    Tool(
        "orchestrators_context",
        "If you are a run's orchestrator: the goal, the owner's steer, your agents with their "
        "roles, and what they reported. With wait true it returns once something new comes "
        "back (at most 50 seconds).",
        _obj({"run_id": {"type": "string"}, "wait": {"type": "boolean"}}, ["run_id"]),
        orchestrators_context,
        "runs.write",
    ),
    Tool(
        "orchestrators_spawn",
        "Orchestrator only: start one of your agents on its own CLI, with a short brief of its "
        "piece.",
        _obj(
            {
                "run_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "brief": {"type": "string"},
            },
            ["run_id", "agent_id"],
        ),
        orchestrators_spawn,
        "runs.write",
    ),
    Tool(
        "orchestrators_sheet_fill",
        "Orchestrator only: fill your auto sheet in Project > Context. Every row needs what, "
        "value, source and the agent that found it.",
        _obj(
            {
                "run_id": {"type": "string"},
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "what": {"type": "string"},
                            "value": {"type": "string"},
                            "source": {"type": "string"},
                            "agent": {"type": "string"},
                        },
                        "required": ["what", "value", "source", "agent"],
                    },
                },
            },
            ["run_id", "rows"],
        ),
        orchestrators_sheet_fill,
        "runs.write",
    ),
    Tool(
        "orchestrators_finish",
        "Orchestrator only: pin the final output (saved first with outputs_save) with a "
        "summary and its sources. A recommended action that spends, posts or is "
        "customer-facing goes in action, with the agent_id that would do it, and waits for the "
        "owner's yes.",
        _obj(
            {
                "run_id": {"type": "string"},
                "final_output_id": {"type": "string"},
                "summary": {"type": "string"},
                "sources": STRINGS,
                "action": ACTION,
            },
            ["run_id", "final_output_id", "summary"],
        ),
        orchestrators_finish,
        "runs.write",
    ),
    Tool(
        "orchestrators_agent_context",
        "If you are a spawned agent: your role, your brief, the run's goal and what the other "
        "agents reported.",
        _obj(
            {"run_id": {"type": "string"}, "agent_id": {"type": "string"}},
            ["run_id", "agent_id"],
        ),
        orchestrators_agent_context,
        "runs.write",
    ),
    Tool(
        "orchestrators_report",
        "A spawned agent reports: the output_id from outputs_save, a one-line summary and its "
        "sources. Anything that spends money, posts or is customer-facing goes in action and "
        "comes back needs_user_confirmation: do not do it.",
        _obj(
            {
                "run_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "output_id": {"type": "string"},
                "summary": {"type": "string"},
                "sources": STRINGS,
                "action": ACTION,
            },
            ["run_id", "agent_id", "output_id", "summary"],
        ),
        orchestrators_report,
        "runs.write",
    ),
    Tool(
        "outputs_save",
        "Save what you made in this run (the whole text, as Markdown) as a draft in the "
        "project's Outputs; returns its output_id.",
        _obj(
            {
                "run_id": {"type": "string", "description": "The run_id from claim_task."},
                "title": {"type": "string"},
                "text": {"type": "string"},
            },
            ["run_id", "text"],
        ),
        outputs_save,
        "runs.write",
    ),
]
