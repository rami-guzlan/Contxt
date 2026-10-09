"""Skills from the app: run one, improve one, write a new one.

A skill is one of the Brain's procedures: its SKILL.md and the files beside it. Running one is
AI work like any other: the person says what they need, a model follows the skill with the
Brain's context and saves what it made with `save_skill_result`, shown on the skill's page. A
skill that makes files (a PDF, a deck) runs in a folder of its own with file and Python tools;
the runner sets the folder up and records what the run left there (`record_files`).

Improving a skill, or writing a new one, is a task too: the model proposes the text with
`propose_brain_skill`, and it waits in Review like every change to the Brain. A person's own
edit applies at once, as an undo point.
"""

from __future__ import annotations

import builtins
import os
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Task
from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.ports import BrainProposal, BrainSkill

from .artifacts import Artifacts
from .brain import Brain, proposer
from .context import open_to
from .distill import Distillation
from .runtime import Runtime
from .tasks import Tasks

RUN = "skill"  # the template of a skill run
DRAFT = "skill-draft"  # the template of improving a skill, or writing a new one
# What a skill makes (its `artifacts`) that is a file made on this computer: such a skill runs
# in a folder of its own, with file and Python tools.
FILE_KINDS = frozenset(
    (
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "image",
        "png",
        "jpg",
        "jpeg",
        "svg",
        "gif",
        "html",
        "csv",
        "zip",
        "video",
        "mp4",
    )
)
# What a skill that only supplies others holds (fonts and logos, say): not something to run.
RESOURCES = frozenset(
    (
        "fonts",
        "font",
        "logos",
        "logo",
        "assets",
        "asset",
        "icons",
        "templates",
        "template",
        "styles",
        "colors",
        "palette",
        "visuals",
    )
)
MAX_ASK = 4000  # characters in what a person asks of a skill
MAX_BODY = 60000  # characters in a skill's procedure
MAX_RESULT = 400000  # characters in a run's result
MAX_ATTACHED = 5  # Brain files one run may be pointed to
MAX_EDITS = 30  # passages one improvement may change
MAX_SKILLS = 6  # skills one run from the Skills page may follow
RECENT = 500  # tasks read to find a skill's runs
RUN_CONTRACT = {
    "artifacts": [],
    "notes": "Save what you made once with save_skill_result (this run's run_id), then "
    "complete the task. Nothing is published or sent.",
    "tool": "save_skill_result",
}
DRAFT_CONTRACT = {
    "artifacts": [],
    "notes": "Propose the skill once with propose_brain_skill (this run's run_id), then "
    "complete the task. It waits in Review for the person.",
    "tool": "propose_brain_skill",
}
RUN_INSTRUCTIONS = """\
Run the skill {name} for the request below. First read it in full with get_brain_skill (name \
"{name}") and follow it step by step. The Relevant context section holds what the Brain found \
for this request; open what the skill loads with get_brain_entry, get_brain_reference or \
search_context. Use only what the Brain, the pinned items and the request say: never invent \
facts, names, numbers or quotes, and where something is missing, say so in the result.

Where the skill asks questions before it starts, answer them from the request and the \
context; where they cannot be answered, choose a sensible default and say which in the result.
{files}
Save the result once with save_skill_result, with this run's run_id: a short title, and the \
whole result as Markdown (the post, the outline, the email: what the person asked for, ready \
to use, without commentary around it). Then complete the task. Never publish or send \
anything."""
FILES_PART = """
This run makes files, in a folder of its own on this computer (your working directory). The \
skill's own files are in ./skill (its scripts in ./skill/scripts, its assets in ./skill/assets) \
and the skills it depends on in folders named after them (for example ./shared-assets). Read \
and write files there, and run Python with `python` (for example `python skill/scripts/x.py`). \
Save what you make in the working directory itself, not inside ./skill: where the skill says \
/mnt/user-data/outputs or present_files, write to the working directory instead. Only what \
you leave there is kept; the copies of the skills are removed when the run ends. Check each \
file you made opens (read it back, or render a page), and in the result list each file with \
what it is.
"""
RUN_MANY_INSTRUCTIONS = """\
Run these skills for the request below, in this order: {names}. First read each in full with \
get_brain_skill and follow them step by step, the result of one feeding the next where that \
fits (research, then the draft, then its formatting). The Relevant context section holds what \
the Brain found for this request; open what the skills load with get_brain_entry, \
get_brain_reference or search_context. Use only what the Brain, the pinned items and the \
request say: never invent facts, names, numbers or quotes, and where something is missing, \
say so in the result.

Where a skill asks questions before it starts, answer them from the request and the context; \
where they cannot be answered, choose a sensible default and say which in the result.
{files}
Save the result once with save_skill_result, with this run's run_id: a short title, and the \
whole result as Markdown (what the person asked for, ready to use, without commentary around \
it). Then complete the task. Never publish or send anything."""
PICK_INSTRUCTIONS = """\
The request below names no skill. The Relevant context section holds what the Brain found \
for it, including the skills that fit (under Procedure or Skills): read the best fit in full \
with get_brain_skill and follow it step by step. When none fits, do the work directly from \
the Brain's context. Use only what the Brain, the pinned items and the request say: never \
invent facts, names, numbers or quotes, and where something is missing, say so in the result. \
If the skill that fits makes files (a PDF, a deck), say so and suggest running it from its page, \
where it can make them.

Save the result once with save_skill_result, with this run's run_id: a short title, and the \
whole result as Markdown, ending with one line naming the skill you followed (or "No skill \
fitted"). Then complete the task. Never publish or send anything."""
FILES_PART_MANY = """
This run makes files, in a folder of its own on this computer (your working directory). Each \
skill's own files are in a folder named after it (./name, its scripts in ./name/scripts, its \
assets in ./name/assets), as are the skills they depend on. Read and write files there, and \
run Python with `python`. Save what you make in the working directory itself, not inside the \
skills' folders: where a skill says /mnt/user-data/outputs or present_files, write to the \
working directory instead. Only what you leave there is kept; the copies of the skills are \
removed when the run ends. Check each file you made opens, and in the result list each file \
with what it is.
"""
IMPROVE_INSTRUCTIONS = """\
Improve the skill {name} as the person asks below. First read it in full with get_brain_skill \
(name "{name}"). Change only what the request asks for, plus anything the change makes wrong \
elsewhere in the skill; keep everything else word for word, including headings and the steps \
the request does not touch. Use only what the request and the Brain say.

Propose the new version once with propose_brain_skill, with this run's run_id and target \
"{name}". Send the change as edits: each a passage quoted exactly from the skill's procedure \
(find: long enough to occur once) and the text that replaces it (replace). To add a step, quote \
the line it follows and replace it with that line plus the new one. The app applies the edits \
to the skill as it is now, so everything you do not quote stays word for word. Send the whole \
procedure as body instead only when most of it changes. Give a description, when_to_use or \
triggers only when the request changes what the skill is for, and in reason one or two plain \
sentences on what changed and why. Then complete the task. It waits in Review for the person; \
nothing changes until they approve it."""
NEW_INSTRUCTIONS = """\
Write a new skill from the person's description below{source}. A skill is a procedure an AI \
follows to make something (a post, an email, a proposal, a deck): what it needs first and what \
to ask when that is missing, numbered steps, the shape of the result, and the checks before \
handing it over. Search the Brain (search_context) for the rules, voice and facts it should \
follow, and read a similar skill (get_brain_skill) for the shape. Use only what the \
description and the Brain say.

Propose it once with propose_brain_skill, with this run's run_id: a short name (lowercase \
words joined by hyphens), a category{categories}, a description saying what it makes and when \
to use it, when_to_use, three to five triggers (short phrases a person would say to ask for \
it), artifacts (what it makes: post, email, pdf, docx, pptx), loads (the Brain topics and \
references/ documents it should read), and the body: Markdown starting with "# /<name>". Then \
complete the task. It waits in Review for the person."""


