"""The Workspace: where the owner thinks first, before working with AI.

What it holds is notes underneath (services/notes.py): docs the owner writes (from a template or
blank), links (a calendar, a sheet, a folder), and anything else linked to a project, such as a
recording brought in through Capture. Each can be linked to several projects at once and stays
one item: the link is a label, so nothing is copied and nothing becomes readable by an AI.

AI acts on a doc only when asked, and only through runs like a skill run, with the doc pinned at
the version it is then: Draft from it (follow a skill, or ask an agent: "I outline, you write"),
Push back (a critic that asks the hard questions and writes nothing for the owner), or Continue
(finish where it stops). What a run makes comes back beside the doc; the owner takes it as the
doc's next version, as a new doc, or leaves it.
"""

from __future__ import annotations

import builtins
import os
import re
from typing import Any
from urllib.parse import urlparse

from workspace_core.docx import markdown_to_docx
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Task
from workspace_core.errors import NotFound, ValidationFailed

from .agents import Agents
from .brain import Brain
from .notes import MARKUP, Note, Notes, cut
from .runtime import Runtime
from .skills import Skills

# A new doc's start: (title, Markdown). Blank is just a page.
TEMPLATES: dict[str, tuple[str, str]] = {
    "blank": ("", ""),
    "outline": (
        "Outline",
        "## What it is for\n\n## Who it is for\n\n## The points, in order\n\n1. \n2. \n3. \n\n"
        "## What it should not say\n",
    ),
    "plan": (
        "Plan",
        "## The goal\n\n## Where it stands\n\n## The steps\n\n- [ ] \n- [ ] \n\n"
        "## Risks and open questions\n",
    ),
    "decision": (
        "Decision",
        "## The decision\n\n## Why\n\n## What else we considered\n\n## Who decided, and when\n",
    ),
    "progress": (
        "Progress update",
        "## What moved\n\n## What is stuck\n\n## What comes next\n",
    ),
}
ACTIONS = ("draft", "push-back", "continue")
IMPORTS = (".md", ".txt", ".html", ".htm", ".docx", ".pptx", ".pdf")
MAX_IMPORT = 25 * 1024 * 1024
MAX_ASK = 2000
PUSH_BACK = """\
You are {owner}'s critical-thinking partner. Read the pinned note “{title}” ({note}) in full with
get_context_item. Do not rewrite it and do not write any of it for {owner}. Push back on it the
way a sharp, kind colleague would before it goes further: the claims that need evidence, the
gaps in the reasoning, the questions its readers will ask, the assumptions to check, and what is
missing. Use the Brain's context (search_context) to say where something the note says clashes
with what the Brain holds.

Save the result once with save_skill_result, with this run's run_id: a short title, and the
questions and challenges as Markdown, most important first, each with one line on why it
matters. Then complete the task. Never publish or send anything."""
CONTINUE = """\
Read the pinned note “{title}” ({note}) in full with get_context_item. Continue it from where it
stops{where}, in its own voice and shape, using only what the note, the Brain's context
(search_context) and the request say; mark anything missing as [to check] instead of inventing it.

Save the result once with save_skill_result, with this run's run_id: a short title, and only the
new part as Markdown (it goes after what is there). Then complete the task. Never publish or send
anything."""


def excerpt(body: str, limit: int = 160) -> str:
    """A doc's opening in words: its lines without Markdown, headings and empty checkboxes left
    out, so a template not filled in yet says nothing."""
    words = []
    for line in str(body or "").splitlines():
        if line.lstrip().startswith("#"):
            continue
        text = MARKUP.sub("", line.strip() + " ")  # the space lets a bare "- [ ]" match
        text = re.sub(r"\*\*|__|`", "", text).strip()
        if text:
            words.append(text)
    return cut(" ".join(words), limit)


def _kind(note: Note) -> str:
    if note.capture == "link":
        return "link"
    return "doc" if note.capture == "note" else note.capture


