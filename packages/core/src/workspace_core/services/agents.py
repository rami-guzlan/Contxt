"""Agents in the workspace: roles the owner writes like a job description, kept in the Brain and
run as AI work like a skill run.

The Brain keeps each agent (`agents/<name>/AGENT.md`) and assembles its role with every pointer
resolved to what it is now. Here the owner lists, writes, saves and archives agents; asks a
model to write an agent's operating prompt from its form (the server runs that in the
background through the model the owner chose: `builder_prompt` and `read_builder`); and asks
an agent for something. That is a run like a skill run: the same queue, the same result tool,
the same review, its instructions opening with the agent's role, with the documents it points to
named and the recent meetings it reads pinned at the version they are now.
"""

from __future__ import annotations

import builtins
import datetime as dt
import json
import os
import re
from typing import Any

from workspace_core.clock import iso
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Task
from workspace_core.errors import NotFound, ValidationFailed

from .agent import _json_in
from .brain import Brain
from .notes import Note, Notes
from .runtime import Runtime
from .skills import Skills, makes_files

NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
LIST_FIELDS = (
    "responsibilities",
    "goals",
    "projects",
    "skills",
    "library",
    "context",
    "boundaries",
)
TEXT_LIMITS = {"role": 300, "output_shape": 500, "output": 20, "runner": 90, "scope": 120}
MAX_ITEMS = 20
MAX_ITEM = 300
MAX_PROMPT = 30_000
MAX_ASK = 4000
MAX_MEETINGS = 3
MEETINGS = ("recording", "transcript")
INSTRUCTIONS = """\
You are working as the agent {name} for {owner}. Its role, as {owner} wrote it, is below, with
what it points to as each is now. Follow it for the request at the end. The Relevant context
section holds what the Brain found for this request. Where the role says get_skill or
get_reference, use get_brain_skill and get_brain_reference. Use only what the Brain, the pinned
items and the request say: never invent facts, names, numbers or quotes, and where something is
missing, say so in the result.

Save the result once with save_skill_result, with this run's run_id: a short title, and the whole
result as Markdown (what was asked for, ready to use, without commentary around it). Then complete
the task. Never publish or send anything.

---

{role}
---"""
BUILDER = """\
You write an agent's operating prompt for {owner}. Follow the procedure below, then the role
they filled in.

## The procedure

{procedure}

## The role {owner} filled in

{form}
"""


def pinned_notes_line(notes: builtins.list[Note]) -> str:
    """The line that sends a run to the notes pinned for it (Workspace docs, say)."""
    if len(notes) == 1:
        note = notes[0]
        return (
            f"Work from the pinned note “{note.title}” ({note.id}): read it in full with "
            "get_context_item first."
        )
    listed = ", ".join(f"“{n.title}” ({n.id})" for n in notes)
    return f"Work from the pinned notes {listed}: read each in full with get_context_item first."


def _clean_list(value: Any, field: str) -> builtins.list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        value = [line for line in value.splitlines()]
    if not isinstance(value, list):
        raise ValidationFailed(f"{field} is a list.", field=field)
    items = [" ".join(str(v).split())[:MAX_ITEM] for v in value if str(v).strip()]
    if len(items) > MAX_ITEMS:
        raise ValidationFailed(f"At most {MAX_ITEMS} in {field}.", field=field)
    return list(dict.fromkeys(items))


def clean_form(form: dict[str, Any]) -> dict[str, Any]:
    """The role's fields as the Brain takes them; the Brain checks what they mean."""
    out: dict[str, Any] = {}
    for key, limit in TEXT_LIMITS.items():
        if key in form and form[key] is not None:
            out[key] = " ".join(str(form[key]).split())[:limit]
    for key in LIST_FIELDS:
        if key in form:
            out[key] = _clean_list(form[key], key)
    if form.get("meetings_days") not in (None, ""):
        try:
            out["meetings_days"] = int(form["meetings_days"])
        except (TypeError, ValueError) as exc:
            raise ValidationFailed(
                "meetings_days is a number of days.", field="meetings_days"
            ) from exc
    if "review" in form:
        out["review"] = bool(form["review"])
    return out


