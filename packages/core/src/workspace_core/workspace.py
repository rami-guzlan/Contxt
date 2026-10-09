"""The facade every adapter uses: the REST API, the MCP endpoint, the CLI and the worker.

ws = Workspace.open("data", brain=brain_adapter)
owner = ws.owner()
note = ws.notes.create(owner, title="Campaign ideas")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import Clock, SystemClock
from workspace_core.db import migrate, schema
from workspace_core.db.engine import Database, sqlite_url
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import WorkspaceInfo
from workspace_core.domain.schedule import zone
from workspace_core.ids import new_id
from workspace_core.ports import BrainHit, BrainPort, BrainProject, NoBrain, TextExtractor
from workspace_core.storage.objects import ObjectStore

from .clock import iso
from .services.actors import Actors
from .services.agent import KnowledgeAgent
from .services.agents import Agents
from .services.approvals import Approvals
from .services.artifacts import Artifacts, Destination
from .services.brain import Brain
from .services.bus import Bus
from .services.captures import Captures
from .services.catchup import CatchUp
from .services.context import Context
from .services.distill import Distillation
from .services.events import Events
from .services.legacy import Legacy
from .services.movein import MovingIn
from .services.notes import Note, Notes
from .services.onboarding import Onboarding
from .services.projects import Projects
from .services.runtime import Runtime
from .services.skills import Skills
from .services.tasks import Tasks


@dataclass
class SearchResults:
    brain: list[BrainHit] = field(default_factory=list)
    projects: list[BrainProject] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)


class Workspace:
    def __init__(self, rt: Runtime, data_dir: str, owner_id: str, system_id: str) -> None:
        self.rt = rt
        self.data_dir = data_dir
        self.owner_id = owner_id
        self.system_id = system_id
        self.actors = Actors(rt)
        self.projects = Projects(rt)  # the task bus's boundary; people see the Brain's
        self.tasks = Tasks(rt)
        self.bus = Bus(rt, system_id)
        self.context = Context(rt)
        self.artifacts = Artifacts(rt)
        self.approvals = Approvals(rt)
        self.events = Events(rt)
        self.brain = Brain(rt)
        self.distill = Distillation(rt, self.tasks)
        self.notes = Notes(rt)
        self.captures = Captures(rt, self.tasks, self.distill)
        self.skills = Skills(rt, self.tasks, self.distill, self.brain, self.artifacts)
        self.onboarding = Onboarding(rt)
        self.legacy = Legacy(rt)
        self.catch_up = CatchUp(rt, self.brain, self.legacy)
        self.move_in = MovingIn(rt)
        self.agent = KnowledgeAgent(rt, self.brain)
        self.agents = Agents(rt, self.brain, self.skills, self.notes)

    # ---------------------------------------------------------------- lifecycle

    @classmethod
    def open(
        cls,
        data_dir: str,
        *,
        database_url: str | None = None,
        clock: Clock | None = None,
        brain: BrainPort | None = None,
        extractor: TextExtractor | None = None,
        name: str = "My workspace",
        timezone: str = "UTC",
        lease_seconds: int = 900,
    ) -> Workspace:
        """Open (and on first use create) a workspace; migrations run automatically."""
        data_dir = os.path.abspath(data_dir)
        os.makedirs(data_dir, exist_ok=True)
        db = Database(database_url or sqlite_url(os.path.join(data_dir, "workspace.sqlite")))
        migrate.upgrade(db, backup_dir=os.path.join(data_dir, "backups"))
        rt = Runtime(
            db=db,
            clock=clock or SystemClock(),
            objects=ObjectStore(os.path.join(data_dir, "objects")),
            brain=brain or NoBrain(),
            extractor=extractor,
            lease_seconds=lease_seconds,
        )
        workspace_id, owner_id, system_id = _bootstrap(rt, name, timezone)
        rt.workspace_id = workspace_id
        return cls(rt, data_dir, owner_id, system_id)

    def close(self) -> None:
        self.rt.db.close()

    def info(self) -> WorkspaceInfo:
        with self.rt.read() as tx:
            return WorkspaceInfo.from_row(
                tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            )

    def owner(self) -> Principal:
        return self.actors.principal(self.owner_id)

    def system(self) -> Principal:
        return self.actors.principal(self.system_id)

    def add_destination(self, destination: Destination) -> None:
        self.artifacts.destinations[destination.name] = destination

    def update_settings(
        self,
        who: Principal,
        *,
        name: str | None = None,
        timezone: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> WorkspaceInfo:
        who.require("workspace.admin")
        with self.rt.write() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            changes: dict[str, Any] = {}
            if name:
                changes["name"] = name.strip()
            if timezone:
                zone(timezone)
                changes["timezone"] = timezone
            if settings:
                changes["settings"] = {**row["settings"], **settings}
            row = tx.update(schema.workspaces, row, changes)
            tx.emit(
                "workspace.updated",
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=row["id"],
                data={"fields": sorted(changes)},
            )
        return WorkspaceInfo.from_row(row)

    # ---------------------------------------------------------------- cross-cutting reads

    def search(self, who: Principal, query: str, limit: int = 10) -> SearchResults:
        """Global search: the Brain's entries, the projects it follows, the caller's notes."""
        terms = [t for t in str(query or "").lower().split() if len(t) > 1]
        results = SearchResults()
        if not terms:
            return results
        if who.can("brain.read"):
            results.brain = self.brain.search(who, query, limit)
            results.projects = [
                p
                for p in self.brain.projects(who)
                if all(term in " ".join([p.title, p.summary, *p.aliases]).lower() for term in terms)
            ][:limit]
        if who.can("context.read"):
            results.notes = self.notes.search(who, query, limit=limit)
        return results

    def counts(self, who: Principal) -> dict[str, Any]:
        """The numbers the navigation and the status show: what waits for the person in
        Review, and the AI work the app started, by status."""
        tasks = schema.tasks
        with self.rt.read() as tx:
            by_status = {
                r["status"]: r["n"]
                for r in tx.rows(
                    sa.select(tasks.c.status, sa.func.count().label("n"))
                    .where(tasks.c.archived_at.is_(None))
                    .group_by(tasks.c.status)
                )
            }
        waiting = len(self.rt.brain.proposals()) if who.can("brain.read") else 0
        return {"brain_proposals": waiting, "ai_work": by_status}


def _bootstrap(rt: Runtime, name: str, timezone: str) -> tuple[str, str, str]:
    """The workspace row and its two built-in actors: the owner and the system."""
    zone(timezone)
    with rt.db.write() as conn:
        row = conn.execute(sa.select(schema.workspaces)).mappings().first()
        if row is not None:
            settings = row["settings"]
            return row["id"], settings["owner_actor_id"], settings["system_actor_id"]
        now = rt.clock.now()
        stamp = iso(now)
        workspace_id = new_id("ws", now)
        owner_id, system_id = new_id("act", now), new_id("act", now)
        conn.execute(
            schema.workspaces.insert().values(
                id=workspace_id,
                name=name,
                timezone=timezone,
                settings={"owner_actor_id": owner_id, "system_actor_id": system_id},
                created_at=stamp,
                updated_at=stamp,
                version=1,
            )
        )
        for actor_id, kind, label in (
            (owner_id, "human", "Owner"),
            (system_id, "system", "Workspace"),
        ):
            conn.execute(
                schema.actors.insert().values(
                    id=actor_id,
                    workspace_id=workspace_id,
                    kind=kind,
                    name=label,
                    created_at=stamp,
                    updated_at=stamp,
                    version=1,
                )
            )
        conn.execute(
            schema.events.insert().values(
                id=new_id("evt", now),
                workspace_id=workspace_id,
                at=stamp,
                actor_id=owner_id,
                type="workspace.created",
                subject_type="workspace",
                subject_id=workspace_id,
                data={"name": name, "timezone": timezone},
                noise=False,
            )
        )
    return workspace_id, owner_id, system_id
