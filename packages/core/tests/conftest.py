import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from workspace_core.clock import FixedClock
from workspace_core.errors import Conflict, NotFound
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
        self.extra_skills: list[BrainSkill] = []  # skills a test adds to weekly-posts
        self.skill_dir: str | None = None  # where weekly-posts' files are, when a test says
        self.uploaded: list[dict] = []
        self.started: list[BrainProject] = []
        self.updates: list[dict] = []  # progress recorded on projects
        self.previewed: list[tuple] = []
        self.requests: list[str] = []
        self.analysis: dict[str, dict] = {}  # extra review analysis, by proposal id
        self.batches: list[dict] = []
        self.points: list[dict] = []
        self.used: list[tuple[str, list[dict]]] = []  # entries counted for AI work, by run
        self.voice_hash = "h1"  # the version of voice-guide the Brain holds now
        self.dismissed: list[str] = []
        self.policy: dict = {"review_days": {}, "retention_days": 90}
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
        return {"available": True, "name": "Fake brain"}

    def context(self, request, *, session_id=None):
        self.requests.append(request)
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
            {"id": f"proposal-{i + 1}", "body": p.get("statement", ""), **p}
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
            ok = target in self.entries if on_entry else target in waiting
            if ok and not on_entry:
                self.decided[target] = action == "approve"
                waiting.discard(target)
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
                "label": label or "Decisions",
                "decisions": done,
                "undone_by": None,
            }
            self.points.insert(0, point)
        return {"results": results, "checkpoint": point}

    def checkpoints(self, limit=50):
        return self.points[:limit]

    def undo(self, checkpoint_id):
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

    def skill_source(self, name):
        return "1. Read the calendar.\n2. Draft." if name == "weekly-posts" else None

    def file_content(self, path, *, original=False):
        if path != "references/voice.md" or original:
            return None
        return BrainFileContent(
            filename="voice.md", mime="text/markdown", data=b"# Voice\nWarm and plain."
        )

    def attention(self):
        return {"clashes": [], "twins": [], "flagged": [], "recheck": [], "usage": {}, "days": 7}

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
    ):
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
            }
        )
        if self.file_policy == "apply":
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

    def projects(self):
        return list(self.started)

    def create_project(self, *, name, summary, aliases, proposer):
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

    def preview(self, request, *, project=None):
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
        return [{"at": "2026-09-01T10:00:00Z", "action": "approved", "note": "voice-guide"}]

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

    def set_policies(self, changes):
        self.policy.update(changes)
        return {"status": "updated", "policy": dict(self.policy), "checkpoint": {"id": "cp-policy"}}

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
