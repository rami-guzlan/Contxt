import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from workspace_core.clock import FixedClock
from workspace_core.errors import Conflict, NotFound, ValidationFailed
from workspace_core.ports import (
    BrainArea,
    BrainCatalog,
    BrainContext,
    BrainDocument,
    BrainEntry,
    BrainEntrySummary,
    BrainFile,
    BrainFileContent,
    BrainFiles,
    BrainHit,
    BrainProject,
    BrainProposal,
    BrainSkill,
    BrainTopic,
)
from workspace_core.workspace import Workspace

# Set to a PostgreSQL server URL (postgresql+psycopg://user:pass@host:port/postgres) to run
# every core test against PostgreSQL instead of SQLite; each test gets a fresh database.
POSTGRES = os.environ.get("CONTXT_TEST_DATABASE_URL") or os.environ.get(
    "WORKSPACE_TEST_DATABASE_URL"  # the earlier name
)


@pytest.fixture
def database_url():
    if not POSTGRES:
        yield None
        return
    name = f"ws_test_{uuid.uuid4().hex[:12]}"
    admin = sa.create_engine(POSTGRES, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        yield sa.engine.make_url(POSTGRES).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()


class FakeBrain:
    """A Brain that answers from a dictionary and records proposals."""

    def __init__(self) -> None:
        self.proposed: list[dict] = []
        self.decided: dict[str, bool] = {}
        self.not_indexed: set[str] = set()
        self.extra_skills: list[BrainSkill] = []  # skills a test adds to weekly-posts
        self.skill_dir: str | None = None  # where weekly-posts' files are, when a test says
        self.uploaded: list[dict] = []
        self.started: list[BrainProject] = []
        self.updates: list[dict] = []  # progress recorded on projects
        self.previewed: list[tuple] = []
        self.briefed: list[str] = []  # what context() was asked for
        self.analysis: dict[str, dict] = {}  # extra review analysis, by proposal id
        self.batches: list[dict] = []
        self.points: list[dict] = []
        self.used: list[tuple[str, list[dict]]] = []  # entries counted for AI work, by run
        self.voice_hash = "h1"  # the version of voice-guide the Brain holds now
        self.dismissed: list[str] = []
        self.policy: dict = {"review_days": {}, "retention_days": 90}
        self.went_in: list[dict] = []  # what went in on its own, for recaps
        self.goal_answers: dict[str, str] = {}
        self.moved: list[tuple] = []  # what move_in was asked to read
        self.watch: dict = {
            "clashes": [],
            "twins": [],
            "flagged": [],
            "recheck": [],
            "usage": {},
            "days": 7,
        }
        self.events: list[dict] = []  # journal records activity() adds, newest first
        self.findings: list[dict] = []  # what the weekly cross-check finds
        self.baselines: dict[str, str] = {}  # entry id: why it is a baseline
        self.challenged: list[dict] = []  # challenges raised
        self.builtin: dict[str, bool] = {"knowledge-check": False, "wrap-up": True}
        self.gathered: dict[str, list[dict]] = {}  # the knowledge agent's candidates, by action
        self.prompt_cards: dict[str, dict] = {}  # prompts kept in the Library, by card id
        self.entries = {
            "voice-guide": BrainEntry(
                id="voice-guide",
                title="Voice guide",
                text="Write plainly. No hype.",
                scope="company",
                kind="rule",
                status="approved",
                revision="r1",
            ),
        }

    def status(self):
        return {"available": True, "name": "Fake brain", "principal": "person:owner"}

    def context(self, request, *, session_id=None):
        self.briefed.append(request)
        return BrainContext(
            available=True,
            text="# Brain context\nWrite plainly. No hype.",
            entry_ids=["voice-guide"],
            entries=[{"id": "voice-guide", "hash": self.voice_hash, "tokens": 6}],
        )

    def search(self, query, limit=10):
        if "voice" not in query.lower():
            return []
        return [
            BrainHit(
                id="voice-guide",
                title="Voice guide",
                summary="Write plainly.",
                scope="company",
                kind="rule",
                score=1.0,
            )
        ]

    def entry(self, entry_id):
        return self.entries.get(entry_id)

    def skill(self, name):
        if name != "weekly-posts":
            return None
        return BrainDocument(
            kind="skill", name=name, text="1. Read the calendar.\n2. Draft.", loads=["rules/voice"]
        )

    def reference(self, path):
        if path != "references/voice.md":
            return None
        return BrainDocument(kind="reference", name=path, text="# Voice\nWarm and plain.")

    def indexed(self, ids):
        # Every entry is searchable at once, except the ones a test holds back.
        return {i for i in ids if i not in self.not_indexed}

    def propose(self, **fields):
        self.proposed.append(fields)
        return BrainProposal(
            status="pending",
            message="Waiting for the owner's review.",
            proposal_id=f"proposal-{len(self.proposed)}",
        )

    def proposals(self):
        # Shaped like the real inbox rows: the text is the proposal's `body`.
        return [
            {
                "id": f"proposal-{i + 1}",
                "body": p.get("statement", ""),
                "target": {
                    "kind": p.get("kind"),
                    "title": p.get("title"),
                    **(p.get("extra") or {}),
                },
                **p,
            }
            for i, p in enumerate(self.proposed)
            if f"proposal-{i + 1}" not in self.decided
        ]

    def review(self):
        empty = {
            "replaces": [],
            "conflicts": [],
            "overlaps": [],
            "duplicates": [],
            "problems": [],
            "suggested": [],
            "new_topic": False,
            "change": "new",
        }
        return [dict(empty, id=p["id"], **self.analysis.get(p["id"], {})) for p in self.proposals()]

    def decide_many(self, decisions, *, label=None, source=None):
        waiting = {p["id"] for p in self.proposals()}
        results, done = [], []
        for item in decisions:
            action = item["action"]
            target = item.get("proposal_id") or item.get("entry_id")
            on_entry = action in (
                "archive",
                "edit",
                "restore",
                "unarchive",
                "update",
                "verify",
                "mark",
            )
            card = self.prompt_cards.get(target) if on_entry else None
            ok = (target in self.entries or card is not None) if on_entry else target in waiting
            if ok and not on_entry:
                self.decided[target] = action == "approve"
                waiting.discard(target)
            if card is not None:
                self._decide_prompt(card, action, item.get("fields") or {})
            status = {
                "approve": "approved",
                "reject": "rejected",
                "archive": "archived",
                "edit": "edited",
                "restore": "restored",
                "unarchive": "unarchived",
                "update": "updated",
                "verify": "verified",
                "mark": "marked",
            }[action]
            results.append(
                {
                    "id": target,
                    "action": action,
                    "ok": ok,
                    "message": f"{status} {target}" if ok else f"No pending {target}",
                    "data": {"status": status, "id": target} if ok else {},
                }
            )
            if ok:
                done.append({"action": status, "id": target})
        self.batches.append({"decisions": decisions, "label": label, "source": source})
        point = None
        if done:
            point = {
                "id": f"cp-{len(self.points) + 1}",
                "at": "2026-09-28T12:00:00Z",
                "label": label or "Decisions",
                "decisions": done,
                "source": source or {},
                "undone_by": None,
            }
            self.points.insert(0, point)
        return {"results": results, "checkpoint": point}

    def checkpoints(self, limit=50):
        return self.points[:limit]

    def brain_versions(self):
        return list(getattr(self, "made_versions", []))

    def save_version(self, *, cause="manual", note=""):
        made = getattr(self, "made_versions", [])
        version = {"name": f"v{len(made) + 1}", "cause": cause, "note": note}
        self.made_versions = made + [version]
        return {"status": "made", "version": version}

    def version_diff(self, a, b):
        return {"from": a, "to": b, "added": [], "changed": [], "removed": [], "cells": []}

    def restore_version(self, version, *, ids=None):
        return self.save_version(cause="restore", note=f"from {version}")

    def correct(self, packet_id, kind, *, item="", note=""):
        self.corrected = getattr(self, "corrected", []) + [(packet_id, kind, item, note)]
        return {"outcome": "recorded", "kind": kind}

    def undo(self, checkpoint_id, *, together=False):
        from workspace_core.errors import Conflict, NotFound

        point = next((p for p in self.points if p["id"] == checkpoint_id), None)
        if point is None:
            raise NotFound(f"No undo point {checkpoint_id}.")
        if point["undone_by"]:
            raise Conflict("Already undone.")
        for decision in point["decisions"]:
            self.decided.pop(decision["id"], None)
        made = {
            "id": f"cp-{len(self.points) + 1}",
            "label": f"Undo: {point['label']}",
            "decisions": [],
            "undone_by": None,
        }
        point["undone_by"] = made["id"]
        self.points.insert(0, made)
        return {"undone": checkpoint_id, "checkpoint": made}

    def catalog(self):
        return BrainCatalog(
            areas=[
                BrainArea(
                    key="brand",
                    label="Brand",
                    description="How we sound and look",
                    topics=[BrainTopic(key="brand/voice", label="Voice", entries=1)],
                )
            ],
            entries=[
                BrainEntrySummary(
                    id="voice-guide",
                    title="Voice guide",
                    summary="Write plainly.",
                    area="brand",
                    topic="brand/voice",
                    kind="rule",
                    scope="company",
                    verified="2026-09-01",
                    standing=True,
                )
            ],
        )

    def files(self):
        return BrainFiles(
            references=[
                BrainFile(
                    path="references/voice.md",
                    kind="reference",
                    title="Voice",
                    size=24,
                    mime="text/markdown",
                )
            ],
            skills=[
                BrainSkill(
                    name="weekly-posts",
                    category="social",
                    description="Draft posts",
                    triggers=["draft this week's posts"],
                    artifacts=["post"],
                ),
                *self.extra_skills,
            ],
        )

    def propose_skill(
        self,
        *,
        proposer,
        sources,
        body,
        target=None,
        name=None,
        category=None,
        description=None,
        when_to_use=None,
        triggers=None,
        artifacts=None,
        loads=None,
        reason="",
        evidence="",
        files=None,
        depends_on=None,
    ):
        known = {"weekly-posts", *(s.name for s in self.extra_skills)}
        if target and target not in known:
            return BrainProposal(status="refused", message=f"No skill {target!r} to change.")
        waiting = next(
            (
                p
                for p in self.proposals()
                if str(p.get("kind", "")).startswith("skill.")
                and p["target"]["name"] == (target or name)
            ),
            None,
        )
        if waiting:
            return BrainProposal(
                status="duplicate",
                message=f"A proposal for skill {target or name} is already waiting.",
                proposal_id=waiting["id"],
            )
        task = next((s[len("task:") :] for s in sources if s.startswith("task:")), None)
        self.proposed.append(
            {
                "kind": "skill.update" if target else "skill.create",
                "target": {
                    "name": target or name,
                    "category": category,
                    "description": description,
                    "triggers": triggers,
                    "artifacts": artifacts,
                    "loads": loads,
                    "depends_on": depends_on,
                    "files": files,
                },
                "title": f"/{target or name}",
                "statement": body,
                "proposer": proposer,
                "sources": sources,
                "task_id": task,
                "reason": reason,
                "evidence": evidence,
            }
        )
        return BrainProposal(
            status="pending",
            message="Waiting for the owner's review.",
            proposal_id=f"proposal-{len(self.proposed)}",
        )

    def skill_versions(self, name, *, with_text=False):
        if name != "weekly-posts":
            return None
        row = {
            "ref": "current",
            "at": "2026-09-01T10:00:00Z",
            "current": True,
            "message": "",
            "hash": "h1",
            "chars": 31,
            "text_changed": True,
        }
        if with_text:
            row["body"] = "1. Read the calendar.\n2. Draft."
        return [row]

    def skill_folder(self, name):
        return self.skill_dir if name == "weekly-posts" else None

    def skill_freshness(self, name):
        if name != "weekly-posts":
            return None
        return {
            "last_edited": "2026-09-01T10:00:00Z",
            "changed": list(getattr(self, "changed_loads", [])),
        }

    def embed(self, texts):
        vectors = getattr(self, "vectors", None)
        return vectors(texts) if vectors else None

    def skill_source(self, name):
        return "1. Read the calendar.\n2. Draft." if name == "weekly-posts" else None

    def file_content(self, path, *, original=False):
        if path != "references/voice.md" or original:
            return None
        return BrainFileContent(
            filename="voice.md", mime="text/markdown", data=b"# Voice\nWarm and plain."
        )

    def attention(self):
        return dict(self.watch)

    def history(self, entry_id):
        if entry_id not in self.entries:
            return []
        return [{"at": "2026-09-01T10:00:00Z", "action": "approved", "by": "person:owner"}]

    # What the fake does with a file: "wait" for review, or "apply" (filed at once with an
    # undo point), as the real Brain's capture policy would say.
    file_policy = "wait"

    def add_file(
        self,
        *,
        filename,
        data,
        title,
        description,
        topic,
        proposer,
        project=None,
        status=None,
        origin="app",
        wait=False,
        library=None,
        replaces=None,
        came_from=None,
    ):
        self.came_from = [*getattr(self, "came_from", []), came_from]
        self.uploaded.append(
            {
                "filename": filename,
                "data": data,
                "title": title,
                "description": description,
                "topic": topic,
                "proposer": proposer,
                "project": project,
                "status": status,
                "origin": origin,
                "wait": wait,
                "library": library,
                "replaces": replaces,
            }
        )
        prior = next((c for c in self.prompt_cards.values() if c["path"] == replaces), None)
        if (library or {}).get("library") == "prompt" or prior is not None:
            return self._keep_prompt(filename, data, title, project, library or {}, prior)
        if self.file_policy == "apply" and not wait:
            return BrainProposal(
                status="applied",
                message="Filed it. Your AI can use it now.",
                proposal_id=f"file-{len(self.uploaded)}",
                entry_id="card-1",
                path=f"references/{filename}.md",
                version=1,
                sections=2,
                project=project,
                checkpoint_id="cp-1",
            )
        return BrainProposal(
            status="pending",
            message="Waiting for the owner's review.",
            proposal_id=f"file-{len(self.uploaded)}",
        )

    # ---- prompts kept in the Library: a card with the words, in the owner's own scope

    def prompts(self, *, archived=False):
        return [
            {k: v for k, v in c.items() if k != "versions"}
            for c in reversed(self.prompt_cards.values())
            if c["archived"] == archived
        ]

    def prompt(self, prompt_id):
        found = self.prompt_cards.get(prompt_id)
        return None if found is None else dict(found, versions=list(found["versions"]))

    def _keep_prompt(self, filename, data, title, project, library, prior):
        words = data.decode("utf-8")
        if prior is not None and prior["body"] == words:
            return BrainProposal(
                status="duplicate", message="Nothing new.", path=prior["path"], entry_id=prior["id"]
            )
        if prior is None:
            card_id = f"prompt-{len(self.prompt_cards) + 1}"
            prior = self.prompt_cards[card_id] = {
                "id": card_id,
                "path": f"references/prompts/{filename}",
                "title": title,
                "body": words,
                "tags": list(library.get("tags") or []),
                "picks": {
                    "skills": list(library.get("prompt_skills") or []),
                    "agent": library.get("prompt_agent") or None,
                    "docs": list(library.get("prompt_docs") or []),
                    "library": list(library.get("prompt_reads") or []),
                    "project": project,
                },
                "project": project,
                "project_title": None,
                "version": 1,
                "added": "2026-10-09",
                "updated": "2026-10-09T12:00:00Z",
                "origin": self.came_from[-1],
                "scope": "person:owner",
                "archived": False,
                "attachments": [],
                "versions": [],
            }
        else:
            prior.update(body=words, version=prior["version"] + 1)
        prior["versions"].insert(
            0, {"ref": f"v{prior['version']}", "at": "2026-10-09T12:00:00Z", "body": words}
        )
        return BrainProposal(
            status="applied",
            message="Kept it.",
            proposal_id=f"file-{len(self.uploaded)}",
            entry_id=prior["id"],
            path=prior["path"],
            version=prior["version"],
            project=project,
            checkpoint_id="cp-1",
        )

    @staticmethod
    def _decide_prompt(card, action, fields):
        if action in ("archive", "unarchive"):
            card["archived"] = action == "archive"
        lists = {"prompt_skills": "skills", "prompt_docs": "docs", "prompt_reads": "library"}
        for key, value in fields.items():
            words = [w.strip() for w in str(value).split(",") if w.strip()]
            if key == "tags":
                card["tags"] = words
            elif key in lists:
                card["picks"][lists[key]] = words
            elif key == "prompt_agent":
                card["picks"]["agent"] = value or None
            elif key == "title":
                card["title"] = value
            elif key == "project_id":
                card["project"] = card["picks"]["project"] = value or None

    def projects(self):
        return list(self.started)

    def create_project(self, *, name, summary, aliases, proposer, objective="", goals=None):
        slug = name.lower().replace(" ", "-")
        if any(p.id == slug for p in self.started):
            raise Conflict(f"A Focus {slug} already exists; record an update instead.")
        made = BrainProject(
            id=slug,
            title=name,
            summary=summary,
            aliases=list(aliases),
            topic=f"projects/{slug}",
        )
        self.started.append(made)
        return made

    def project(self, project_id):
        found = next((p for p in self.started if p.id == project_id), None)
        if found is None:
            return None
        return {
            "id": found.id,
            "title": found.title,
            "summary": found.summary,
            "aliases": list(found.aliases),
            "state": {"current": found.current, "next": found.next},
            "brief": "",
            "updates": [u for u in reversed(self.updates) if u["project"] == project_id],
            "files": [u for u in self.uploaded if u["project"] == project_id],
            "notes": [],
        }

    def project_update(self, project_id, *, summary, changes, evidence=""):
        index = next((i for i, p in enumerate(self.started) if p.id == project_id), None)
        if index is None:
            raise NotFound(f"No project {project_id}.")
        fields = {k: v for k, v in changes.items() if k in ("current", "next", "blockers")}
        self.started[index] = replace(self.started[index], **fields)
        made = {"project": project_id, "summary": summary, "changes": changes, "evidence": evidence}
        self.updates.append(made)
        return {"id": project_id, "seq": len(self.updates)}

    def preview(self, request, *, project=None, tools=True):
        self.previewed.append((request, project))
        return {
            "text": f"## Task\n\n{request}",
            "mode": "standard",
            "tokens": 12,
            "project": None,
            "procedure": None,
            "notes": [],
            "sections": [],
            "related": [],
        }

    def verify(self, entry_id, *, confidence=None):
        entry = self.entries[entry_id]
        entry = replace(
            entry,
            verified="2026-09-28",
            stale=False,
            stale_reason=None,
            confidence=confidence or entry.confidence,
        )
        self.entries[entry_id] = entry
        return entry

    # ---- the supply chain

    def record_use(self, ref, entries):
        self.used.append((ref, [dict(e) for e in entries]))

    def entry_details(self, entry_id):
        if entry_id not in self.entries:
            return None
        entry = self.entries[entry_id]
        return {
            "type": "note",
            "id": entry.id,
            "title": entry.title,
            "hash": self.voice_hash,
            "owner": "person:owner",
            "live": True,
            "uses": {"total": len(self.used)},
            "baseline": self.baselines.get(entry.id, ""),
        }

    def inventory(self):
        return [self.entry_details(i) for i in self.entries]

    def versions(self, entry_id, *, with_text=False):
        if entry_id not in self.entries:
            return None
        rows = [
            {
                "ref": "current",
                "at": "2026-09-28T12:00:00Z",
                "hash": self.voice_hash,
                "changes": [],
            },
            {"ref": "abc1234", "at": "2026-09-01T10:00:00Z", "hash": "h1", "changes": []},
        ]
        if with_text:
            for row in rows:
                row["body"] = self.entries[entry_id].text
        return rows

    def version(self, entry_id, ref):
        return next(
            (v for v in self.versions(entry_id, with_text=True) or [] if v["ref"] == ref), None
        )

    def activity(self, *, entry_id=None, since=None, until=None, actions=None, by=None, limit=200):
        return [
            *self.events,
            {"at": "2026-09-01T10:00:00Z", "action": "approved", "note": "voice-guide"},
        ]

    def use(self, entry_id, *, days=90):
        if entry_id not in self.entries:
            return None
        recent = [
            {"session_id": f"work:{ref}", "via": "work", "hash": e["hash"]}
            for ref, items in self.used
            for e in items
            if e["id"] == entry_id
        ]
        return {"id": entry_id, "daily": [], "recent": recent, "totals": {"total": len(recent)}}

    def gaps(self, *, days=30):
        return [
            g
            for g in [{"key": "packet:p1", "kind": "nothing", "request": "Capital?"}]
            if g["key"] not in self.dismissed
        ]

    def dismiss_gap(self, key):
        self.dismissed.append(key)

    def flow(self, *, days=7):
        return {"days": days, "came_in": len(self.proposed), "waiting": len(self.proposals())}

    def policies(self):
        return dict(self.policy)

    def cross_check(self):
        return list(self.findings)

    def challenge_targets(self, limit=3):
        return [{"id": e.id, "claim": e.text, "title": e.title} for e in self.entries.values()][
            :limit
        ]

    def challenge(self, note_id, *, claim, evidence, source, proposer):
        self.challenged.append(
            {"note_id": note_id, "claim": claim, "evidence": evidence, "source": source}
        )
        return BrainProposal(
            status="pending", message="Challenge proposed.", proposal_id=f"challenge-{note_id}"
        )

    def set_policies(self, changes):
        self.policy.update(changes)
        return {"status": "updated", "policy": dict(self.policy), "checkpoint": {"id": "cp-policy"}}

    def propose_many(self, items, *, proposer):
        return [self.propose(proposer=proposer, **item) for item in items]

    def recap(self, since):
        return {
            "since": since,
            "went_in": list(self.went_in),
            "went_in_total": len(self.went_in),
            "decided": {},
            "came_in": {
                "total": len(self.proposed),
                "by_source": {},
                "waiting": len(self.proposals()),
            },
            "projects": [],
            "gaps": 0,
        }

    def unsaved(self):
        return list(getattr(self, "unsaved_paths", []))

    def models(self):
        return {"matching": {"enabled": True, "present": False, "downloading": False}}

    def download_models(self):
        return {"matching": {"enabled": True, "present": False, "downloading": True}}

    def holds_text(self, fingerprints):
        return set(fingerprints) & set(getattr(self, "held_texts", set()))

    def skills_history(self, names):
        return {n: {"hashes": [], "last_edited": None, "changed": []} for n in names}

    def local_models(self):
        return {"enabled": True, "setup": "laptop", "roles": []}

    def act_local_models(self, action, name="", on=None):
        self.local_acts = [*getattr(self, "local_acts", []), (action, name, on)]
        return dict(self.local_models(), notice="")

    def made_from(self, path):
        return None

    def work_given(self, run_id):
        return [{"kind": "note", "id": "voice-guide", "title": "Voice guide", "tokens": 5}]

    def kernel(self, *, tools=True):
        return {"text": "# Startup\nWrite plainly.", "tokens": 6}

    def record_model_call(self, job, model, **figures):
        self.model_calls = [*getattr(self, "model_calls", []), (job, model, figures)]

    def report(self, *, days=7, claude_code=False, quality=True):
        return {"days": days, "spend": {"days": []}, "per_day_usd": 0.0, "text": "No use."}

    def replay(self, packet_ids, *, at=None, proposal=None):
        return {"against": "now", "replayed": len(packet_ids), "changed": 0, "rows": []}

    def eval_case(self, packet_id):
        return None

    def eval_label(self, packet_id, labels):
        return {"id": packet_id, "labeled": True, **labels}

    def eval_status(self):
        return {"cases": 0, "labeled": 0, "held_out": 0, "by_type": {}}

    def calibration_samples(self):
        return [{"label": "kernel", "text": "# Startup\nWrite plainly.", "estimated": 6}]

    def set_calibration(self, pairs, *, method):
        return {"factor": 1.0, "method": method, "samples": len(pairs)}

    def agent_outline(self, *, brief=False):
        return {
            "counts": {"notes": len(self.entries)},
            "text": "# The Brain as it is now\n\n"
            + "\n".join(f"- `{i}` {e.title}" for i, e in self.entries.items()),
        }

    def agent_gather(self, action, *, limit=10):
        found = list(self.gathered.get(action) or [])
        return {
            "action": action,
            "candidates": [{"ref": f"c{n}", **c} for n, c in enumerate(found[:limit], 1)],
            "found": len(found),
        }

    def agent_skill(self, name):
        return f"# /{name}\n\nJudge each candidate. Answer in JSON."

    def agent_skills(self):
        return [{"name": "tidy-repeats", "description": "Repeats.", "text": "...", "own": False}]

    # ---- Work: agents, kept in memory the way the Brain keeps them in files

    def agents(self, *, archived=False):
        found = getattr(self, "kept_agents", {})
        return [dict(a) for a in found.values() if archived or a["status"] != "archived"]

    def agent(self, name):
        found = getattr(self, "kept_agents", {}).get(name)
        if found is None:
            return None
        known = {"weekly-posts", *(s.name for s in self.extra_skills)}
        resolved = {
            "skills": [
                {"name": s, "missing": s not in known, "description": ""} for s in found["skills"]
            ],
            "library": [{"path": p, "missing": False, "title": p} for p in found["library"]],
            "context": [{"key": c, "missing": False} for c in found["context"]],
            "projects": [],
            "broken": [f"/{s}" for s in found["skills"] if s not in known],
        }
        prompt = f"# You are working as {name}\n\n{found['role']}\n\n{found['prompt']}\n"
        return {"agent": dict(found), "resolved": resolved, "prompt": prompt}

    def save_agent(self, name, fields, prompt, *, label=None):
        if not fields.get("role"):
            raise ValidationFailed("Not saved: say in a line what it does (role).")
        self.kept_agents = getattr(self, "kept_agents", {})
        agent = {
            "name": name,
            "role": fields["role"],
            "prompt": prompt,
            "status": "active",
            "output": fields.get("output") or "outputs",
            "output_shape": fields.get("output_shape") or "",
            "runner": fields.get("runner") or "claude",
            "review": True,
            "meetings_days": int(fields.get("meetings_days") or 0),
            "scope": "",
            "path": f"agents/{name}/AGENT.md",
        }
        for key in (
            "responsibilities",
            "goals",
            "projects",
            "skills",
            "library",
            "context",
            "boundaries",
        ):
            agent[key] = list(fields.get(key) or [])
        self.kept_agents[name] = agent
        return {
            "status": "saved",
            "name": name,
            "path": agent["path"],
            "checkpoint": {"id": f"cp-agent-{name}"},
        }

    def archive_agent(self, name):
        found = getattr(self, "kept_agents", {}).get(name)
        if found is None:
            raise NotFound(f"No agent named {name!r}.")
        found["status"] = "archived"
        return {"status": "saved", "name": name, "checkpoint": {"id": f"cp-archive-{name}"}}

    def agent_versions(self, name, *, with_text=False):
        found = getattr(self, "kept_agents", {}).get(name)
        return None if found is None else [{"ref": "current", "at": "2026-09-28T13:00:00Z"}]

    def work_skill(self, name):
        return {
            "agent-builder": "Write the agent's operating prompt.",
            "prompt-improver": "Improve the request.",
        }.get(name)

    def requests(self, *, limit=50, before=None, client=None):
        rows = list(getattr(self, "request_rows", []))
        return {"requests": rows[:limit], "brain_tokens": 100, "apps": []}

    def request(self, packet_id):
        from workspace_core.errors import NotFound

        raise NotFound(f"No request {packet_id}.")

    def weekly(self, weeks=8):
        return [{"start": "2026-09-22", "end": "2026-09-28", "conversations": 3, "packets": 5}]

    def goals(self):
        exists = bool(self.goal_answers.get("purpose"))
        return {
            "questions": [{"id": "purpose", "question": "What should this Brain help you do?"}],
            "answers": dict(self.goal_answers),
            "exists": exists,
            "id": "you-goals",
            "purpose": self.goal_answers.get("purpose", ""),
            "updated": None,
            "text": "\n\n".join(self.goal_answers.values()) if exists else "",
        }

    # The goal ladder: no goals, like a Brain that has none yet.
    def ladder(self, *, with_signals=False):
        from workspace_core.ports import NoBrain

        return NoBrain().ladder(with_signals=with_signals)

    def goal_cards(self):
        return []

    def goal(self, goal_id):
        from workspace_core.errors import NotFound

        raise NotFound(f"No goal {goal_id!r}.")

    def act_goal(self, action, goal_id="", fields=None):
        from workspace_core.errors import Conflict

        raise Conflict("The test Brain keeps no goals.")

    # State and tasks: none, like a Brain that has none yet.
    def state_act(self, action, fields=None):
        from workspace_core.ports import NoBrain

        return NoBrain().state_act(action, fields)

    def tasks(self, **filters):
        return []

    def task(self, task_id):
        from workspace_core.errors import NotFound

        raise NotFound(f"No task {task_id!r}.")

    def hand_off(self, **fields):
        from workspace_core.errors import Conflict

        raise Conflict("The test Brain keeps no tasks.")

    def get_state(self, *, sheet="", row="", query=""):
        return {"text": "No State sheets yet.", "sheets": []}

    def update_state(self, updates, *, evidence="", session_id=""):
        from workspace_core.errors import Conflict

        raise Conflict("The test Brain keeps no State.")

    def outputs_for(self, paths):
        return {}

    # The updating loop and the local agent: nothing recorded, no tools.
    def agent_tool(self, name, args):
        return None, [f"no tool {name!r}"]

    def agent_menu(self):
        return ""

    def changes_digest(self):
        return ""

    def record_agent_run(self, run_id, action, ending, record):
        self.agent_runs_kept = [
            *getattr(self, "agent_runs_kept", []),
            (run_id, action, ending, record),
        ]

    def record_episode(self, **fields):
        self.episodes = [*getattr(self, "episodes", []), fields]

    def loop_status(self):
        from workspace_core.ports import NoBrain

        return getattr(self, "loop", None) or NoBrain().loop_status()

    def correction(self, text, *, session_id="", packet_id=""):
        return {"suspects": [], "card": None}

    def close_correction(self, correction_id, status):
        self.closed = [*getattr(self, "closed", []), (correction_id, status)]

    def check_output(self, text, *, sent_back=""):
        found = [
            {"note": rule, "rule": rule, "found": phrase, "kind": "phrase"}
            for rule, phrase in getattr(self, "forbidden", {}).items()
            if phrase.lower() in str(text).lower()
        ]
        if found and sent_back:
            self.sent_back = [*getattr(self, "sent_back", []), sent_back]
        return found

    def agent_runs(self, limit=20):
        return [
            {"id": r, "action": a, "ending": e, "at": "2026-10-10T12:00:00Z", "record": rec}
            for r, a, e, rec in reversed(getattr(self, "agent_runs_kept", []))
        ][:limit]

    def blast_radius(self, proposal_id):
        return {"briefs": 0, "changed": 0, "rows": [], "seconds": 0.0}

    def link_output(self, path, *, project=None, row=None):
        return None

    def set_goals(self, answers):
        if not answers.get("purpose"):
            from workspace_core.errors import ValidationFailed

            raise ValidationFailed("Say what this Brain should help you do.", field="purpose")
        self.goal_answers = dict(answers)
        self.entries["you-goals"] = BrainEntry(
            id="you-goals",
            title="Your goals for this Brain",
            text="\n\n".join(answers.values()),
            scope="person:owner",
            kind="identity",
            status="approved",
            revision="r1",
        )
        return dict(self.goals(), status="saved", checkpoint={"id": "cp-goals"})

    def builtin_skills(self):
        rows = [{"name": n, "category": "brain", "installed": on} for n, on in self.builtin.items()]
        return {"skills": rows, "missing": [r["name"] for r in rows if not r["installed"]]}

    def add_builtin_skills(self, names=None):
        added = [n for n, on in self.builtin.items() if not on and (names is None or n in names)]
        for name in added:
            self.builtin[name] = True
        return {"added": added, "checkpoint": {"id": "cp-skills"} if added else None}

    def move_in(self, sources, *, name=""):
        """Each line of each source is one idea; "known:" lines are known, "clash:" ones
        disagree with voice-guide, "secret:" ones hold a password."""
        self.moved.append((sources, name))
        ideas = []
        for number, source in enumerate(sources, start=1):
            for line in source["text"].splitlines():
                text = line.strip()
                if not text:
                    continue
                status, _, rest = text.partition(":") if ":" in text else ("new", "", text)
                off = status == "off"  # an idea the sift left out
                project = status == "project"  # one that serves a goal and a project
                ideas.append(
                    {
                        "id": f"i{len(ideas) + 1}",
                        "source": f"s{number}",
                        "source_kind": source["kind"],
                        "text": rest.strip() or text,
                        "original": rest.strip() or text,
                        "kind": "rule" if status == "rule" else "fact",
                        "personal": status == "rule",
                        "topic": "brand/voice",
                        "status": {"known": "known", "clash": "disagree", "secret": "private"}.get(
                            status, "new"
                        ),
                        "match": {"id": "voice-guide", "title": "Voice guide"}
                        if status in ("known", "clash")
                        else None,
                        "private": "a password or key" if status == "secret" else None,
                        "secret": status == "secret",
                        "fits": not off,
                        "serves": {
                            "goal": "what your Brain is for" if project else None,
                            "project": {"id": "q4-webinars", "title": "Q4 webinars"}
                            if project
                            else None,
                            "about_you": status == "rule",
                        },
                        **({"left_out": "none of your goals or projects covers it"} if off else {}),
                    }
                )
        return {
            "sources": [
                {"id": f"s{i}", "kind": s["kind"], "label": s.get("label") or s["kind"]}
                for i, s in enumerate(sources, start=1)
            ],
            "ideas": ideas,
            "stages": {"ideas": len(ideas)},
            "examples": {},
        }

    def mark(self, entry_id, state, *, reason):
        entry = self.entries[entry_id]
        entry = (
            replace(entry, stale=True, stale_reason="marked stale")
            if state == "stale"
            else replace(entry, confidence="disputed")
        )
        self.entries[entry_id] = entry
        return entry


class FakeDestination:
    name = "fake-drive"
    label = "Fake drive"
    accepts = ("document", "social_post")

    def __init__(self) -> None:
        self.delivered: list[tuple[str, bytes]] = []

    def deliver(self, *, artifact, version, data):
        self.delivered.append((version.filename, data))
        return {"location": f"fake://{version.filename}"}


@pytest.fixture
def clock():
    # Monday 28 September 2026, 09:00 in New York.
    return FixedClock(datetime(2026, 9, 28, 13, 0, tzinfo=UTC))


@pytest.fixture
def brain():
    return FakeBrain()


@pytest.fixture
def ws(tmp_path, clock, brain, database_url):
    workspace = Workspace.open(
        str(tmp_path / "data"),
        database_url=database_url,
        clock=clock,
        brain=brain,
        name="Test workspace",
        timezone="America/New_York",
    )
    yield workspace
    workspace.close()


@pytest.fixture
def destination(ws):
    target = FakeDestination()
    ws.add_destination(target)
    return target


@pytest.fixture
def owner(ws):
    return ws.owner()


@pytest.fixture
def connect(ws, owner):
    def _connect(name="Claude Code", provider="claude-code", projects=None):
        connection = ws.actors.connect_model(owner, name=name, provider=provider, projects=projects)
        return ws.actors.authenticate(connection.token)

    return _connect


@pytest.fixture
def project(ws, owner):
    return ws.projects.create(owner, title="Content creation", summary="Weekly posts")


@pytest.fixture
def make_task(ws, owner, project):
    def _make(
        assignee,
        *,
        title="Draft next week's posts",
        schedule=None,
        ready=True,
        review_policy="required",
        **fields,
    ):
        task = ws.tasks.create(
            owner,
            project_id=project.id,
            title=title,
            purpose="Keep the weekly cadence",
            instructions="Draft three posts from the developed ideas.",
            assignee_id=assignee.actor_id if assignee else None,
            schedule=schedule or {"kind": "manual"},
            output_contract={"artifacts": [{"type": "social_post", "count": 3}]},
            review_policy=review_policy,
            **fields,
        )
        return ws.tasks.mark_ready(owner, task.id) if ready else task

    return _make
