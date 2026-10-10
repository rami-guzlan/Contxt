"""The workspace's side of the Brain: governed reads, proposals and the distill flow.

Models may propose long-term context; the Brain records the proposal and a person (or an
explicit policy) approves it. The workspace adds lineage: which notes or AI work a proposal
came from, and an event naming who proposed it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.ports import (
    BrainCatalog,
    BrainDocument,
    BrainEntry,
    BrainFileContent,
    BrainFiles,
    BrainHit,
    BrainProject,
    BrainProposal,
)

from .distill import RECONCILE
from .runtime import Runtime, recall, remember

# What the owner can do with this computer's local models (Settings, On this computer).
LOCAL_ACTIONS = ("check", "default", "download", "remove", "speed", "claude_code")

KINDS = ("fact", "rule", "preference", "decision", "procedure", "identity", "state")
MAX_FILE = 10 * 1024 * 1024  # the Brain's own ceiling for one document or asset
ACTIONS = (
    "approve",
    "reject",
    "unschedule",  # a scheduled revision waits for a decision again
    "archive",
    "edit",
    "restore",
    "unarchive",
    "update",
    "verify",
    "mark",
)
# About an entry rather than a waiting proposal.
ENTRY_ACTIONS = ("archive", "edit", "restore", "unarchive", "update", "verify", "mark")
CONFIDENCE = ("confirmed", "inferred", "disputed", "unknown")
# What a person sets on an entry directly (the Brain checks each value).
ENTRY_FIELDS = (
    "owner",
    "review_days",
    "review_by",
    "classification",
    "area",
    "topic",
    "aliases",  # a project's other names, comma separated
    # When it reaches a model: standing, domain (a must-hold), on-demand or manual, and for
    # a must-hold the domains it covers, the words that bring it in (both comma separated),
    # its one line and whether the startup context shows that line in full.
    "load",
    "applies_to",
    "triggers",
    "must_text",
    "critical",
    "baseline",  # the owner marks it a baseline: a change to it waits, with a reason
    "as_of",  # the day a changing value was true (YYYY-MM-DD)
    "valid_until",  # the last day it holds
    "library",  # an item's kind in the Library: guide, reference, influence or asset
    "refresh",  # how often the Library fetches it again: never, weekly or monthly
    "origin",  # where a filed item came from: capture:recording, library, run:<id>, ...
    "title",  # a filed item's title, on its card
    "project_id",  # the project a filed item is for
    # A prompt's tags and what it is used with (all but the agent comma separated).
    "tags",
    "prompt_skills",
    "prompt_agent",
    "prompt_docs",
    "prompt_reads",
)
LIBRARY_KINDS = ("guide", "reference", "influence", "asset")
LIBRARY_REFRESH = ("never", "weekly", "monthly")
FIELD_LIMITS = {  # characters; other fields take 200
    "triggers": 1200,
    "applies_to": 600,
    "tags": 600,
    "prompt_skills": 2000,
    "prompt_docs": 2000,
    "prompt_reads": 2000,
}
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,80}$")  # a version: a commit, or "current"
MAX_TEXT = 60_000  # characters in one entry a person writes or edits
SUMMARY_LIMIT = 200  # characters in the one line a list shows for an entry
MAX_DECISIONS = 200
TOPIC = re.compile(r"^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9-]*$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ENTRY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$")
FILE_STATUS = re.compile(r"^[a-z][a-z -]{0,29}$")  # draft, sent, final, in review
# What a project update may change, as the Brain's Focus journal keeps it.
PROJECT_STATE = ("status", "current", "next", "blockers", "decisions", "completed")
MAX_REQUEST = 4000  # characters in a request to preview
MAX_ALIASES = 12


def proposer(who: Principal) -> str:
    """How a proposal names the real actor; the Brain itself records its owner."""
    return f"{who.kind}:{who.name} ({who.actor_id})"


def display_name(raw: str | None) -> str:
    """A proposer as people read it: "model:Claude Code (act_...)" is "Claude Code"."""
    found = re.match(r"^(?:human|model|system):(.+?) \([^()]*\)$", str(raw or ""))
    if found:
        return found.group(1)
    return str(raw or "").strip() or "Someone"


@dataclass(frozen=True)
class ReviewBatch:
    """Waiting proposals that came from one piece of work: a task's run (a distillation, say),
    one conversation, or one person."""

    key: str  # task:<id> | session:<id> | proposer:<raw>
    title: str
    proposer: str
    created: str
    proposal_ids: list[str]
    counts: dict[str, int]
    topics: list[dict[str, Any]] = field(default_factory=list)  # [{"route_key", "count"}]
    task_id: str | None = None
    task_status: str | None = None
    documents: list[dict[str, str]] = field(default_factory=list)  # what the task read
    # A reconcile request's batch: the proposal and entry it settles, and which is current.
    reconciles: dict[str, str] | None = None


@dataclass(frozen=True)
class BrainReview:
    batches: list[ReviewBatch]
    proposals: list[dict[str, Any]]  # each waiting proposal, with its `analysis`


def _needs_a_look(analysis: dict[str, Any]) -> bool:
    """Something to settle before approving: a contradiction, a near repeat, a duplicate
    among the proposals, or a problem."""
    return bool(
        analysis.get("conflicts")
        or any(o.get("close") for o in analysis.get("overlaps") or [])
        or analysis.get("duplicates")
        or analysis.get("problems")
    )


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    analyses = [row.get("analysis") or {} for row in rows]
    look = sum(1 for a in analyses if _needs_a_look(a))
    return {
        "total": len(rows),
        "new": sum(1 for a in analyses if a.get("change") == "new"),
        "updates": sum(1 for a in analyses if a.get("change") in ("update", "retire")),
        "replaces": sum(1 for a in analyses if a.get("change") == "new" and a.get("replaces")),
        "conflicts": sum(1 for a in analyses if a.get("conflicts")),
        "close": sum(1 for a in analyses if any(o.get("close") for o in a.get("overlaps") or [])),
        "duplicates": sum(1 for a in analyses if a.get("duplicates")),
        "problems": sum(1 for a in analyses if a.get("problems")),
        "files": sum(1 for a in analyses if a.get("change") == "file"),
        "skills": sum(1 for a in analyses if a.get("change") == "skill"),
        "new_topics": sum(1 for a in analyses if a.get("new_topic")),
        "look": look,
        "clear": len(rows) - look,
    }


def _ids(value: Any, name: str) -> list[str]:
    """Entry ids a proposal or decision names, checked for shape (the Brain checks they exist)."""
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationFailed(f"{name} is a list of entry ids.", field=name)
    ids = list(dict.fromkeys(v.strip() for v in value if v.strip()))
    if any(not ENTRY_ID.match(v) for v in ids):
        raise ValidationFailed(f"{name} holds something that is not an entry id.", field=name)
    return ids


def _topic(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if not TOPIC.match(text):
        raise ValidationFailed("A topic reads area/topic, for example brand/voice.", field="topic")
    return text


def _decision(item: dict[str, Any]) -> dict[str, Any]:
    """One decision, checked and reduced to what the Brain port takes."""
    if not isinstance(item, dict):
        raise ValidationFailed("Each decision is an object.")
    action = str(item.get("action") or "")
    if action not in ACTIONS:
        raise ValidationFailed(f"A decision is one of {', '.join(ACTIONS)}.", field="action")
    reason = " ".join(str(item.get("reason") or "").split())[:500]
    title = " ".join(str(item.get("title") or "").split())[:200]
    summary = " ".join(str(item.get("summary") or "").split())[:300]
    body = _text(item.get("body"))
    if action in ENTRY_ACTIONS:
        entry = str(item.get("entry_id") or "").strip()
        if not ENTRY_ID.match(entry):
            raise ValidationFailed(f"Name the entry to {action}.", field="entry_id")
        out: dict[str, Any] = {"action": action, "entry_id": entry, "reason": reason}
        if action == "edit":
            if body is None:
                raise ValidationFailed("An edit needs the entry's new text.", field="body")
            out["body"] = body
            out.update({k: v for k, v in (("title", title), ("summary", summary)) if v})
            if item.get("minor"):
                out["minor"] = True  # a typo or cleanup: not new knowledge
        elif action == "restore":
            ref = str(item.get("ref") or "").strip()
            if not REF.match(ref):
                raise ValidationFailed("Name the version to restore.", field="ref")
            out["ref"] = ref
        elif action == "verify" and item.get("confidence"):
            confidence = str(item["confidence"])
            if confidence not in CONFIDENCE:
                raise ValidationFailed(
                    f"Confidence is one of {', '.join(CONFIDENCE)}.", field="confidence"
                )
            out["confidence"] = confidence
        elif action == "mark":
            state = str(item.get("state") or "")
            if state not in ("stale", "disputed"):
                raise ValidationFailed("Mark an entry stale or disputed.", field="state")
            if not reason:
                raise ValidationFailed(
                    "Say why, so the next person knows what to check.", field="reason"
                )
            out["state"] = state
        elif action == "update":
            fields = item.get("fields")
            if not isinstance(fields, dict) or not fields:
                raise ValidationFailed("Say which details to change.", field="fields")
            unknown = sorted(str(k) for k in fields if k not in ENTRY_FIELDS)
            if unknown:
                raise ValidationFailed(
                    f"{', '.join(unknown)} cannot be set on an entry; set "
                    f"{', '.join(ENTRY_FIELDS)}.",
                    field="fields",
                )
            out["fields"] = {
                str(k): (
                    "" if v is None else " ".join(str(v).split())[: FIELD_LIMITS.get(str(k), 200)]
                )
                for k, v in fields.items()
            }
        return out
    proposal_id = str(item.get("proposal_id") or "").strip()
    if not proposal_id:
        raise ValidationFailed("Name the proposal to decide.", field="proposal_id")
    out = {"action": action, "proposal_id": proposal_id, "reason": reason}
    if action == "approve":
        replaces = _ids(item.get("replaces"), "replaces")
        topic = _topic(item.get("topic"))
        if replaces:
            out["replaces"] = replaces
        if topic:
            out["topic"] = topic
        if title:
            out["title"] = title
        if body is not None:  # approved in the person's own words
            out["body"] = body
        if summary:
            out["summary"] = summary
    return out


def _text(value: Any) -> str | None:
    """A person's text for an entry: None when not given; refused when empty or too long."""
    if value is None:
        return None
    text = str(value).replace("\r\n", "\n").strip()
    if not text:
        raise ValidationFailed("The text is empty.", field="body")
    if len(text) > MAX_TEXT:
        raise ValidationFailed(
            f"Keep an entry under {MAX_TEXT:,} characters; split longer material into a "
            "reference document.",
            field="body",
        )
    return text