class Agents:
    def __init__(self, rt: Runtime, brain: Brain, skills: Skills, notes: Notes) -> None:
        self.rt = rt
        self.brain = brain
        self.skills = skills
        self.notes = notes

    # ---------------------------------------------------------------- reading

    def list(self, who: Principal, *, archived: bool = False) -> builtins.list[dict[str, Any]]:
        """Every agent the owner defined, with its last run."""
        who.require("brain.read")
        found = self.rt.brain.agents(archived=archived)
        last: dict[str, dict[str, Any]] = {}
        for run in self.skills.runs_where(who, lambda about: bool(about.get("agent")), limit=50):
            name = str(run.get("agent") or "")
            if name and name not in last:
                last[name] = {
                    "task_id": run["task_id"],
                    "status": run["status"],
                    "at": run["updated_at"],
                }
        return [dict(a, last_run=last.get(a["name"])) for a in found]

    def get(self, who: Principal, name: str) -> dict[str, Any]:
        """One agent: its role, each pointer as it is now, and the prompt a model gets for it."""
        who.require("brain.read")
        found = self.rt.brain.agent(str(name or "").strip().lower())
        if found is None:
            raise NotFound(f"No agent named {name}.", name=name)
        return found

    def versions(
        self, who: Principal, name: str, *, with_text: bool = False
    ) -> builtins.list[dict[str, Any]]:
        who.require("brain.read")
        rows = self.rt.brain.agent_versions(name, with_text=with_text)
        if rows is None:
            raise NotFound(f"No agent named {name}.", name=name)
        return rows

    def runs(self, who: Principal, name: str) -> builtins.list[dict[str, Any]]:
        """What the agent was asked and what it made, newest first."""
        return self.skills.runs_where(who, lambda about: about.get("agent") == name)

    # ---------------------------------------------------------------- changing

    def save(self, who: Principal, name: str, form: dict[str, Any], prompt: str) -> dict[str, Any]:
        """Create or change an agent: the owner's change to the Brain, one undo point."""
        who.require("brain.govern")
        wanted = str(name or "").strip().lower()
        if not NAME.match(wanted):
            raise ValidationFailed(
                "An agent's name is lowercase words joined by hyphens, such as content-strategist.",
                field="name",
            )
        text = str(prompt or "").strip()
        if len(text) > MAX_PROMPT:
            raise ValidationFailed(
                f"Keep the prompt under {MAX_PROMPT:,} characters.", field="prompt"
            )
        saved = self.rt.brain.save_agent(wanted, clean_form(form), text)
        with self.rt.write() as tx:
            tx.emit(
                "agent.saved",
                actor_id=who.actor_id,
                subject_type="agent",
                subject_id=wanted,
                data={"checkpoint": (saved.get("checkpoint") or {}).get("id")},
            )
        return dict(self.get(who, wanted), checkpoint=saved.get("checkpoint"))

    def archive(self, who: Principal, name: str) -> dict[str, Any]:
        who.require("brain.govern")
        done = self.rt.brain.archive_agent(name)
        with self.rt.write() as tx:
            tx.emit(
                "agent.archived",
                actor_id=who.actor_id,
                subject_type="agent",
                subject_id=name,
                data={},
            )
        return done

    # ---------------------------------------------------------------- a model writes its prompt

    def builder_prompt(self, who: Principal, name: str, form: dict[str, Any]) -> str:
        """What the model reads to write the agent's operating prompt: the procedure, then the
        role as filled in, each pointer with a line saying what it is."""
        who.require("brain.read")
        procedure = self.rt.brain.work_skill("agent-builder")
        if not procedure:
            raise NotFound("The procedure for writing an agent's prompt is missing from the Brain.")
        fields = clean_form(form)
        files = self.brain.files(who)
        skills = {s.name: s for s in files.skills}
        titles = {r.path: r.title for r in files.references}
        lines = [
            f"Name: {name or '(not named yet)'}",
            f"What it does: {fields.get('role') or '(not said)'}",
        ]
        for key, label in (
            ("responsibilities", "Responsible for"),
            ("goals", "Goals it serves"),
            ("boundaries", "Never does"),
        ):
            if fields.get(key):
                lines.append(f"{label}:\n" + "\n".join(f"- {v}" for v in fields[key]))
        if fields.get("skills"):
            lines.append(
                "Skills it points to:\n"
                + "\n".join(
                    f"- /{n}: {skills[n].description}"
                    if n in skills
                    else f"- /{n} (not written yet)"
                    for n in fields["skills"]
                )
            )
        if fields.get("library"):
            lines.append(
                "Documents it reads whole:\n"
                + "\n".join(f"- {titles.get(p, p)}" for p in fields["library"])
            )
        if fields.get("context"):
            lines.append("Brain areas and topics: " + ", ".join(fields["context"]))
        if fields.get("projects"):
            lines.append("Projects: " + ", ".join(fields["projects"]))
        if fields.get("output_shape"):
            lines.append(f"Its work's shape: {fields['output_shape']}")
        return BUILDER.format(owner=who.name, procedure=procedure.strip(), form="\n\n".join(lines))

    @staticmethod
    def read_builder(answer: str) -> dict[str, Any]:
        """The prompt the model wrote, and what it says would make it sharper."""
        found = _json_in(answer, last=True)
        if found is None or not str(found.get("prompt") or "").strip():
            raise ValidationFailed(
                "The model's answer had no prompt in it. Try again, or write it yourself."
            )
        questions = [
            " ".join(str(q).split())[:200] for q in found.get("questions") or [] if str(q).strip()
        ]
        return {"prompt": str(found["prompt"]).strip()[:MAX_PROMPT], "questions": questions[:8]}

    # ---------------------------------------------------------------- asking it for something

    def run(
        self,
        who: Principal,
        name: str,
        *,
        ask: str,
        project: str | None = None,
        capture_id: str | None = None,
    ) -> Task:
        """Ask the agent for something: a run like a skill run, opening with its role. With
        `capture_id`, a note it works from (a Workspace doc: "I outline, you write"), pinned at
        the version it is now."""
        who.require("tasks.write")
        doc = self.notes.get(who, capture_id) if capture_id else None
        plan = self.plan(who, name, ask=ask, project=project, docs=[doc] if doc else None)
        if doc is not None:
            plan["about"]["capture"] = {"id": doc.id, "title": doc.title, "revision": doc.revision}
        return self.skills.queue(who, **plan)

    def plan(
        self,
        who: Principal,
        name: str,
        *,
        ask: str,
        project: str | None = None,
        docs: builtins.list[Note] | None = None,
        skills: builtins.list[str] | None = None,
        library: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        """What asking the agent sends a model, without starting anything (Compose shows it
        first): the run's title and purpose, its instructions, the request the Brain briefs it
        on, its record, and what it pins. `docs` are notes it works from; `skills` and
        `library` add to what the agent points to."""
        found = self.get(who, name)
        agent, resolved = found["agent"], found["resolved"]
        if agent.get("status") == "archived":
            raise ValidationFailed(f"The agent {name} is archived; bring it back first.", name=name)
        ask = str(ask or "").strip()
        if not ask:
            raise ValidationFailed("Say what you need from it.", field="ask")
        if len(ask) > MAX_ASK:
            raise ValidationFailed(f"Keep the request under {MAX_ASK:,} characters.", field="ask")
        own = [s["name"] for s in resolved["skills"] if not s["missing"]]
        added = [n for n in skills or [] if n not in own]
        names = [*own, *added]
        paths = list(
            dict.fromkeys(
                [d["path"] for d in resolved["library"] if not d["missing"]] + list(library or [])
            )
        )
        held = {s.name: s for s in self.brain.files(who).skills}
        files_mode = any(makes_files(held.get(n)) for n in names)
        instructions = INSTRUCTIONS.format(
            name=agent["name"], owner=who.name, role=found["prompt"].strip()
        )
        extra = ""
        focus = None
        if project:
            focus = next((p for p in self.brain.projects(who) if p.id == project), None)
            if focus is None:
                raise NotFound(f"No project {project}.", project=project)
            extra += f"\n\nThis is for the project {focus.title} ({focus.id})."
        if added:
            extra += (
                "\n\nFollow these skills too, in this order, reading each in full with "
                "get_brain_skill first: " + ", ".join(f"/{n}" for n in added) + "."
            )
        if paths:
            extra += (
                "\n\nRead these documents whole with get_brain_reference: " + ", ".join(paths) + "."
            )
        notes = [d for d in docs or [] if d is not None]
        if notes:
            extra += "\n\n" + pinned_notes_line(notes)
        meetings = self._meetings(who, agent)
        if meetings:
            extra += (
                "\n\nRecent meetings, pinned: "
                + "; ".join(f"“{m.title}” ({m.created_at[:10]}, {m.id})" for m in meetings)
                + ". Read what you need with get_context_item."
            )
        instructions += f"\n\nThe request, from {who.name}:\n{ask}{extra}"
        request = f"{ask}\n\nAs the agent {agent['name']}: {agent['role']}"
        if agent["context"]:
            request += "\nContext: " + ", ".join(agent["context"])
        if focus is not None:
            request += f"\nProject: {focus.title}"
        about: dict[str, Any] = {
            "name": names[0] if names else "",
            "names": names,
            "ask": ask,
            "agent": agent["name"],
            "files": files_mode,
        }
        if focus is not None:
            about["project"] = {"id": focus.id, "title": focus.title}
        if paths:
            about["attached"] = paths
        pins = [("context_item", n.id, n.revision) for n in notes]
        pins += [("context_item", m.id, m.revision) for m in meetings]
        return {
            "title": f"Ask {agent['name']}",
            "purpose": f"The agent {agent['name']} works on what {who.name} asked.",
            "instructions": instructions,
            "request": request,
            "about": about,
            "pins": pins,
        }

    def _meetings(self, who: Principal, agent: dict[str, Any]) -> builtins.list[Any]:
        """The recordings and transcripts from the last days the agent reads, newest first:
        those linked to its projects when any are, else the latest."""
        days = int(agent.get("meetings_days") or 0)
        if days <= 0:
            return []
        cutoff = iso(self.rt.clock.now() - dt.timedelta(days=days))
        recent = [
            n
            for n in self.notes.list(who, limit=300)
            if n.capture in MEETINGS and n.created_at >= cutoff and n.body.strip()
        ]
        projects = set(agent.get("projects") or [])
        linked = [n for n in recent if projects & set(getattr(n, "projects", []) or [])]
        return (linked or recent)[:MAX_MEETINGS]

    # ---------------------------------------------------------------- other AIs

    @staticmethod
    def claude_code_file(name: str, role: str) -> tuple[str, str]:
        """Where Claude Code finds a subagent, and what it says: only to fetch the agent from
        the Brain and follow it, so Claude Code always works from the current version."""
        path = os.path.join(os.path.expanduser("~"), ".claude", "agents", f"{name}.md")
        description = (role or f"The agent {name} from the Brain.").replace("\n", " ")
        text = (
            "---\n"
            f"name: {name}\n"
            f"description: {json.dumps(description)[1:-1]} Use when asked to work as {name}.\n"
            "---\n"
            f"You are the agent {name}, kept in the owner's Brain. Before anything else, call the "
            f'Brain\'s get_agent tool with name "{name}" and follow what it returns: your current '
            "role, what you point to and what you never do. Then call get_task_context with the "
            "task in front of you. If the Brain is not connected, say so and stop.\n"
        )
        return path, text