def makes_files(skill: BrainSkill | None) -> bool:
    """Whether a skill makes files on this computer (a PDF, a deck), not only text."""
    return bool(skill) and any(
        str(kind).strip().lower() in FILE_KINDS for kind in (skill.artifacts if skill else [])
    )


def use_of(skill: BrainSkill, used_by: builtins.list[str]) -> str:
    """How a person uses a skill from the app: `run` it here; `support`, the files other
    skills build on (fonts, logos), kept rather than run; or `chat`, a procedure called by
    name that makes nothing (the Brain's own housekeeping, like closing a session), run in a
    conversation with the AI where it has the tools it needs."""
    kinds = {str(kind).strip().lower() for kind in skill.artifacts if str(kind).strip()}
    if used_by and kinds and kinds <= RESOURCES:
        return "support"
    if not kinds and skill.invocation == "explicit":
        return "chat"
    return "run"


def apply_edits(body: str, edits: builtins.list[dict[str, Any]], *, shown: str = "") -> str:
    """The procedure with each quoted passage replaced, in order. A passage must occur exactly
    once, so an edit can never land somewhere it was not meant for. `shown` is the skill as an
    AI reads it (a header above the procedure), so a quote from the header is named as such."""
    if len(edits) > MAX_EDITS:
        raise ValidationFailed(f"Send at most {MAX_EDITS} edits at a time.", field="edits")
    for number, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            raise ValidationFailed(f"Edit {number} is {{find, replace}}.", field="edits")
        find, replace = str(edit.get("find") or ""), str(edit.get("replace") or "")
        if not find.strip():
            raise ValidationFailed(f"Edit {number} quotes nothing to find.", field="edits")
        found = body.count(find)
        if not found and find.strip() in shown:
            raise ValidationFailed(
                f"Edit {number}: that passage is in the header shown above the procedure (its "
                "name, Loads, Folder and the like), which an edit cannot change. Quote the "
                "procedure itself, the text below the Folder line.",
                field="edits",
                find=find[:200],
            )
        if found != 1:
            raise ValidationFailed(
                f"Edit {number}: the passage to find occurs {found} times in the skill"
                + (": quote it exactly as it reads now." if not found else ": quote more of it."),
                field="edits",
                find=find[:200],
            )
        body = body.replace(find, replace)
    return body


def _ask(text: Any, what: str) -> str:
    text = str(text or "").strip()
    if not text:
        raise ValidationFailed(f"Say what you need {what}.", field="ask")
    if len(text) > MAX_ASK:
        raise ValidationFailed(f"Ask in at most {MAX_ASK:,} characters.", field="ask")
    return text


