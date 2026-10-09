"""Compose: one place to ask, built so the owner sees and reuses what goes to the model.

The owner writes a request and picks what goes with it: skills in order (or none, and the Brain
picks), one agent, Workspace docs and other notes, documents to read whole, a project. Compose
plans the run exactly as it would start it (an agent's run when an agent is picked, else a run
like the Skills page's), so the prompt on screen is the prompt the model gets: the instructions,
the pinned notes, and the Brain's brief for the request. From there the owner improves the request
(the chosen model rewrites it, saying what changed and what it leaned on), runs it here, copies it
for any AI (whole, or short: a request that tells a connected AI to fetch its brief), or saves it
(services/prompts.py).
"""

from __future__ import annotations

import builtins
from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Task
from workspace_core.errors import NotFound, ValidationFailed

from .agent import _json_in
from .agents import Agents, pinned_notes_line
from .brain import Brain
from .notes import Note, Notes, cut
from .prompts import MAX_BODY, MAX_DOCS, MAX_LIBRARY, MAX_SKILLS, Prompts
from .runtime import Runtime
from .skills import (
    FILES_PART_MANY,
    PICK_INSTRUCTIONS,
    RUN_CONTRACT,
    RUN_MANY_INSTRUCTIONS,
    Skills,
    makes_files,
    use_of,
)

MAX_BRIEF = 4000  # characters of the Brain's brief the improver reads
IMPROVER = """\
You improve a request {owner} wrote in Compose. Follow the procedure below, then the request
and what {owner} picked to go with it.

## The procedure

{procedure}

## The request, as {owner} wrote it

{request}

## What {owner} picked

{picks}
"""