class Docs:
    def __init__(
        self, rt: Runtime, notes: Notes, brain: Brain, skills: Skills, agents: Agents
    ) -> None:
        self.rt = rt
        self.notes = notes
        self.brain = brain
        self.skills = skills
        self.agents = agents

    # ---------------------------------------------------------------- reading

    def items(
        self, who: Principal, *, project: str | None = None, archived: bool = False
    ) -> dict[str, Any]:
        """The Workspace by project: docs and links the owner made, and anything linked to a
        project (or what was set aside, with `archived`). For one project, also the agents that
        work on it."""
        projects = {p.id: p for p in self.brain.projects(who)}
        mine = [
            n
            for n in self.notes.list(who, archived=archived, limit=1000)
            if n.capture in ("note", "link") or n.projects
        ]
        if project:
            mine = [n for n in mine if project in n.projects]
        out: dict[str, Any] = {
            "items": [self._item(n, projects) for n in mine],
            "projects": [
                {"id": p.id, "title": p.title, "active": p.active} for p in projects.values()
            ],
        }
        if project:
            out["agents"] = [
                {"name": a["name"], "role": a["role"], "last_run": a.get("last_run")}
                for a in self.agents.list(who)
                if project in a["projects"]
            ]
        return out

    @staticmethod
    def _item(note: Note, projects: dict[str, Any]) -> dict[str, Any]:
        kind = _kind(note)
        return {
            "id": note.id,
            "title": note.title,
            "kind": kind,
            "url": note.url,
            "excerpt": "" if kind == "link" else excerpt(note.body),
            "projects": [
                {
                    "id": p,
                    "title": projects[p].title if p in projects else p,
                    "missing": p not in projects,
                }
                for p in note.projects
            ],
            "updated_at": note.updated_at,
            "original": note.original,
        }

    def _projects(self, who: Principal, projects: builtins.list[str] | None) -> builtins.list[str]:
        wanted = list(dict.fromkeys(str(p).strip() for p in projects or [] if str(p).strip()))
        if not wanted:
            return []
        known = {p.id for p in self.brain.projects(who)}
        missing = [p for p in wanted if p not in known]
        if missing:
            raise NotFound(f"No project {missing[0]}.", project=missing[0])
        return wanted

    # ---------------------------------------------------------------- making and linking

    def create(
        self,
        who: Principal,
        *,
        template: str = "blank",
        title: str = "",
        projects: builtins.list[str] | None = None,
    ) -> Note:
        """A new doc, blank or from a template, linked to the projects given."""
        if template not in TEMPLATES:
            raise ValidationFailed(
                f"A template is one of {', '.join(TEMPLATES)}.", field="template"
            )
        heading, body = TEMPLATES[template]
        return self.notes.create(
            who, title=title.strip() or heading, body=body, projects=self._projects(who, projects)
        )

    def link(
        self,
        who: Principal,
        *,
        url: str,
        title: str = "",
        projects: builtins.list[str] | None = None,
    ) -> Note:
        """A link kept in the Workspace: a calendar, a sheet, a folder, a page."""
        host = urlparse(str(url or "").strip()).netloc
        return self.notes.create(
            who,
            title=title.strip() or host or "Link",
            url=url,
            projects=self._projects(who, projects),
        )

    def set_projects(self, who: Principal, note_id: str, projects: builtins.list[str]) -> Note:
        return self.notes.set_projects(who, note_id, self._projects(who, projects))

    def import_file(
        self,
        who: Principal,
        *,
        filename: str,
        data: bytes,
        projects: builtins.list[str] | None = None,
    ) -> Note:
        """A document brought in as a new doc to work in: its text, with its shape kept."""
        name = os.path.basename(str(filename or "").replace("\\", "/")).strip()
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMPORTS:
            raise ValidationFailed(f"Bring in {', '.join(IMPORTS)} files as a doc.", field="file")
        if not data or len(data) > MAX_IMPORT:
            raise ValidationFailed("A file to bring in as a doc is at most 25 MB.", field="file")
        extractor = self.rt.extractor
        text = extractor.markdown(data, name) if extractor is not None else None
        if not text or not text.strip():
            raise ValidationFailed(f"{name} has no text to work in.", field="file")
        title = re.sub(r"[_-]+", " ", os.path.splitext(name)[0]).strip() or name
        return self.notes.create(
            who, title=title, body=text, projects=self._projects(who, projects)
        )

    # ---------------------------------------------------------------- with AI, when asked

    def draft(
        self,
        who: Principal,
        note_id: str,
        *,
        skill: str | None = None,
        agent: str | None = None,
        ask: str = "",
    ) -> Task:
        """Draft from the doc: follow a skill, or ask an agent, with the doc pinned."""
        note = self.notes.get(who, note_id)
        if not note.body.strip():
            raise ValidationFailed("Write something first: an outline is enough.", field="note")
        wanted = (
            " ".join(str(ask or "").split())[:MAX_ASK] or f"Draft it from my note “{note.title}”."
        )
        project = note.projects[0] if note.projects else None
        if agent:
            return self.agents.run(who, agent, ask=wanted, project=project, capture_id=note.id)
        if skill:
            return self.skills.run(who, skill, ask=wanted, capture_id=note.id, project=project)
        raise ValidationFailed("Pick a skill or an agent to draft with.", field="skill")

    def push_back(self, who: Principal, note_id: str) -> Task:
        """A critic that asks the hard questions and writes nothing for the owner."""
        note = self._readable(who, note_id)
        return self._prompt_run(
            who,
            note,
            action="push-back",
            title=f"Push back on {note.title}",
            instructions=PUSH_BACK.format(owner=who.name, title=note.title, note=note.id),
            request=f"Questions and challenges for: {note.title}",
        )

    def continue_(self, who: Principal, note_id: str, *, where: str = "") -> Task:
        """Finish the doc where it stops (or from the part named)."""
        note = self._readable(who, note_id)
        place = " ".join(str(where or "").split())[:300]
        return self._prompt_run(
            who,
            note,
            action="continue",
            title=f"Continue {note.title}",
            instructions=CONTINUE.format(
                title=note.title, note=note.id, where=f" (from: {place})" if place else ""
            ),
            request=f"Continue: {note.title}\n\n{cut(note.body, 600)}",
        )

    def _readable(self, who: Principal, note_id: str) -> Note:
        note = self.notes.get(who, note_id)
        if not note.body.strip():
            raise ValidationFailed("Write something first.", field="note")
        return note

    def _prompt_run(
        self,
        who: Principal,
        note: Note,
        *,
        action: str,
        title: str,
        instructions: str,
        request: str,
    ) -> Task:
        about: dict[str, Any] = {
            "name": "",
            "names": [],
            "ask": title,
            "doc_action": action,
            "capture": {"id": note.id, "title": note.title, "revision": note.revision},
        }
        return self.skills.queue(
            who,
            title=title,
            purpose=f"{title}, for {who.name}.",
            instructions=instructions,
            request=request,
            about=about,
            pins=[("context_item", note.id, note.revision)],
        )

    def runs(self, who: Principal, note_id: str) -> builtins.list[dict[str, Any]]:
        """What AI made from this doc, newest first."""
        return self.skills.runs_where(
            who, lambda about: (about.get("capture") or {}).get("id") == note_id
        )

    def use(self, who: Principal, note_id: str, *, task_id: str, how: str) -> Note:
        """Take what a run made: as the doc's next version, added at its end, or as a new doc
        linked to the same projects. The version says where it came from."""
        if how not in ("version", "append", "new"):
            raise ValidationFailed(
                "Take it as the next version, add it at the end, or make a new doc.", field="how"
            )
        note = self.notes.get(who, note_id)
        run = next((r for r in self.runs(who, note_id) if r["task_id"] == task_id), None)
        if run is None or not run.get("result"):
            raise NotFound("That run made nothing to take.", task_id=task_id)
        text = str(run["result"]["text"] or "").strip()
        source = (
            f"From {run['agent']}"
            if run.get("agent")
            else (f"From /{run['skill']}" if run.get("skill") else "From your AI")
        )
        if how == "new":
            return self.notes.create(
                who,
                title=str(run["result"]["title"] or f"{note.title}, drafted"),
                body=text,
                projects=note.projects,
            )
        body = text if how == "version" else f"{note.body.rstrip()}\n\n{text}\n"
        return self.notes.add_version(who, note_id, body=body, label=source)

    # ---------------------------------------------------------------- leaving the app

    def export(self, who: Principal, note_id: str, *, fmt: str = "md") -> tuple[str, str, bytes]:
        """The doc as Markdown or Word: (file name, media type, bytes)."""
        note = self.notes.get(who, note_id)
        stem = re.sub(r"[^A-Za-z0-9 ._-]+", "", note.title).strip() or "doc"
        if fmt == "docx":
            return (
                f"{stem}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                markdown_to_docx(note.title, note.body),
            )
        if fmt != "md":
            raise ValidationFailed("Export as md or docx.", field="format")
        text = f"# {note.title}\n\n{note.body.strip()}\n"
        return f"{stem}.md", "text/markdown; charset=utf-8", text.encode("utf-8")