def _names(values: Any, count: int = 12, limit: int = 160) -> builtins.list[str]:
    out = []
    for value in values if isinstance(values, list) else [values] if values else []:
        text = " ".join(str(value or "").split())[:limit]
        if text and text not in out:
            out.append(text)
    return out[:count]


class Skills:
    def __init__(
        self,
        rt: Runtime,
        tasks: Tasks,
        distill: Distillation,
        brain: Brain,
        artifacts: Artifacts,
    ) -> None:
        self.rt = rt
        self.tasks = tasks
        self.distill = distill
        self.brain = brain
        self.artifacts = artifacts

    # ---------------------------------------------------------------- reading

    def find(self, who: Principal, name: str) -> BrainSkill:
        wanted = str(name or "").strip().lstrip("/")
        found = next((s for s in self.brain.files(who).skills if s.name == wanted), None)
        if found is None:
            raise NotFound(f"No skill {wanted}.", name=wanted)
        return found

    def cards(self, who: Principal) -> dict[str, Any]:
        """Every skill with what it makes, its last run and the skills that build on it (one
        others use, like a folder of fonts and logos, is not run on its own), and the new
        skills waiting in Review."""
        skills = self.brain.files(who).skills
        used_by: dict[str, builtins.list[str]] = {}
        for skill in skills:
            for dep in skill.depends_on:
                used_by.setdefault(dep, []).append(skill.name)
        last: dict[str, dict[str, Any]] = {}
        for task in self._tasks(who, RUN):
            name = self._skill_of(task)
            if name and name not in last:
                last[name] = {"task_id": task.id, "status": task.status, "at": task.updated_at}
        waiting = [
            {
                "proposal_id": p.get("id"),
                "name": (p.get("target") or {}).get("name"),
                "description": (p.get("target") or {}).get("description"),
                "task_id": p.get("task_id"),
            }
            for p in self.brain.proposals(who)
            if str(p.get("kind") or "") == "skill.create"
        ]
        return {
            "skills": [
                {
                    "name": s.name,
                    "category": s.category,
                    "description": s.description,
                    "triggers": s.triggers,
                    "artifacts": s.artifacts,
                    "makes_files": makes_files(s),
                    "files": len(s.files),
                    "last_run": last.get(s.name),
                    "used_by": used_by.get(s.name, []),
                    "use": use_of(s, used_by.get(s.name, [])),
                }
                for s in skills
            ],
            "waiting": waiting,
        }

    def versions(
        self, who: Principal, name: str, *, with_text: bool = False
    ) -> builtins.list[dict[str, Any]]:
        """Every version of the skill's procedure, newest first, from the Brain's history."""
        who.require("brain.read")
        rows = self.rt.brain.skill_versions(str(name or "").lstrip("/"), with_text=with_text)
        if rows is None:
            raise NotFound(f"No skill {name}.", name=name)
        return rows

    def runs(self, who: Principal, name: str, *, limit: int = 20) -> builtins.list[dict[str, Any]]:
        """The skill's recent runs and drafts, newest first: what was asked, where each stands,
        and what came of it (the result, the files it made, the change it proposed). A run of
        several skills shows on each of their pages."""
        mine = [t for t in self._tasks(who, RUN, DRAFT) if name in self._skills_of(t)][:limit]
        return self._shaped(who, mine, name)

    def recent(self, who: Principal, *, limit: int = 10) -> builtins.list[dict[str, Any]]:
        """The latest runs from the Skills page and from every skill, newest first."""
        return self._shaped(who, self._tasks(who, RUN)[: max(1, min(int(limit), 50))], None)

    def runs_where(
        self, who: Principal, keep: Any, *, limit: int = 20
    ) -> builtins.list[dict[str, Any]]:
        """Runs whose record `keep(about)` accepts (an agent's runs, say), newest first, shaped
        the way a skill's page shows them."""
        mine = [t for t in self._tasks(who, RUN) if keep(dict(t.provenance.get("skill") or {}))]
        return self._shaped(who, mine[: max(1, min(int(limit), 50))], None)

    def tally(self, who: Principal, key: Any) -> dict[str, dict[str, Any]]:
        """How many runs count for each thing, and when the last one was made: `key(about)`
        names what a run counts for (a saved prompt, say), or None."""
        out: dict[str, dict[str, Any]] = {}
        for task in self._tasks(who, RUN):  # newest first
            found = key(dict(task.provenance.get("skill") or {}))
            if not found:
                continue
            hit = out.setdefault(str(found), {"uses": 0, "last": task.created_at})
            hit["uses"] += 1
        return out

    def queue(
        self,
        who: Principal,
        *,
        title: str,
        purpose: str,
        instructions: str,
        request: str,
        about: dict[str, Any],
        pins: builtins.list[tuple[str, str, int]] | None = None,
    ) -> Task:
        """A run like a skill run (the same queue, result tool and review), for another part of
        Work: an agent asked for something, a prompt run from Compose."""
        who.require("tasks.write")
        return self._ask_model(
            who,
            title=title,
            purpose=purpose,
            instructions=instructions,
            request=request,
            template=RUN,
            contract=RUN_CONTRACT,
            about=about,
            pins=pins,
        )

    def _shaped(
        self, who: Principal, mine: builtins.list[Task], name: str | None
    ) -> builtins.list[dict[str, Any]]:
        if not mine:
            return []
        ids = [t.id for t in mine]
        results: dict[str, dict[str, Any]] = {}
        arts = schema.artifacts
        with self.rt.read() as tx:
            for row in tx.rows(
                sa.select(arts)
                .where(arts.c.task_id.in_(ids), arts.c.archived_at.is_(None))
                .order_by(arts.c.updated_at.desc(), arts.c.id.desc())
            ):
                if row["task_id"] in results:
                    continue
                version, data = self.artifacts.content(who, row["id"])
                results[row["task_id"]] = {
                    "artifact_id": row["id"],
                    "title": row["title"],
                    "text": data.decode("utf-8", errors="replace")[:MAX_RESULT],
                    "version": version.number,
                    "at": version.created_at,
                }
        proposals: dict[str, dict[str, Any]] = {}
        for proposal in self.brain.proposals(who):
            task_id = proposal.get("task_id")
            if task_id in ids and task_id not in proposals:
                proposals[str(task_id)] = {"id": proposal.get("id"), "status": "waiting"}
        # A proposal no longer waiting was decided: say how, from the decision's event.
        gone = {
            str((t.provenance.get("skill") or {}).get("proposal", {}).get("id")): t.id
            for t in mine
            if t.id not in proposals and (t.provenance.get("skill") or {}).get("proposal")
        }
        if gone:
            events = schema.events
            with self.rt.read() as tx:
                for row in tx.rows(
                    sa.select(events.c.subject_id, events.c.type)
                    .where(
                        events.c.workspace_id == self.rt.workspace_id,
                        events.c.subject_type == "brain_proposal",
                        events.c.subject_id.in_(list(gone)),
                        events.c.type.in_(("brain.approved", "brain.rejected")),
                    )
                    .order_by(events.c.seq)
                ):
                    proposals[gone[row["subject_id"]]] = {
                        "id": row["subject_id"],
                        "status": "approved" if row["type"] == "brain.approved" else "rejected",
                    }
        out = []
        for task in mine:
            about = dict(task.provenance.get("skill") or {})
            skills = self._skills_of(task)
            out.append(
                {
                    "task_id": task.id,
                    # the skill whose page shows it; on the Skills page, the first it followed
                    "skill": name or (skills[0] if skills else ""),
                    "skills": skills,
                    "kind": "run" if task.template == RUN else "improve",
                    "agent": about.get("agent") or None,
                    # a Workspace doc's own runs: push back on it, or continue it
                    "doc_action": about.get("doc_action") or None,
                    "ask": about.get("ask") or "",
                    "status": task.status,
                    "assignee_id": task.assignee_id,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "makes_files": bool(about.get("files")),
                    "folder": about.get("folder"),
                    "files": list(about.get("made") or []),
                    "capture": about.get("capture"),
                    "project": about.get("project"),
                    "attached": list(about.get("attached") or []),
                    "result": results.get(task.id),
                    "proposal": proposals.get(task.id) or about.get("proposal"),
                }
            )
        return out

    # ---------------------------------------------------------------- asking a model

    def run(
        self,
        who: Principal,
        name: str,
        *,
        ask: str,
        capture_id: str | None = None,
        project: str | None = None,
        files: builtins.list[str] | None = None,
    ) -> Task:
        """Ask a model to run the skill: say what is needed, optionally with something
        brought in (a capture), a project, and files the Brain holds."""
        who.require("tasks.write")
        skill = self.find(who, name)
        if use_of(skill, self._users(who, skill.name)) != "run":
            raise ValidationFailed(
                f"/{skill.name} is not run on its own here: "
                + (
                    "other skills use its files."
                    if skill.artifacts
                    else f"call it in a conversation with your AI (/{skill.name})."
                ),
                name=skill.name,
            )
        ask = _ask(ask, "from it")
        capture, focus, attached, extra = self._inputs(who, capture_id, project, files)
        files_mode = makes_files(skill)
        instructions = RUN_INSTRUCTIONS.format(
            name=skill.name, files=FILES_PART if files_mode else ""
        )
        instructions += f"\n\nThe request, from {who.name}:\n{ask}{extra}"
        request = f"{ask}\n\nUsing the skill {skill.name}: {skill.description}"
        if focus:
            request += f"\nProject: {focus['title']}"
        about: dict[str, Any] = {"name": skill.name, "ask": ask, "files": files_mode}
        return self._ask_model(
            who,
            title=f"Run /{skill.name}",
            purpose=f"Run the skill {skill.name} for {who.name}.",
            instructions=instructions,
            request=request,
            template=RUN,
            contract=RUN_CONTRACT,
            about=self._with_inputs(about, capture, focus, attached),
            capture=capture,
        )

    def run_many(
        self,
        who: Principal,
        names: builtins.list[str],
        *,
        ask: str,
        capture_id: str | None = None,
        project: str | None = None,
        files: builtins.list[str] | None = None,
    ) -> Task:
        """Ask a model for what is needed with the skills chosen on the Skills page, followed
        in the order given. With one, it is that skill's run; with none, the Brain picks the
        skill that fits (the run's context lists it), or the work is done without one."""
        wanted = list(
            dict.fromkeys(
                str(n or "").strip().lstrip("/") for n in names or [] if str(n or "").strip()
            )
        )
        if len(wanted) > MAX_SKILLS:
            raise ValidationFailed(
                f"Choose at most {MAX_SKILLS} skills for one run.", field="names"
            )
        if len(wanted) == 1:
            return self.run(
                who, wanted[0], ask=ask, capture_id=capture_id, project=project, files=files
            )
        who.require("tasks.write")
        skills = [self.find(who, name) for name in wanted]
        for skill in skills:
            if use_of(skill, self._users(who, skill.name)) != "run":
                raise ValidationFailed(
                    f"/{skill.name} is not run on its own here: choose the skills you run.",
                    name=skill.name,
                )
        ask = _ask(ask, "from them" if skills else "done")
        capture, focus, attached, extra = self._inputs(who, capture_id, project, files)
        files_mode = any(makes_files(skill) for skill in skills)
        if skills:
            listed = ", ".join(f"/{skill.name}" for skill in skills)
            instructions = RUN_MANY_INSTRUCTIONS.format(
                names=listed, files=FILES_PART_MANY if files_mode else ""
            )
            request = f"{ask}\n\nUsing the skills " + "; ".join(
                f"{skill.name}: {skill.description}" for skill in skills
            )
            title, purpose = f"Run {listed}", f"Run the skills {listed} for {who.name}."
        else:
            instructions, request = PICK_INSTRUCTIONS, ask
            title = "Run what fits: " + (ask if len(ask) <= 60 else ask[:57] + "...")
            purpose = f"Do what {who.name} asked, with the skill that fits."
        instructions += f"\n\nThe request, from {who.name}:\n{ask}{extra}"
        if focus:
            request += f"\nProject: {focus['title']}"
        about: dict[str, Any] = {
            "name": skills[0].name if skills else "",
            "names": [skill.name for skill in skills],
            "ask": ask,
            "files": files_mode,
        }
        return self._ask_model(
            who,
            title=title,
            purpose=purpose,
            instructions=instructions,
            request=request,
            template=RUN,
            contract=RUN_CONTRACT,
            about=self._with_inputs(about, capture, focus, attached),
            capture=capture,
        )

    def _inputs(
        self,
        who: Principal,
        capture_id: str | None,
        project: str | None,
        files: builtins.list[str] | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, builtins.list[str], str]:
        """What a run is pointed to besides the request, and the lines that say so."""
        capture = self._capture(who, capture_id) if capture_id else None
        focus = self._project(who, project) if project else None
        attached = self._attached(who, files)
        extra = ""
        if focus:
            extra += f"\n\nThis is for the project {focus['title']} ({focus['id']})."
        if capture:
            extra += f"\n\nUse the pinned item, “{capture['title']}” ({capture['id']})."
        if attached:
            extra += "\n\nRead these files with get_brain_reference: " + ", ".join(attached) + "."
        return capture, focus, attached, extra

    @staticmethod
    def _with_inputs(
        about: dict[str, Any],
        capture: dict[str, Any] | None,
        focus: dict[str, Any] | None,
        attached: builtins.list[str],
    ) -> dict[str, Any]:
        if capture:
            about["capture"] = capture
        if focus:
            about["project"] = focus
        if attached:
            about["attached"] = attached
        return about

    def improve(
        self,
        who: Principal,
        name: str,
        *,
        ask: str,
        capture_id: str | None = None,
        example: str | None = None,
    ) -> Task:
        """Ask a model for a better version of the skill; it waits in Review. It can learn
        from an example: something it made that the person liked (`example`, a run's result),
        or something they brought in or wrote (`capture_id`), such as a result they edited."""
        who.require("brain.propose")
        skill = self.find(who, name)
        ask = _ask(ask, "changed")
        capture = self._capture(who, capture_id) if capture_id else None
        result = self._result(who, skill.name, example) if example else None
        instructions = IMPROVE_INSTRUCTIONS.format(name=skill.name)
        instructions += f"\n\nWhat {who.name} wants changed:\n{ask}"
        shown = [f"“{x['title']}”" for x in (result, capture) if x]
        if shown:
            instructions += (
                f"\n\nLearn from the pinned example ({' and '.join(shown)}): it shows what "
                f"{who.name} wants the skill to make. Change the skill so that what it makes "
                "comes out like it, in the places the request names; say in reason what you "
                "took from it."
            )
        about: dict[str, Any] = {"name": skill.name, "ask": ask}
        if result:
            about["example"] = {"id": result["id"], "title": result["title"]}
        if capture:
            about["capture"] = {"id": capture["id"], "title": capture["title"]}
        pins = [("artifact", result["id"], result["version"])] if result else []
        return self._ask_model(
            who,
            title=f"Improve /{skill.name}",
            purpose=f"Propose a better version of the skill {skill.name}.",
            instructions=instructions,
            request=f"{ask}\n\nImproving the skill {skill.name}: {skill.description}",
            template=DRAFT,
            contract=DRAFT_CONTRACT,
            about=about,
            capture=capture,
            pins=pins,
        )

    def draft(self, who: Principal, *, ask: str, capture_id: str | None = None) -> Task:
        """Ask a model to write a new skill from a description (or from something brought in:
        "teach from this"); it waits in Review."""
        who.require("brain.propose")
        ask = _ask(ask, "the skill to do")
        capture = self._capture(who, capture_id) if capture_id else None
        categories = sorted({s.category for s in self.brain.files(who).skills if s.category})
        instructions = NEW_INSTRUCTIONS.format(
            source=", and the pinned item it should teach from" if capture else "",
            categories=f" (one the Brain uses: {', '.join(categories)}; or a new one)"
            if categories
            else "",
        )
        instructions += f"\n\nWhat {who.name} wants the skill to do:\n{ask}"
        if capture:
            instructions += (
                f"\n\nTeach from the pinned item, “{capture['title']}” ({capture['id']})."
            )
        about: dict[str, Any] = {"name": None, "ask": ask}
        if capture:
            about["capture"] = capture
        return self._ask_model(
            who,
            title="Write a new skill",
            purpose="Propose a new skill for the Brain.",
            instructions=instructions,
            request=ask,
            template=DRAFT,
            contract=DRAFT_CONTRACT,
            about=about,
            capture=capture,
        )

    # ---------------------------------------------------------------- what a model sends back

    def save_result(self, who: Principal, *, run_id: str, title: str, text: str) -> dict[str, Any]:
        """What a skill run made, shown on the skill's page; saved again in the same run, it
        is a new version of the same result."""
        who.require("runs.write")
        task = self._task_of_run(who, run_id, RUN, "This run is not a skill run.")
        text = str(text or "").strip()
        if not text:
            raise ValidationFailed(
                "Save the result itself: the whole text, as Markdown.", field="text"
            )
        if len(text) > MAX_RESULT:
            raise ValidationFailed(f"A result is at most {MAX_RESULT:,} characters.", field="text")
        title = " ".join(str(title or "").split())[:200] or task["title"]
        arts = schema.artifacts
        with self.rt.read() as tx:
            earlier = tx.first(
                sa.select(arts.c.id).where(
                    arts.c.task_id == task["id"],
                    arts.c.created_by == who.actor_id,
                    arts.c.archived_at.is_(None),
                )
            )
        made = self.artifacts.create(
            who,
            type="document",
            title=title,
            content=text,
            run_id=run_id,
            artifact_id=earlier["id"] if earlier else None,
            mime="text/markdown",
        )
        return {
            "artifact_id": made.artifact.id,
            "version": made.version.number,
            "title": made.artifact.title,
        }

    def propose(
        self,
        who: Principal,
        *,
        run_id: str,
        body: str | None = None,
        edits: builtins.list[dict[str, Any]] | None = None,
        target: str | None = None,
        name: str | None = None,
        category: str | None = None,
        description: str | None = None,
        when_to_use: str | None = None,
        triggers: builtins.list[str] | None = None,
        artifacts: builtins.list[str] | None = None,
        loads: builtins.list[str] | None = None,
        reason: str = "",
    ) -> BrainProposal:
        """A model's new skill, or new version of one, from a draft run: it waits in Review."""
        who.require("brain.propose")
        task = self._task_of_run(who, run_id, DRAFT, "This run does not draft a skill.")
        about = dict((task["provenance"] or {}).get("skill") or {})
        wanted = about.get("name")
        target = str(target or "").strip().lstrip("/") or None
        if wanted and target != wanted:
            raise ValidationFailed(
                f'This run improves {wanted}: pass target "{wanted}".', field="target"
            )
        if not wanted and target:
            raise ValidationFailed(
                "This run writes a new skill: leave out target and give it a name.",
                field="target",
            )
        if edits and str(body or "").strip():
            raise ValidationFailed("Send either edits or the whole body, not both.", field="body")
        if edits:
            if not target:
                raise ValidationFailed(
                    "A new skill needs its whole procedure as body.", field="edits"
                )
            current = self.rt.brain.skill_source(target)
            if current is None:
                raise NotFound(f"No skill {target}.", name=target)
            shown = self.rt.brain.skill(target)
            body = apply_edits(current, list(edits), shown=shown.text if shown else "")
        body = str(body or "").strip()
        if not body:
            raise ValidationFailed(
                "Send the change as edits, or the whole procedure as body.", field="body"
            )
        if len(body) > MAX_BODY:
            raise ValidationFailed(f"A skill is at most {MAX_BODY:,} characters.", field="body")
        sources = [f"task:{task['id']}", f"run:{run_id}"]
        capture = about.get("capture") or {}
        if capture.get("id"):
            sources.append(f"context_item:{capture['id']}")
        result = self.rt.brain.propose_skill(
            proposer=proposer(who),
            sources=sources,
            body=body,
            target=target,
            name=None if target else str(name or "").strip(),
            category=None if target else str(category or "").strip().lower(),
            description=" ".join(str(description or "").split()) or None,
            when_to_use=" ".join(str(when_to_use or "").split()) or None,
            triggers=_names(triggers) or None,
            artifacts=_names(artifacts, 8, 40) or None,
            loads=_names(loads, 20, 200) or None,
            reason=" ".join(str(reason or "").split())[:600],
            evidence=str(about.get("ask") or "")[:2000],
        )
        if result.status == "refused":
            raise ValidationFailed(result.message)
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task["id"], "task")
            provenance = dict(row["provenance"] or {})
            provenance["skill"] = {
                **dict(provenance.get("skill") or {}),
                "proposal": {"id": result.proposal_id, "status": result.status},
                "proposed": target or str(name or "").strip(),
            }
            tx.update(schema.tasks, row, {"provenance": provenance})
            tx.emit(
                "skill.proposed",
                actor_id=who.actor_id,
                subject_type="brain_proposal",
                subject_id=result.proposal_id or (target or str(name or "")),
                project_id=row["project_id"],
                data={
                    "skill": target or str(name or "").strip(),
                    "change": "update" if target else "new",
                    "status": result.status,
                    "task_id": row["id"],
                    "run_id": run_id,
                },
            )
        return result

    # ---------------------------------------------------------------- the person's own edit

    def edit(
        self,
        who: Principal,
        name: str,
        *,
        body: str,
        description: str | None = None,
        when_to_use: str | None = None,
        triggers: builtins.list[str] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """The person's own new version of a skill: it applies at once, as an undo point."""
        who.require("brain.govern")
        skill = self.find(who, name)
        body = str(body or "").strip()
        if not body:
            raise ValidationFailed("Write the skill's steps.", field="body")
        if len(body) > MAX_BODY:
            raise ValidationFailed(f"A skill is at most {MAX_BODY:,} characters.", field="body")
        why = " ".join(str(reason or "").split())[:600] or "Edited in the app"
        made = self.rt.brain.propose_skill(
            proposer=proposer(who),
            sources=[],
            body=body,
            target=skill.name,
            description=" ".join(str(description or "").split()) or None,
            when_to_use=" ".join(str(when_to_use or "").split()) or None,
            triggers=_names(triggers) if triggers is not None else None,
            reason=why,
        )
        if made.status != "pending" or not made.proposal_id:
            raise Conflict(made.message)
        return self.brain.decide(who, made.proposal_id, approve=True, reason=why)

    # ---------------------------------------------------------------- files a run made

    def record_files(
        self,
        who: Principal,
        task_id: str,
        *,
        folder: str,
        files: builtins.list[dict[str, Any]],
    ) -> None:
        """Where a run that makes files worked, and what it left there (the runner's report)."""
        who.require("tasks.write")
        with self.rt.write() as tx:
            row = tx.one(schema.tasks, task_id, "task")
            if row["template"] != RUN:
                raise ValidationFailed("Only a skill run makes files.", task_id=task_id)
            provenance = dict(row["provenance"] or {})
            provenance["skill"] = {
                **dict(provenance.get("skill") or {}),
                "folder": folder,
                "made": [{"name": str(f["name"]), "size": int(f.get("size") or 0)} for f in files][
                    :200
                ],
            }
            tx.update(schema.tasks, row, {"provenance": provenance})

    def made_file(self, who: Principal, task_id: str, name: str) -> str:
        """Where one file a run made is on disk, for a download."""
        task = self.tasks.get(who, task_id)
        about = dict(task.provenance.get("skill") or {})
        folder = str(about.get("folder") or "")
        listed = {str(f.get("name")) for f in about.get("made") or []}
        if not folder or name not in listed:
            raise NotFound(f"This run made no file {name}.", name=name)
        root = os.path.realpath(folder)
        full = os.path.realpath(os.path.join(root, *name.split("/")))
        if os.path.commonpath([root, full]) != root or not os.path.isfile(full):
            raise NotFound(f"{name} is no longer in the run's folder.", name=name)
        return full

    # ---------------------------------------------------------------- internals

    def _ask_model(
        self,
        who: Principal,
        *,
        title: str,
        purpose: str,
        instructions: str,
        request: str,
        template: str,
        contract: dict[str, Any],
        about: dict[str, Any],
        capture: dict[str, Any] | None = None,
        pins: builtins.list[tuple[str, str, int]] | None = None,
    ) -> Task:
        """The task a model takes, with what it reads pinned before anyone can claim it.
        Without a model to name, it waits for one (the local CLI takes it when the person
        runs it here)."""
        with self.rt.read() as tx:
            try:
                assignee: str | None = self.distill._default_assignee(tx)
            except ValidationFailed:
                assignee = None
        task = self.tasks.create(
            who,
            title=title,
            purpose=purpose,
            instructions=instructions,
            assignee_id=assignee,
            schedule={"kind": "manual"},
            output_contract=contract,
            review_policy="auto",
            brain_request=request[:2000],
            template=template,
            provenance={"skill": about},
        )
        if capture:
            self.tasks.pin(
                who,
                task.id,
                ref_type="context_item",
                ref_id=capture["id"],
                version=capture["revision"],
            )
        for ref_type, ref_id, version in pins or []:
            self.tasks.pin(who, task.id, ref_type=ref_type, ref_id=ref_id, version=version)
        return self.tasks.mark_ready(who, task.id) if assignee else task

    def made_in(self, who: Principal, folder: str) -> dict[str, Any] | None:
        """The skill run that worked in one folder of the outputs folder: what was asked of
        which skill, for which project, with which files, and its runs (each run's id is how
        to read what the Brain handed it)."""
        wanted = os.path.normcase(os.path.abspath(folder))
        for task in self._tasks(who, RUN):
            about = dict(task.provenance.get("skill") or {})
            there = str(about.get("folder") or "")
            if not there or os.path.normcase(os.path.abspath(there)) != wanted:
                continue
            runs = schema.task_runs
            with self.rt.read() as tx:
                rows = tx.rows(
                    sa.select(runs.c.id, runs.c.actor_id, runs.c.claimed_at, runs.c.status)
                    .where(runs.c.task_id == task.id)
                    .order_by(runs.c.claimed_at)
                )
                names = {
                    r["id"]: r["name"]
                    for r in tx.rows(
                        sa.select(schema.actors.c.id, schema.actors.c.name).where(
                            schema.actors.c.id.in_({r["actor_id"] for r in rows})
                        )
                    )
                }
            return {
                "task_id": task.id,
                "skill": self._skill_of(task),
                "ask": about.get("ask") or "",
                "project": about.get("project"),
                "attached": list(about.get("attached") or []),
                "capture": about.get("capture"),
                "status": task.status,
                "created_at": task.created_at,
                "runs": [
                    {
                        "id": r["id"],
                        "at": r["claimed_at"],
                        "status": r["status"],
                        "by": names.get(r["actor_id"], "a model"),
                    }
                    for r in rows
                ],
            }
        return None

    def _tasks(self, who: Principal, *templates: str) -> builtins.list[Task]:
        who.require("tasks.read")
        table = schema.tasks
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table)
                .where(
                    table.c.workspace_id == self.rt.workspace_id,
                    table.c.template.in_(templates),
                    table.c.archived_at.is_(None),
                )
                # ids count up in creation order, so two made in one moment keep theirs
                .order_by(table.c.created_at.desc(), table.c.id.desc())
                .limit(RECENT)
            )
        return [Task.from_row(r) for r in rows if who.sees_project(r["project_id"])]

    def _users(self, who: Principal, name: str) -> builtins.list[str]:
        """The skills that build on this one."""
        return [s.name for s in self.brain.files(who).skills if name in s.depends_on]

    @staticmethod
    def _skill_of(task: Task) -> str | None:
        about = task.provenance.get("skill") or {}
        return about.get("name") if isinstance(about, dict) else None

    @staticmethod
    def _skills_of(task: Task) -> builtins.list[str]:
        """Every skill a run followed: one, several chosen on the Skills page, or none (the
        Brain picked)."""
        about = task.provenance.get("skill") or {}
        if not isinstance(about, dict):
            return []
        names = about.get("names")
        if isinstance(names, list):
            return [str(n) for n in names if n]
        return [str(about["name"])] if about.get("name") else []

    def _task_of_run(
        self, who: Principal, run_id: str, template: str, wrong: str
    ) -> dict[str, Any]:
        with self.rt.read() as tx:
            run = tx.one(schema.task_runs, run_id, "run")
            if run["actor_id"] != who.actor_id:
                raise PermissionDenied("That run belongs to someone else.", run_id=run_id)
            task = tx.one(schema.tasks, run["task_id"], "task")
        if task["template"] != template:
            raise ValidationFailed(wrong, run_id=run_id)
        return task

    def _capture(self, who: Principal, capture_id: str) -> dict[str, Any]:
        with self.rt.read() as tx:
            row = tx.get(schema.context_items, capture_id)
            if row is None or not open_to(tx, who, row):
                raise NotFound(f"No note with id {capture_id}.", id=capture_id)
        if not str(row["body"] or "").strip():
            raise ValidationFailed("It has no text yet.", field="capture_id")
        return {"id": row["id"], "title": row["title"], "revision": row["revision"]}

    def _result(self, who: Principal, name: str, artifact_id: str) -> dict[str, Any]:
        """What a run of this skill made, as an example to learn from."""
        artifact = self.artifacts.get(who, artifact_id)
        with self.rt.read() as tx:
            task = tx.get(schema.tasks, artifact.task_id) if artifact.task_id else None
        made_by = ((task or {}).get("provenance") or {}).get("skill") or {}
        if task is None or task["template"] != RUN or made_by.get("name") != name:
            raise NotFound(f"That is not something /{name} made.", example=artifact_id)
        return {"id": artifact.id, "title": artifact.title, "version": artifact.current_version}

    def _project(self, who: Principal, project: str) -> dict[str, Any]:
        wanted = str(project or "").strip()
        found = next((p for p in self.brain.projects(who) if p.id == wanted), None)
        if found is None:
            raise NotFound(f"No project {wanted}.", project=wanted)
        return {"id": found.id, "title": found.title}

    def _attached(self, who: Principal, files: builtins.list[str] | None) -> builtins.list[str]:
        paths = [str(p).strip() for p in files or [] if str(p).strip()]
        if len(paths) > MAX_ATTACHED:
            raise ValidationFailed(f"Point a run to at most {MAX_ATTACHED} files.", field="files")
        if not paths:
            return []
        held = {f.path for f in self.brain.files(who).references}
        missing = [p for p in paths if p not in held]
        if missing:
            raise NotFound(f"The Brain holds no document at {missing[0]}.", path=missing[0])
        return list(dict.fromkeys(paths))