class Compose:
    def __init__(
        self,
        rt: Runtime,
        brain: Brain,
        skills: Skills,
        agents: Agents,
        notes: Notes,
        prompts: Prompts,
    ) -> None:
        self.rt = rt
        self.brain = brain
        self.skills = skills
        self.agents = agents
        self.notes = notes
        self.prompts = prompts

    # ---------------------------------------------------------------- what the owner picked

    def _picked(
        self,
        who: Principal,
        *,
        request: str,
        skills: builtins.list[str] | None = None,
        agent: str | None = None,
        docs: builtins.list[str] | None = None,
        library: builtins.list[str] | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """The picks, each checked against the Brain and the owner's notes."""
        ask = str(request or "").strip()
        if not ask:
            raise ValidationFailed("Write what you want first.", field="request")
        if len(ask) > MAX_BODY:
            raise ValidationFailed(
                f"Keep the request under {MAX_BODY:,} characters.", field="request"
            )
        names = list(
            dict.fromkeys(str(n).strip().lstrip("/") for n in skills or [] if str(n).strip())
        )
        if len(names) > MAX_SKILLS:
            raise ValidationFailed(f"Pick at most {MAX_SKILLS} skills.", field="skills")
        files = self.brain.files(who)
        held = {s.name: s for s in files.skills}
        for name in names:
            skill = held.get(name)
            if skill is None:
                raise NotFound(f"No skill {name}.", name=name)
            users = [s.name for s in files.skills if name in s.depends_on]
            if use_of(skill, users) != "run":
                raise ValidationFailed(
                    f"/{name} is not run on its own: pick the skills you run.", name=name
                )
        ids = list(dict.fromkeys(str(d).strip() for d in docs or [] if str(d).strip()))
        if len(ids) > MAX_DOCS:
            raise ValidationFailed(f"Pick at most {MAX_DOCS} notes.", field="docs")
        notes = [self.notes.get(who, i) for i in ids]
        paths = list(dict.fromkeys(str(p).strip() for p in library or [] if str(p).strip()))
        if len(paths) > MAX_LIBRARY:
            raise ValidationFailed(f"Pick at most {MAX_LIBRARY} documents.", field="library")
        known = {r.path: r for r in files.references}
        for path in paths:
            if path not in known:
                raise NotFound(f"The Brain holds no document at {path}.", path=path)
        focus = None
        if project:
            focus = next((p for p in self.brain.projects(who) if p.id == project), None)
            if focus is None:
                raise NotFound(f"No project {project}.", project=project)
        return {
            "ask": ask,
            "skills": [held[n] for n in names],
            "agent": str(agent or "").strip() or None,
            "notes": notes,
            "library": [known[p] for p in paths],
            "project": focus,
        }

    # ---------------------------------------------------------------- the run, before it runs

    def plan(
        self,
        who: Principal,
        *,
        request: str,
        skills: builtins.list[str] | None = None,
        agent: str | None = None,
        docs: builtins.list[str] | None = None,
        library: builtins.list[str] | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """The run as Compose would start it, without starting it: its title and purpose, its
        instructions, the request the Brain briefs it on, its record and what it pins."""
        p = self._picked(
            who,
            request=request,
            skills=skills,
            agent=agent,
            docs=docs,
            library=library,
            project=project,
        )
        ask, notes = p["ask"], p["notes"]
        names = [s.name for s in p["skills"]]
        paths = [r.path for r in p["library"]]
        if p["agent"]:
            plan = self.agents.plan(
                who, p["agent"], ask=ask, project=project, docs=notes, skills=names, library=paths
            )
        else:
            plan = self._skills_plan(who, ask, p["skills"], notes, paths, p["project"])
        about = plan["about"]
        about["compose"] = True
        if notes:
            about["docs"] = [{"id": n.id, "title": n.title, "revision": n.revision} for n in notes]
        return plan

    def _skills_plan(
        self,
        who: Principal,
        ask: str,
        skills: builtins.list[Any],
        notes: builtins.list[Note],
        paths: builtins.list[str],
        focus: Any,
    ) -> dict[str, Any]:
        """A run like the Skills page's: the skills in order, or none and the Brain picks."""
        files_mode = any(makes_files(s) for s in skills)
        if skills:
            listed = ", ".join(f"/{s.name}" for s in skills)
            instructions = RUN_MANY_INSTRUCTIONS.format(
                names=listed, files=FILES_PART_MANY if files_mode else ""
            )
            request = f"{ask}\n\nUsing the skills " + "; ".join(
                f"{s.name}: {s.description}" for s in skills
            )
            title, purpose = f"Run {listed}", f"Run the skills {listed} for {who.name}."
        else:
            instructions, request = PICK_INSTRUCTIONS, ask
            title = "Compose: " + cut(ask, 60)
            purpose = f"Do what {who.name} asked, with the skill that fits."
        extra = ""
        if focus is not None:
            extra += f"\n\nThis is for the project {focus.title} ({focus.id})."
            request += f"\nProject: {focus.title}"
        if paths:
            extra += (
                "\n\nRead these documents whole with get_brain_reference: " + ", ".join(paths) + "."
            )
        if notes:
            extra += "\n\n" + pinned_notes_line(notes)
        about: dict[str, Any] = {
            "name": skills[0].name if skills else "",
            "names": [s.name for s in skills],
            "ask": ask,
            "files": files_mode,
        }
        if focus is not None:
            about["project"] = {"id": focus.id, "title": focus.title}
        if paths:
            about["attached"] = paths
        return {
            "title": title,
            "purpose": purpose,
            "instructions": f"{instructions}\n\nThe request, from {who.name}:\n{ask}{extra}",
            "request": request,
            "about": about,
            "pins": [("context_item", n.id, n.revision) for n in notes],
        }

    def packet(self, who: Principal, **spec: Any) -> dict[str, Any]:
        """The run's packet as a model would get it when it claims the run, minus the ids it
        gets then: the instructions, each pinned note as it is now, and the Brain's brief."""
        who.require("brain.read")
        plan = self.plan(who, **spec)
        inputs = []
        for _, note_id, revision in plan["pins"]:
            note = self.notes.get(who, note_id)
            text = note.body or ""
            limit = self.rt.max_input_chars
            inputs.append(
                {
                    "ref": f"context_item:{note.id}",
                    "title": note.title,
                    "version": revision,
                    "text": text[:limit],
                    "truncated": len(text) > limit,
                }
            )
        brain = self.rt.brain.context(plan["request"][:2000])
        return {
            "task": {"id": "(given when it runs)", "title": plan["title"], "revision": 1},
            "purpose": {"text": plan["purpose"], "project": None},
            "instructions": {"text": plan["instructions"], "prompt_version": 1},
            "inputs": inputs,
            "brain": {
                "available": brain.available,
                "text": brain.text,
                "entry_ids": list(brain.entry_ids),
                "note": brain.reason,
            },
            "output_contract": RUN_CONTRACT,
            "review_policy": "auto",
            "review_notes": [],
            "about": plan["about"],
        }

    def short(self, who: Principal, **spec: Any) -> str:
        """The request for any AI connected to the Brain: what was asked, then the calls that
        fetch its brief, the agent, the skills and the documents. Notes are private to the app,
        so their text comes along."""
        p = self._picked(who, **spec)
        focus = p["project"]
        lines = [p["ask"], ""]
        lines.append(
            "Before you start, call get_task_context with this request"
            + (f" (it is for the project {focus.title})" if focus is not None else "")
            + "."
        )
        if p["agent"]:
            name = p["agent"]
            lines.append(
                f'Work as the agent {name}: call get_agent with name "{name}" first, and follow it.'
            )
        if p["skills"]:
            lines.append(
                "Follow these skills in this order, opening each with get_skill: "
                + ", ".join(f"/{s.name}" for s in p["skills"])
                + "."
            )
        if p["library"]:
            lines.append(
                "Read these documents whole with get_reference: "
                + ", ".join(r.path for r in p["library"])
                + "."
            )
        lines.append(
            "Use only what the Brain, my notes and this request say; where something is missing, "
            "say so instead of guessing."
        )
        for note in p["notes"]:
            lines += ["", f"## My note: {note.title}", "", (note.body or "").strip()]
        return "\n".join(lines).strip() + "\n"

    def run(self, who: Principal, *, prompt_id: str | None = None, **spec: Any) -> Task:
        """Run it here: a task on the same queue as every skill and agent run."""
        who.require("tasks.write")
        plan = self.plan(who, **spec)
        if prompt_id:
            saved = self.prompts.get(who, prompt_id)
            plan["about"]["prompt"] = {"id": saved.id, "title": saved.title}
            plan["title"] = cut(saved.title, 120)
        return self.skills.queue(who, **plan)

    # ---------------------------------------------------------------- improving the request

    def improver_prompt(self, who: Principal, **spec: Any) -> str:
        """What the model reads to improve the request: the procedure, the request, each pick
        with a line saying what it is, and the Brain's brief, cut short."""
        who.require("brain.read")
        procedure = self.rt.brain.work_skill("prompt-improver")
        if not procedure:
            raise NotFound("The procedure for improving a prompt is missing from the Brain.")
        p = self._picked(who, **spec)
        lines: builtins.list[str] = []
        if p["skills"]:
            lines.append(
                "Skills, in this order:\n"
                + "\n".join(f"- /{s.name}: {s.description}" for s in p["skills"])
            )
        if p["agent"]:
            found = self.agents.get(who, p["agent"])
            lines.append(f"Agent: {found['agent']['name']}, {found['agent']['role']}")
        if p["notes"]:
            lines.append(
                "Workspace docs and notes:\n"
                + "\n".join(f"- {n.title}: {cut(n.body or '', 300)}" for n in p["notes"])
            )
        if p["library"]:
            lines.append(
                "Documents to read whole:\n"
                + "\n".join(
                    f"- {r.path} ({r.title})" + (f": {r.description}" if r.description else "")
                    for r in p["library"]
                )
            )
        if p["project"] is not None:
            focus = p["project"]
            lines.append(
                f"Project: {focus.title}" + (f", {focus.summary}" if focus.summary else "")
            )
        brief = self.rt.brain.context(self.plan(who, **spec)["request"][:2000])
        if brief.text:
            lines.append(
                "What the Brain would hand an AI for this request (cut short):\n"
                + brief.text.strip()[:MAX_BRIEF]
            )
        return IMPROVER.format(
            owner=who.name,
            procedure=procedure.strip(),
            request=p["ask"],
            picks="\n\n".join(lines) or "Nothing: the Brain picks what fits.",
        )

    @staticmethod
    def read_improved(answer: str) -> dict[str, Any]:
        """The improved request, each change in a line, the picks it leaned on, and what is
        still unclear."""
        found = _json_in(answer, last=True)
        if found is None or not str(found.get("prompt") or "").strip():
            raise ValidationFailed("The model's answer had no request in it. Try again.")

        def lines(key: str, limit: int) -> builtins.list[str]:
            value = found.get(key) or []
            if not isinstance(value, list):
                return []
            return [" ".join(str(v).split())[:300] for v in value if str(v).strip()][:limit]

        return {
            "prompt": str(found["prompt"]).strip()[:MAX_BODY],
            "changes": lines("changes", 10),
            "used": lines("used", 12),
            "questions": lines("questions", 8),
        }
