"""Agents over REST: roles written like a job description and kept in the Brain. List them,
write and save one (the owner's change, with an undo point), have the chosen model write its
operating prompt (in the background; poll /api/brain/agent/jobs/{id}), read the prompt a model
gets for it, ask it for something (a run like a skill run), see what it made, and add it to
Claude Code as a subagent that always fetches the current version from the Brain."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

from workspace_core.domain.records import Task
from workspace_core.errors import Conflict

from ..deps import WS, Who
from ..knowledge_agent import AgentWork
from ..schemas import AgentAskIn, AgentPromptIn, AgentSaveIn

router = APIRouter(prefix="/api/agents")

FORM = (
    "role",
    "responsibilities",
    "goals",
    "projects",
    "skills",
    "library",
    "context",
    "meetings_days",
    "boundaries",
    "output",
    "output_shape",
    "runner",
    "review",
)


def work(request: Request) -> AgentWork:
    found: AgentWork = request.app.state.runtime.agent
    return found


def _form(body: Any) -> dict[str, Any]:
    return {key: getattr(body, key) for key in FORM}


@router.get("")
def agents(who: Who, ws: WS, archived: bool = False) -> list[dict[str, Any]]:
    """Every agent, with its last run."""
    return ws.agents.list(who, archived=archived)


@router.post("", status_code=201)
def create(body: AgentSaveIn, who: Who, ws: WS) -> dict[str, Any]:
    """Make an agent. Refused when one by that name is there already."""
    if any(a["name"] == body.name.strip().lower() for a in ws.agents.list(who, archived=True)):
        raise Conflict(f"An agent named {body.name} is there already: open it to change it.")
    return ws.agents.save(who, body.name, _form(body), body.prompt)


@router.post("/prompt", status_code=201)
def write_prompt(body: AgentPromptIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Have the chosen model write the operating prompt from the form, in the background.
    Nothing is saved: the owner reads it, edits it and saves it."""
    form = _form(body)
    return (
        work(request)
        .start_work(
            who,
            "agent-prompt",
            lambda: ws.agents.builder_prompt(who, body.name, form),
            ws.agents.read_builder,
            model=body.model,
            message=body.role,
        )
        .to_dict()
    )


@router.get("/{name}")
def agent(name: str, who: Who, ws: WS) -> dict[str, Any]:
    """One agent: its role, each pointer as it is now (and what no longer resolves), and the
    prompt a model gets for it before the brief of a task."""
    return ws.agents.get(who, name)


@router.put("/{name}")
def save(name: str, body: AgentSaveIn, who: Who, ws: WS) -> dict[str, Any]:
    """Change an agent: the owner's change to the Brain, one undo point."""
    return ws.agents.save(who, name, _form(body), body.prompt)


@router.delete("/{name}")
def archive(name: str, who: Who, ws: WS) -> dict[str, Any]:
    """Archive an agent: its file stays in the Brain, with an undo point."""
    return ws.agents.archive(who, name)


@router.get("/{name}/versions")
def versions(name: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    return ws.agents.versions(who, name)


@router.post("/{name}/run", status_code=201)
def run(name: str, body: AgentAskIn, who: Who, ws: WS) -> Task:
    """Ask the agent for something: a run like a skill run, opening with its role."""
    return ws.agents.run(who, name, ask=body.ask, project=body.project)


@router.get("/{name}/runs")
def runs(name: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    return ws.agents.runs(who, name)


@router.post("/{name}/claude-code")
def add_to_claude_code(name: str, who: Who, ws: WS) -> dict[str, Any]:
    """Write a Claude Code subagent for it on this computer (~/.claude/agents/<name>.md). The
    file only says to fetch the agent from the Brain, so Claude Code always gets the current
    version; it needs the Brain connected in Claude Code."""
    who.require("workspace.admin")
    found = ws.agents.get(who, name)["agent"]
    path, text = ws.agents.claude_code_file(found["name"], found["role"])
    existed = os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as out:
        out.write(text)
    return {"path": path, "replaced": existed}