ORIGIN = re.compile(r"^[a-z]+:[A-Za-z0-9_.:@/-]{0,200}$")
# A source a proposal names, as the kind of origin the Brain records.
SOURCE_ORIGINS = {
    "context_item": "file",
    "artifact": "output",
    "meeting": "meeting",
    "task": "work",
}


def _origin(given: Any, run_id: str | None, sources: list[str], who: Principal) -> str:
    """Where a proposal came from, as the Brain records it (`<kind>:<reference>`)."""
    if given:
        text = str(given).strip()
        if not ORIGIN.match(text):
            raise ValidationFailed(
                "An origin reads kind:reference, like doc:ctx_1@r3.", field="origin"
            )
        return text
    if run_id:
        return f"work:{run_id}"
    for source in sources:
        kind, _, ident = str(source).partition(":")
        if kind in SOURCE_ORIGINS and ident:
            return f"{SOURCE_ORIGINS[kind]}:{ident}"
    return "you:" if who.is_human else "workspace:"


def _task_of(row: dict[str, Any]) -> str | None:
    task = row.get("task_id")
    if task:
        return str(task)
    return next(
        (s[len("task:") :] for s in row.get("sources") or [] if str(s).startswith("task:")), None
    )


class Brain:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def status(self, who: Principal) -> dict[str, Any]:
        who.require("brain.read")
        return self.rt.brain.status()

    def catalog(self, who: Principal) -> BrainCatalog:
        """Every entry, by area and topic: the Brain browsed rather than searched."""
        who.require("brain.read")
        return self.rt.brain.catalog()

    def attention(self, who: Principal) -> dict[str, Any]:
        """What in the Brain wants a look, and how much each entry was used this week."""
        who.require("brain.read")
        return self.rt.brain.attention()

    def files(self, who: Principal) -> BrainFiles:
        """The reference documents, assets and skills the Brain holds."""
        who.require("brain.read")
        return self.rt.brain.files()

    def file_content(
        self, who: Principal, path: str, *, original: bool = False
    ) -> BrainFileContent:
        who.require("brain.read")
        found = self.rt.brain.file_content(path, original=original)
        if found is None:
            raise NotFound(f"The Brain holds no file at {path}.")
        return found

    def history(self, who: Principal, entry_id: str) -> list[dict[str, Any]]:
        """Who approved, verified or marked an entry, newest first."""
        who.require("brain.read")
        return self.rt.brain.history(entry_id)

    # ---------------------------------------------------------------- the supply chain

    def inventory(self, who: Principal) -> list[dict[str, Any]]:
        """Everything the Brain holds, as one table: each entry (live and archived), skill
        and filed document with its owner, origin, confidence, review cadence, sensitivity,
        changes and use."""
        who.require("brain.read")
        return self.rt.brain.inventory()

    def entry_details(self, who: Principal, entry_id: str) -> dict[str, Any]:
        who.require("brain.read")
        found = self.rt.brain.entry_details(entry_id)
        if found is None:
            raise NotFound(f"No Brain entry {entry_id}.", id=entry_id)
        return found

    def versions(
        self, who: Principal, entry_id: str, *, with_text: bool = False
    ) -> list[dict[str, Any]]:
        """Every version of an entry, newest first, each with who made it and why."""
        who.require("brain.read")
        found = self.rt.brain.versions(entry_id, with_text=with_text)
        if found is None:
            raise NotFound(f"No Brain entry {entry_id}.", id=entry_id)
        return found

    def version(self, who: Principal, entry_id: str, ref: str) -> dict[str, Any]:
        who.require("brain.read")
        found = self.rt.brain.version(entry_id, ref)
        if found is None:
            raise NotFound(f"No version {ref} of {entry_id}.", id=entry_id, ref=ref)
        return found

    def activity(
        self,
        who: Principal,
        *,
        entry_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        actions: list[str] | None = None,
        by: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Every governed event, newest first: proposals decided, edits, checks, restores,
        archives, policy changes and undos."""
        who.require("brain.read")
        return self.rt.brain.activity(
            entry_id=entry_id,
            since=since,
            until=until,
            actions=actions,
            by=by,
            limit=max(1, min(int(limit), 1000)),
        )

    def use(self, who: Principal, entry_id: str, *, days: int = 90) -> dict[str, Any]:
        """Where an entry went: by day, in total, and each recent handout, with the AI work
        among them named by its task."""
        who.require("brain.read")
        found = self.rt.brain.use(entry_id, days=max(1, min(int(days), 3650)))
        if found is None:
            raise NotFound(f"No Brain entry {entry_id}.", id=entry_id)
        runs = [
            str(r["session_id"])[len("work:") :]
            for r in found.get("recent") or []
            if str(r.get("session_id") or "").startswith("work:")
        ]
        if runs:
            named = self._runs(who, runs)
            for row in found.get("recent") or []:
                run = named.get(str(row.get("session_id") or "")[len("work:") :])
                if run:
                    row["work"] = run
        return found

    def _runs(self, who: Principal, run_ids: list[str]) -> dict[str, dict[str, Any]]:
        """{run id: its task, project and model}, for runs the caller may see."""
        runs, tasks, actors = schema.task_runs, schema.tasks, schema.actors
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(
                    runs.c.id,
                    runs.c.task_id,
                    tasks.c.title,
                    tasks.c.project_id,
                    actors.c.name.label("actor"),
                )
                .join(tasks, tasks.c.id == runs.c.task_id)
                .join(actors, actors.c.id == runs.c.actor_id)
                .where(runs.c.id.in_(list(dict.fromkeys(run_ids))))
            )
        return {
            r["id"]: {
                "run_id": r["id"],
                "task_id": r["task_id"],
                "title": r["title"],
                "project_id": r["project_id"],
                "actor": r["actor"],
            }
            for r in rows
            if who.sees_project(r["project_id"])
        }

    def gaps(self, who: Principal, *, days: int = 30) -> list[dict[str, Any]]:
        """Requests the Brain served poorly: nothing matched, or the AI had to find an entry
        itself that the packet should have brought."""
        who.require("brain.read")
        return self.rt.brain.gaps(days=max(1, min(int(days), 365)))

    def dismiss_gap(self, who: Principal, key: str) -> None:
        who.require("brain.govern")
        text = str(key or "").strip()
        if not text or len(text) > 300:
            raise ValidationFailed("Name the gap to dismiss.", field="key")
        self.rt.brain.dismiss_gap(text)

    def flow(self, who: Principal, *, days: int = 7) -> dict[str, Any]:
        """The supply chain over `days`: what came in, what was decided, what waits, what was
        handed out, and the health of what the Brain holds."""
        who.require("brain.read")
        return self.rt.brain.flow(days=max(1, min(int(days), 365)))

    def policies(self, who: Principal) -> dict[str, Any]:
        who.require("brain.read")
        return self.rt.brain.policies()

    def models(self, who: Principal) -> dict[str, Any]:
        """The local model that matches by meaning: here, being fetched, or not yet."""
        who.require("brain.read")
        return self.rt.brain.models()

    def download_models(self, who: Principal) -> dict[str, Any]:
        """Fetch the matching model, once: the owner's call, never automatic."""
        who.require("workspace.admin")
        if not who.is_human:
            raise PermissionDenied("Only a person downloads a model.")
        return self.rt.brain.download_models()

    def local_models(self, who: Principal) -> dict[str, Any]:
        """This computer's local models: the machine, its setup, each role's model and the
        pinned options, and whether the retrieval engine runs in full or in fallback."""
        who.require("brain.read")
        return self.rt.brain.local_models()

    def act_local_models(
        self, who: Principal, action: str, name: str = "", on: bool | None = None
    ) -> dict[str, Any]:
        """Check this computer again, make a pinned model the default for its role, download,
        remove or time one, or turn Claude Code on or off for the knowledge agent: the owner's
        call, never automatic."""
        who.require("workspace.admin")
        if not who.is_human:
            raise PermissionDenied("Only a person changes this computer's models.")
        if action not in LOCAL_ACTIONS:
            raise ValidationFailed(
                f"An action is one of {', '.join(LOCAL_ACTIONS)}.", field="action"
            )
        if action in ("default", "download", "remove") and not name:
            raise ValidationFailed("Say which model.", field="name")
        return self.rt.brain.act_local_models(action, name, on)

    def set_policies(self, who: Principal, changes: dict[str, Any]) -> dict[str, Any]:
        """The owner changes how the Brain is governed: one undo point, one event."""
        who.require("brain.govern")
        if not isinstance(changes, dict) or not changes:
            raise ValidationFailed("Say which settings to change.")
        result = self.rt.brain.set_policies(changes)
        with self.rt.write() as tx:
            tx.emit(
                "brain.policy_changed",
                actor_id=who.actor_id,
                subject_type="brain_policy",
                subject_id="policy",
                data={
                    "changes": sorted(changes),
                    "checkpoint": (result.get("checkpoint") or {}).get("id"),
                },
            )
        return result

    # ---- what the Brain is for, and what it comes with

    def goals(self, who: Principal) -> dict[str, Any]:
        """The questions about what the Brain is for, and the owner's answers."""
        who.require("brain.read")
        return self.rt.brain.goals()

    def set_goals(self, who: Principal, answers: Any) -> dict[str, Any]:
        """The owner says what the Brain is for: their purpose (which every AI reads first)
        and every answer, as one undo point."""
        who.require("brain.govern")
        if not isinstance(answers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in answers.items()
        ):
            raise ValidationFailed("Answers map a question to its answer.", field="answers")
        result = self.rt.brain.set_goals(answers)
        if result.get("status") == "saved":
            with self.rt.write() as tx:
                tx.emit(
                    "brain.goals_set",
                    actor_id=who.actor_id,
                    subject_type="brain",
                    subject_id="goals",
                    data={
                        "answered": sorted(k for k, v in answers.items() if v.strip()),
                        "checkpoint": (result.get("checkpoint") or {}).get("id"),
                    },
                )
        return result

    def builtin_skills(self, who: Principal) -> dict[str, Any]:
        """The skills every Brain comes with, and whether this one has each."""
        who.require("brain.read")
        return self.rt.brain.builtin_skills()

    def add_builtin_skills(self, who: Principal, names: list[str] | None = None) -> dict[str, Any]:
        """Add the built-in skills the Brain is missing, as one undo point."""
        who.require("brain.govern")
        result = self.rt.brain.add_builtin_skills(names)
        if result.get("added"):
            with self.rt.write() as tx:
                tx.emit(
                    "brain.skills_added",
                    actor_id=who.actor_id,
                    subject_type="brain",
                    subject_id="skills",
                    data={"skills": result["added"]},
                )
        return result

    def requests(
        self,
        who: Principal,
        *,
        limit: int = 50,
        before: str | None = None,
        client: str | None = None,
    ) -> dict[str, Any]:
        """What each AI asked and what it got, newest first, with the app that asked."""
        who.require("brain.read")
        return self.rt.brain.requests(
            limit=max(1, min(int(limit), 200)),
            before=str(before or "").strip() or None,
            client=str(client or "").strip() or None,
        )

    def request(self, who: Principal, packet_id: str) -> dict[str, Any]:
        """One request in full, with the exact text it was handed and the startup context
        when that went with it."""
        who.require("brain.read")
        packet_id = str(packet_id or "").strip()
        if not packet_id:
            raise ValidationFailed("Name the request.", field="packet_id")
        found = dict(self.rt.brain.request(packet_id))
        found["eval"] = self.rt.brain.eval_case(packet_id)
        return found

    def weekly(self, who: Principal, *, weeks: int = 8) -> list[dict[str, Any]]:
        """Conversations the Brain served in each of the last weeks, oldest first."""
        who.require("brain.read")
        return self.rt.brain.weekly(max(1, min(int(weeks), 26)))

    # ---- measuring: the report card, replays and the owner's labeled requests

    def report(
        self, who: Principal, *, days: int = 7, claude_code: bool = False, quality: bool = True
    ) -> dict[str, Any]:
        """What context cost by day and line, brief sizes by request type and how well briefs
        carry what a task needs. `claude_code` reads Claude Code's transcripts on this
        computer for exact figures (token counts only)."""
        who.require("brain.read")
        return self.rt.brain.report(
            days=max(1, min(int(days), 90)), claude_code=claude_code, quality=quality
        )

    def replay(
        self,
        who: Principal,
        packet_ids: list[str],
        *,
        at: str | None = None,
        proposal: str | None = None,
    ) -> dict[str, Any]:
        """Logged briefs rebuilt against the Brain now, at a git ref or with a proposal
        applied in a copy, each with what would enter, leave or move. Changes nothing."""
        who.require("brain.read")
        ids = [str(p).strip() for p in packet_ids if str(p).strip()][:50]
        if not ids:
            raise ValidationFailed("Name at least one request to replay.", field="packets")
        return self.rt.brain.replay(
            ids, at=str(at or "").strip() or None, proposal=str(proposal or "").strip() or None
        )

    def label_request(
        self, who: Principal, packet_id: str, labels: dict[str, Any]
    ) -> dict[str, Any]:
        """The owner's labels for a logged request (needed, useful, noise, missing notes, or
        that it should get nothing): it joins the private eval set kept beside the Brain,
        never shared."""
        who.require("brain.govern")
        clean: dict[str, Any] = {
            key: [str(i).strip() for i in labels.get(key) or [] if str(i).strip()][:40]
            for key in ("needed", "useful", "noise", "missing")
        }
        nothing = bool(labels.get("nothing"))
        if nothing and (clean["needed"] or clean["useful"] or clean["missing"]):
            raise ValidationFailed(
                "A request that should get nothing has no needed or helpful notes.",
                field="labels",
            )
        if not nothing and not any(clean.values()):
            raise ValidationFailed("Mark at least one note.", field="labels")
        clean["nothing"] = nothing
        return self.rt.brain.eval_label(str(packet_id or "").strip(), clean)

    def eval_status(self, who: Principal) -> dict[str, Any]:
        who.require("brain.read")
        return self.rt.brain.eval_status()

    def search(self, who: Principal, query: str, limit: int = 10) -> list[BrainHit]:
        who.require("brain.read")
        return self.rt.brain.search(query, limit)

    def entry(self, who: Principal, entry_id: str) -> BrainEntry | None:
        who.require("brain.read")
        return self.rt.brain.entry(entry_id)

    def skill(self, who: Principal, name: str) -> BrainDocument | None:
        """A procedure the Brain holds, in full, with what it loads."""
        who.require("brain.read")
        return self.rt.brain.skill(name.lstrip("/"))

    def reference(self, who: Principal, path: str) -> BrainDocument | None:
        who.require("brain.read")
        return self.rt.brain.reference(path)

    def verify(self, who: Principal, entry_id: str, *, confidence: str | None = None) -> BrainEntry:
        """A person confirms an entry is still true today (a human release gate)."""
        who.require("brain.govern")
        entry = self.rt.brain.verify(entry_id, confidence=confidence)
        with self.rt.write() as tx:
            tx.emit(
                "brain.verified",
                actor_id=who.actor_id,
                subject_type="brain_entry",
                subject_id=entry_id,
                data={"confidence": entry.confidence},
            )
        return entry

    def mark(self, who: Principal, entry_id: str, state: str, *, reason: str) -> BrainEntry:
        """A person marks an entry stale or disputed; it stays, ranked lower and flagged."""
        who.require("brain.govern")
        if not str(reason or "").strip():
            raise ValidationFailed(
                "Say why, so the next person knows what to check.", field="reason"
            )
        entry = self.rt.brain.mark(entry_id, state, reason=reason)
        with self.rt.write() as tx:
            tx.emit(
                "brain.marked",
                actor_id=who.actor_id,
                subject_type="brain_entry",
                subject_id=entry_id,
                reason=reason,
                data={"state": state},
            )
        return entry

    def challenge(
        self,
        who: Principal,
        *,
        note_id: str,
        claim: str,
        evidence: str,
        source: str = "",
        run_id: str | None = None,
    ) -> BrainProposal:
        """Challenge an entry: a claim, its evidence and where it comes from. It waits for a
        person; accepted, the entry is disputed and keeps the challenge as its other view."""
        who.require("brain.propose")
        claim, evidence = " ".join(str(claim or "").split()), str(evidence or "").strip()
        source = " ".join(str(source or "").split())
        if not ENTRY_ID.match(str(note_id or "")):
            raise ValidationFailed("Name the entry to challenge.", field="note_id")
        if not claim or len(claim) > 600:
            raise ValidationFailed("Say the claim in at most 600 characters.", field="claim")
        if not evidence or len(evidence) > 2000:
            raise ValidationFailed(
                "Give the evidence in at most 2,000 characters.", field="evidence"
            )
        result = self.rt.brain.challenge(
            str(note_id),
            claim=claim,
            evidence=evidence,
            source=source[:300],
            proposer=proposer(who),
        )
        with self.rt.write() as tx:
            tx.emit(
                "brain.challenged",
                actor_id=who.actor_id,
                subject_type="brain_entry",
                subject_id=str(note_id),
                data={
                    "status": result.status,
                    "proposal": result.proposal_id,
                    **({"run_id": run_id} if run_id else {}),
                },
            )
        return result

    def proposals(self, who: Principal) -> list[dict[str, Any]]:
        who.require("brain.read")
        return self.rt.brain.proposals()

    def review(self, who: Principal) -> BrainReview:
        """Everything waiting, grouped by the work that proposed it, each proposal with what
        approving it would change, and each batch with a count of what needs a look."""
        who.require("brain.read")
        analysis = {str(row.get("id")): row for row in self.rt.brain.review()}
        rows = [
            dict(row, analysis=analysis.get(str(row.get("id")), {}))
            for row in self.rt.brain.proposals()
        ]
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            made_by = _task_of(row)
            session = str((row.get("meta") or {}).get("session") or row.get("session") or "")
            key = (
                f"task:{made_by}"
                if made_by
                else f"session:{session}"
                if session
                else f"proposer:{row.get('proposer') or ''}"
            )
            groups.setdefault(key, []).append(row)
        task_ids = [k[len("task:") :] for k in groups if k.startswith("task:")]
        tasks: dict[str, dict[str, Any]] = {}
        documents: dict[str, list[dict[str, str]]] = {}
        if task_ids:
            with self.rt.read() as tx:
                for found in tx.rows(
                    sa.select(schema.tasks).where(schema.tasks.c.id.in_(task_ids))
                ):
                    if who.sees_project(found["project_id"]):
                        tasks[found["id"]] = found
                pins, items = schema.task_pins, schema.context_items
                for pin in tx.rows(
                    sa.select(pins.c.task_id, items.c.id, items.c.title, items.c.filename)
                    .join(items, items.c.id == pins.c.ref_id)
                    .where(pins.c.task_id.in_(task_ids), pins.c.ref_type == "context_item")
                ):
                    documents.setdefault(pin["task_id"], []).append(
                        {"id": pin["id"], "title": pin["filename"] or pin["title"]}
                    )
        # Reconcile requests about a waiting proposal, and the rewrite each one suggested.
        waiting = {str(row.get("id")) for row in rows}
        reconciling: dict[str, list[dict[str, Any]]] = {}
        with self.rt.read() as tx:
            for found in tx.rows(
                sa.select(schema.tasks)
                .where(
                    schema.tasks.c.workspace_id == self.rt.workspace_id,
                    schema.tasks.c.template == RECONCILE,
                )
                .order_by(schema.tasks.c.created_at.desc())
                .limit(200)
            ):
                spec = (found["provenance"] or {}).get("reconcile") or {}
                if spec.get("proposal_id") in waiting and who.sees_project(found["project_id"]):
                    reconciling.setdefault(spec["proposal_id"], []).append(
                        {
                            "task_id": found["id"],
                            "status": found["status"],
                            "entry_id": spec.get("entry_id"),
                            "current": spec.get("current"),
                            "suggestion_ids": [
                                str(r.get("id")) for r in groups.get(f"task:{found['id']}", [])
                            ],
                        }
                    )
        for row in rows:
            row["reconciliations"] = reconciling.get(str(row.get("id")), [])
        batches = []
        for key, members in groups.items():
            members.sort(key=lambda r: str(r.get("created") or ""))
            task_id = key[len("task:") :] if key.startswith("task:") else None
            work = tasks.get(task_id or "")
            name = display_name(members[0].get("proposer"))
            topics: dict[str, int] = {}
            for row in members:
                route = str(row.get("route_key") or "")
                if route and not route.endswith("/None"):
                    topics[route] = topics.get(route, 0) + 1
            batches.append(
                ReviewBatch(
                    key=key,
                    title=work["title"] if work else f"Proposed by {name}",
                    proposer=name,
                    created=str(members[0].get("created") or ""),
                    proposal_ids=[str(r.get("id")) for r in members],
                    counts=_counts(members),
                    topics=[
                        {"route_key": k, "count": n}
                        for k, n in sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))
                    ],
                    task_id=task_id,
                    task_status=work["status"] if work else None,
                    documents=documents.get(task_id or "", []),
                    reconciles=(
                        (work["provenance"] or {}).get("reconcile")
                        if work and work["template"] == RECONCILE
                        else None
                    ),
                )
            )
        batches.sort(key=lambda b: b.created, reverse=True)
        return BrainReview(batches=batches, proposals=rows)

    def decide_many(
        self,
        who: Principal,
        decisions: list[dict[str, Any]],
        *,
        label: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Approve, reject and archive in one go: a human release gate, saved as one undo
        point. Approving can name the entries the proposal replaces (archived as it lands),
        move it to another topic, or retitle it."""
        who.require("brain.govern")
        if not decisions:
            raise ValidationFailed("Choose at least one proposal or entry to decide.")
        if len(decisions) > MAX_DECISIONS:
            raise ValidationFailed(f"Decide at most {MAX_DECISIONS} at a time.")
        clean = [_decision(d) for d in decisions]
        result = self.rt.brain.decide_many(
            clean, label=(label or "").strip()[:200] or None, source=source or None
        )
        point = result.get("checkpoint") or {}
        with self.rt.write() as tx:
            for asked, outcome in zip(clean, result.get("results") or [], strict=False):
                if not outcome.get("ok"):
                    continue
                on_entry = asked["action"] in ENTRY_ACTIONS
                tx.emit(
                    {
                        "approve": "brain.approved",
                        "reject": "brain.rejected",
                        "unschedule": "brain.unscheduled",
                        "archive": "brain.archived",
                        "edit": "brain.edited",
                        "restore": "brain.restored",
                        "unarchive": "brain.unarchived",
                        "update": "brain.updated",
                        "verify": "brain.verified",
                        "mark": "brain.marked",
                    }[asked["action"]],
                    actor_id=who.actor_id,
                    subject_type="brain_entry" if on_entry else "brain_proposal",
                    subject_id=asked.get("entry_id") or asked["proposal_id"],
                    reason=asked.get("reason") or None,
                    data={
                        "result": (outcome.get("data") or {}).get("status"),
                        "checkpoint": point.get("id"),
                    },
                )
        return result

    def decide(
        self, who: Principal, proposal_id: str, *, approve: bool, reason: str = ""
    ) -> dict[str, Any]:
        """Approve or reject one proposal: a batch of one, with its own undo point."""
        result = self.decide_many(
            who,
            [
                {
                    "action": "approve" if approve else "reject",
                    "proposal_id": proposal_id,
                    "reason": reason,
                }
            ],
        )
        (outcome,) = result["results"]
        if not outcome.get("ok"):
            message = str(outcome.get("message") or "")
            if "no pending proposal" in message.lower() or "not found" in message.lower():
                raise NotFound(message)
            raise Conflict(message)
        return dict(
            outcome.get("data") or {},
            message=outcome.get("message"),
            checkpoint=result.get("checkpoint"),
        )

    def checkpoints(self, who: Principal, *, limit: int = 50) -> list[dict[str, Any]]:
        """Undo points, newest first: what each batch of decisions changed, and whether it can
        still be undone."""
        who.require("brain.read")
        return self.rt.brain.checkpoints(max(1, min(int(limit), 200)))

    def undo(self, who: Principal, checkpoint_id: str) -> dict[str, Any]:
        """Take a batch of decisions back: a human release gate, like deciding it was."""
        who.require("brain.govern")
        result = self.rt.brain.undo(checkpoint_id)
        made = result.get("checkpoint") or {}
        with self.rt.write() as tx:
            tx.emit(
                "brain.undone",
                actor_id=who.actor_id,
                subject_type="brain_checkpoint",
                subject_id=checkpoint_id,
                data={"checkpoint": made.get("id"), "label": made.get("label")},
            )
        return result

    def add_file(
        self,
        who: Principal,
        *,
        filename: str,
        data: bytes,
        title: str = "",
        description: str = "",
        topic: str | None = None,
        project: str | None = None,
        status: str | None = None,
        library: dict[str, Any] | None = None,
        replaces: str | None = None,
        wait: bool = False,
        came_from: str | None = None,
    ) -> BrainProposal:
        """File a document or asset in the Brain, in a project when one is named (a file
        named like one already there is its new version). The Brain's capture policy decides
        whether it is filed at once, with an undo point, or waits for a person's review;
        `wait` makes it wait either way. `library` gives it its Library fields (its kind,
        source, when it was fetched, its refresh); `replaces` names the document this is a new
        version of; `came_from` says where it came from (its origin on its card)."""
        who.require("brain.propose")
        name = os.path.basename(str(filename or "").replace("\\", "/")).strip()
        if not name:
            raise ValidationFailed("Give the file a name.", field="filename")
        if not data:
            raise ValidationFailed("The file is empty.", field="file")
        if len(data) > MAX_FILE:
            raise ValidationFailed("A file for the Brain is at most 10 MB.", field="file")
        title = " ".join(str(title or "").split())
        copy = " ".join(str(status or "").split()).lower() or None
        if copy is not None and not FILE_STATUS.match(copy):
            raise ValidationFailed(
                "A file's status is a word or two, such as draft, sent or final.", field="status"
            )
        result = self.rt.brain.add_file(
            filename=name,
            data=data,
            title=title,
            description=str(description or "").strip(),
            topic=str(topic or "").strip() or None,
            proposer=proposer(who),
            project=str(project or "").strip() or None,
            status=copy,
            # A person in the workspace, or a model working through it.
            origin="app" if who.kind == "human" else "chat",
            wait=wait,
            library=library or None,
            replaces=str(replaces or "").strip() or None,
            came_from=came_from or None,
        )
        if result.status == "refused":
            raise ValidationFailed(result.message, field="file")
        if result.status == "applied":
            with self.rt.write() as tx:
                tx.emit(
                    "brain.filed",
                    actor_id=who.actor_id,
                    subject_type="brain_file",
                    subject_id=result.path or name,
                    data={
                        "title": title or name,
                        "filename": name,
                        "size": len(data),
                        "path": result.path,
                        "version": result.version,
                        "replaced": result.replaced,
                        "project": result.project,
                        "checkpoint": result.checkpoint_id,
                    },
                )
        if result.status == "pending":
            with self.rt.write() as tx:
                tx.emit(
                    "brain.proposed",
                    actor_id=who.actor_id,
                    subject_type="brain_proposal",
                    subject_id=result.proposal_id or name,
                    data={
                        "title": title or name,
                        "kind": "file",
                        "filename": name,
                        "size": len(data),
                        "status": result.status,
                    },
                )
        return result

    # ---- the Library: every item kept whole, by what it is for

    def library(self, who: Principal) -> list[dict[str, Any]]:
        """Every item kept whole that this person may see, as Library items: documents (a
        guide, a reference or an influence; one filed before the Library is a reference) and
        assets (images, fonts, sheets, kept byte for byte), each with where it came from, how
        often it is fetched again, its scope and the skills that load it. Brain > Files shows
        the same items grouped by where they came from."""
        who.require("brain.read")
        files = self.rt.brain.files()
        items = [
            {
                "path": item.path,
                "title": item.title,
                "kind": item.library or ("asset" if item.kind == "asset" else "reference"),
                "file_kind": item.kind,
                "mime": item.mime,
                "summary": item.description,
                "entry_id": item.entry_id,
                "source_url": item.source_url,
                "source_repo": item.source_repo,
                "source_paths": list(item.source_paths),
                "fetched_at": item.fetched_at,
                "refresh": item.refresh or "never",
                "updated": item.updated,
                "dated": item.dated,
                "version": item.version,
                "size": item.size,
                "original": item.original,
                "project": item.project,
                "project_title": item.project_title,
                "origin": item.origin,
                "origin_inferred": item.origin_inferred,
                "scope": item.scope,
                "used_by": {
                    "skills": [s.name for s in files.skills if item.path in s.loads],
                },
            }
            for item in [*files.references, *files.assets]
        ]
        items.sort(key=lambda i: (str(i["updated"] or ""), i["title"]), reverse=True)
        return items

    def library_item(self, who: Principal, path: str) -> dict[str, Any]:
        """One Library item, as the list gives it."""
        found = next((i for i in self.library(who) if i["path"] == path), None)
        if found is None:
            raise NotFound(f"Nothing at {path!r} in the Library.")
        return found

    def library_update(
        self,
        who: Principal,
        path: str,
        *,
        kind: str | None = None,
        refresh: str | None = None,
        origin: str | None = None,
    ) -> dict[str, Any]:
        """Say what kind of item it is, how often it is fetched again, or where it came from
        (for an item filed before origins were kept): a change to its card, one undo point."""
        fields: dict[str, Any] = {}
        if kind is not None:
            if kind not in LIBRARY_KINDS:
                raise ValidationFailed(
                    f"A Library item is one of {', '.join(LIBRARY_KINDS)}.", field="kind"
                )
            fields["library"] = kind
        if refresh is not None:
            if refresh not in LIBRARY_REFRESH:
                raise ValidationFailed(
                    f"Refresh is one of {', '.join(LIBRARY_REFRESH)}.", field="refresh"
                )
            fields["refresh"] = refresh
        if origin is not None:
            fields["origin"] = " ".join(str(origin).split())[:160]
        if not fields:
            raise ValidationFailed("Say what to change: its kind, its refresh or its origin.")
        item = self.library_item(who, path)
        if not item["entry_id"]:
            raise Conflict(
                "This document has no card to keep its Library details on; file it again from"
                " the Library to give it one."
            )
        result = self.decide_many(
            who,
            [{"action": "update", "entry_id": item["entry_id"], "fields": fields}],
            label=f"Library: {item['title']}",
        )
        (outcome,) = result["results"]
        if not outcome.get("ok"):
            raise ValidationFailed(str(outcome.get("message") or "Not changed."))
        return dict(self.library_item(who, path), checkpoint=result.get("checkpoint"))

    # ---- projects: the work the Brain follows across conversations

    def projects(self, who: Principal) -> list[BrainProject]:
        """Every project the Brain follows (its Focus items), active first."""
        who.require("brain.read")
        return self.rt.brain.projects()

    def project(self, who: Principal, project_id: str) -> dict[str, Any]:
        """One project in full: what it is for, where it stands, its progress, its files and
        the notes filed with it."""
        who.require("brain.read")
        found = self.rt.brain.project(project_id)
        if found is None:
            raise NotFound(f"The Brain follows no project {project_id}.")
        return found

    def project_update(
        self,
        who: Principal,
        project_id: str,
        *,
        summary: str,
        changes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Record progress on a project, the way an AI does from a chat: one line on what
        happened, and only the parts of where it stands that changed. Append-only."""
        who.require("brain.propose")
        line = " ".join(str(summary or "").split())
        if not 1 <= len(line) <= 300:
            raise ValidationFailed("Say in one line (up to 300 characters) what happened.")
        clean: dict[str, str] = {}
        for key, value in (changes or {}).items():
            if key not in PROJECT_STATE:
                raise ValidationFailed(
                    f"A project update changes {', '.join(PROJECT_STATE)}; not {key}.",
                    field="changes",
                )
            text = " ".join(str(value or "").split())
            if len(text) > 1000:
                raise ValidationFailed(f"Keep {key} under 1,000 characters.", field="changes")
            if text:
                clean[key] = text
        made = self.rt.brain.project_update(
            project_id, summary=line, changes=clean, evidence=f"recorded by {proposer(who)}"
        )
        with self.rt.write() as tx:
            tx.emit(
                "brain.project_updated",
                actor_id=who.actor_id,
                subject_type="brain_project",
                subject_id=project_id,
                data={"summary": line, "fields": sorted(clean)},
            )
        return made

    def create_project(
        self, who: Principal, *, name: str, summary: str, aliases: list[str] | None = None
    ) -> BrainProject:
        """Start a project in the Brain: its name, one line on what it is for, and the other
        names people will call it by, so a request that uses one brings its state and files."""
        who.require("brain.govern")
        name = " ".join(str(name or "").split())
        summary = " ".join(str(summary or "").split())
        if not 1 <= len(name) <= 80:
            raise ValidationFailed("A project's name is 1 to 80 characters.", field="name")
        if not 1 <= len(summary) <= 300:
            raise ValidationFailed(
                "Say in one line (up to 300 characters) what the project is for.",
                field="summary",
            )
        names = [" ".join(str(a or "").split()) for a in (aliases or [])]
        names = list(dict.fromkeys(a for a in names if a))
        if len(names) > MAX_ALIASES or any(len(a) > 80 for a in names):
            raise ValidationFailed(
                f"Up to {MAX_ALIASES} other names, each up to 80 characters.", field="aliases"
            )
        made = self.rt.brain.create_project(
            name=name, summary=summary, aliases=names, proposer=proposer(who)
        )
        with self.rt.write() as tx:
            tx.emit(
                "brain.project_started",
                actor_id=who.actor_id,
                subject_type="brain_project",
                subject_id=made.id,
                data={"title": made.title, "aliases": made.aliases},
            )
        return made

    def preview(
        self, who: Principal, request: str, *, project: str | None = None, tools: bool = True
    ) -> dict[str, Any]:
        """What an AI would be handed for this request, and why, recording nothing. Without
        `tools`, as a model that cannot call the Brain needs it (see BrainPort.preview)."""
        who.require("brain.read")
        text = str(request or "").strip()
        if not text:
            raise ValidationFailed("Type what you would ask your AI.", field="request")
        if len(text) > MAX_REQUEST:
            raise ValidationFailed(
                f"A request to preview is at most {MAX_REQUEST:,} characters.", field="request"
            )
        return self.rt.brain.preview(text, project=str(project or "").strip() or None, tools=tools)

    def propose(
        self,
        who: Principal,
        *,
        title: str,
        statement: str,
        kind: str = "fact",
        scope: str | None = None,
        evidence: str = "",
        sources: list[str] | None = None,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        replaces: list[str] | None = None,
        contradicts: list[str] | None = None,
        topic: str | None = None,
        revises: str | None = None,
        summary: str | None = None,
        origin: str | None = None,
        goal: str | None = None,
        project: str | None = None,
        must_hold: dict[str, Any] | None = None,
        as_of: str | None = None,
        valid_until: str | None = None,
    ) -> BrainProposal:
        """Submit distilled long-term context. It becomes durable only when approved.

        `must_hold` ({applies_to, triggers, must_text}) proposes a rule as a must-hold: one
        that goes into every brief whenever its domain comes up. Only a person can make one
        critical.

        Made during a run, the proposal names the run and its task among its sources, so the
        work that produced it (a distillation request, say) can show what came of it. It can
        name the entries it replaces (archived when it is approved), the ones it contradicts
        without replacing (for the reviewer to settle), and the topic it belongs in. With
        `revises`, it is a new text for one existing entry instead of a new entry (with
        `replaces` as well, a merge: the entry now says what they said, and they retire). Its
        `summary` is the one line a list shows; without one, the Brain uses the statement's
        first sentence. `origin` says where it came from (`doc:<item>@r<version>` for a
        selection in a doc, say); without one it is read from the run or the first source.
        `goal` names the owner's goal it serves; `project` the active project it belongs to,
        by id or name (it is then kept with that project). `as_of` is the day a changing value
        was true (a total, a count, a version), `valid_until` the last day it holds."""
        who.require("brain.propose")
        title, statement = " ".join(str(title or "").split()), str(statement or "").strip()
        if not title or not statement:
            raise ValidationFailed("A Brain proposal needs a title and a statement.")
        summary = " ".join(str(summary or "").split()) or None
        if summary and len(summary) > SUMMARY_LIMIT:
            raise ValidationFailed(
                f"A summary is one line of at most {SUMMARY_LIMIT} characters.", field="summary"
            )
        if kind not in KINDS:
            raise ValidationFailed(f"Kind is one of {', '.join(KINDS)}.", field="kind")
        replaces = _ids(replaces, "replaces")
        contradicts = _ids(contradicts, "contradicts")
        if set(replaces) & set(contradicts):
            raise ValidationFailed(
                "An entry is either replaced or contradicted, not both.", field="contradicts"
            )
        topic = _topic(topic)
        if revises is not None:
            revises = str(revises).strip()
            if not ENTRY_ID.match(revises):
                raise ValidationFailed("revises names one entry id.", field="revises")
            if contradicts:
                raise ValidationFailed(
                    "A change to an entry cannot also contradict others.", field="revises"
                )
            if revises in replaces:
                raise ValidationFailed("An entry cannot replace itself.", field="replaces")
            topic = None  # a change stays where its entry lives (with replaces: a merge)
        if not str(evidence or "").strip() and not sources:
            raise ValidationFailed(
                "Say where this comes from: quote the evidence or name the source items.",
                field="evidence",
            )
        sources = [str(s) for s in sources or []]
        task_id = project_id = None
        if run_id:
            with self.rt.read() as tx:
                run = tx.one(schema.task_runs, run_id, "run")
                if run["actor_id"] != who.actor_id:
                    raise PermissionDenied("That run belongs to someone else.", run_id=run_id)
                task = tx.one(schema.tasks, run["task_id"], "task")
            task_id, project_id = task["id"], task["project_id"]
            sources += [s for s in (f"task:{task_id}", f"run:{run_id}") if s not in sources]
        origin = _origin(origin, run_id, sources, who)
        extra: dict[str, Any] = {}
        goal = " ".join(str(goal or "").split())[:120]
        if goal:
            extra["goal"] = goal
        if str(project or "").strip():
            wanted = " ".join(str(project).split()).lower()
            found = next(
                (
                    p
                    for p in self.rt.brain.projects()
                    if wanted in (p.id.lower(), p.title.lower(), *(a.lower() for a in p.aliases))
                ),
                None,
            )
            if found is None:
                raise ValidationFailed(
                    f"The Brain follows no project {project!r}: name one of its projects by id.",
                    field="project",
                )
            extra["project_id"] = found.id
        if must_hold:
            if not isinstance(must_hold, dict):
                raise ValidationFailed(
                    "must_hold is {applies_to, triggers, must_text}.", field="must_hold"
                )
            limits = {"applies_to": 600, "triggers": 1200, "must_text": 400}
            held = {
                key: " ".join(str(must_hold.get(key) or "").split())
                for key in limits
                if str(must_hold.get(key) or "").strip()
            }
            for key, limit in limits.items():
                if len(held.get(key, "")) > limit:
                    raise ValidationFailed(
                        f"must_hold.{key} is at most {limit} characters.", field="must_hold"
                    )
            extra["must_hold"] = held
        for name, value in (("as_of", as_of), ("valid_until", valid_until)):
            text = str(value or "").strip()
            if not text:
                continue
            if not DAY.match(text):
                raise ValidationFailed(f"{name} is a date, YYYY-MM-DD.", field=name)
            extra[name] = text
        request = {
            "title": title,
            "statement": statement,
            "kind": kind,
            "scope": scope,
            "evidence": evidence,
            "sources": sources,
            "replaces": replaces,
            "contradicts": contradicts,
            "topic": topic,
            "revises": revises,
            "summary": summary,
            **extra,
        }
        with self.rt.read() as tx:
            prior = recall(tx, who, idempotency_key, "brain.propose", request)
        if prior:
            return BrainProposal(
                status="duplicate", message="Already proposed with this key.", proposal_id=prior
            )
        result = self.rt.brain.propose(
            title=title,
            statement=statement,
            kind=kind,
            scope=scope,
            evidence=evidence,
            sources=sources,
            proposer=proposer(who),
            replaces=replaces,
            contradicts=contradicts,
            topic=topic,
            revises=revises,
            summary=summary,
            origin=origin,
            **({"extra": extra} if extra else {}),
        )
        data: dict[str, Any] = {
            "title": title,
            "kind": kind,
            "status": result.status,
            "sources": sources,
            "scope": scope,
        }
        if task_id:
            data.update(task_id=task_id, run_id=run_id)
        if revises:
            data["revises"] = revises
        data.update(extra)
        with self.rt.write() as tx:
            tx.emit(
                "brain.proposed",
                actor_id=who.actor_id,
                subject_type="brain_proposal",
                subject_id=result.proposal_id or result.entry_id or title,
                project_id=project_id,
                data=data,
            )
            remember(
                tx,
                who,
                idempotency_key,
                "brain.propose",
                request,
                "brain_proposal",
                result.proposal_id or result.entry_id or title,
            )
        return result
