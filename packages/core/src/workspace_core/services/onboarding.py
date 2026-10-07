"""First-time setup: what a new Brain still needs, worked out from what it holds.

Each step is done when its thing exists (the owner's own name, a connected AI, something of
the person's in the Brain, a project the Brain follows, a file in it), so the checklist never
disagrees with the data and needs no upkeep. Only what cannot be read from the data is
stored, in the workspace's settings: when the person finished or put the setup aside, took
the guided tour, or said a step is done as it stands.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import ValidationFailed

from .runtime import Runtime

STEPS = ("you", "ai", "brain", "project", "file")
MARKS = ("completed", "dismissed", "tour_seen")  # moments kept with the workspace
DEFAULT_OWNER = "Owner"  # the owner's name until the person gives theirs


class Onboarding:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def status(self, who: Principal, *, local_model: bool = False) -> dict[str, Any]:
        """The setup checklist, in order, with what each step found; `local_model` says a
        CLI on this computer can already run tasks (the server checks for it)."""
        stored = self._stored()
        marked = set(stored.get("steps") or [])
        with self.rt.read() as tx:
            owner = tx.get(schema.actors, self._owner_id(tx))
            count = _counter(tx, self.rt.workspace_id)
            found = {
                "ai": count(
                    schema.actors,
                    schema.actors.c.kind == "model",
                    archived=False,
                    alive=schema.actors.c.disabled_at.is_(None),
                ),
            }
        brain = self._brain(who)
        found["project"], found["file"] = brain["projects"], brain["files"]
        name = (owner or {}).get("name") or DEFAULT_OWNER
        done = {
            "you": name != DEFAULT_OWNER,
            "ai": found["ai"] > 0 or local_model,
            "brain": brain["own_entries"] > 0 or brain["waiting"] > 0,
            "project": found["project"] > 0,
            "file": found["file"] > 0,
        }
        steps = [
            {
                "id": step,
                "done": done[step] or step in marked,
                "count": found.get(step),
            }
            for step in STEPS
        ]
        return {
            "steps": steps,
            "done": sum(1 for s in steps if s["done"]),
            "total": len(steps),
            "owner_name": name,
            "brain": brain,
            "local_model": local_model,
            **{f"{mark}_at": stored.get(f"{mark}_at") for mark in MARKS},
        }

    def mark(
        self,
        who: Principal,
        *,
        completed: bool | None = None,
        dismissed: bool | None = None,
        tour_seen: bool | None = None,
        step: str | None = None,
    ) -> dict[str, Any]:
        """Keep a moment of the setup: finished, put aside (False brings it back), the tour
        taken, or a step said to be done as it stands."""
        who.require("workspace.admin")
        if step is not None and step not in STEPS:
            raise ValidationFailed(f"A step is one of {', '.join(STEPS)}.", field="step")
        with self.rt.write() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            settings = dict(row["settings"] or {})
            stored = dict(settings.get("onboarding") or {})
            for mark, value in (
                ("completed", completed),
                ("dismissed", dismissed),
                ("tour_seen", tour_seen),
            ):
                if value is not None:
                    stored[f"{mark}_at"] = tx.now if value else None
            if step is not None:
                stored["steps"] = sorted({*stored.get("steps", []), step})
            settings["onboarding"] = stored
            tx.update(schema.workspaces, row, {"settings": settings})
            tx.emit(
                "workspace.onboarding",
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=row["id"],
                data={k: v for k, v in stored.items() if k != "steps"} | {"step": step},
                noise=True,
            )
        return stored

    # ---------------------------------------------------------------- internals

    def _stored(self) -> dict[str, Any]:
        with self.rt.read() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        return dict((row["settings"] or {}).get("onboarding") or {})

    def _owner_id(self, tx: Any) -> str:
        row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        return str((row["settings"] or {}).get("owner_actor_id") or "")

    def _brain(self, who: Principal) -> dict[str, Any]:
        """Whether the Brain is there, how much of it is the person's own (not the system
        notes every Brain starts with), how many proposals wait for them, and how many
        projects it follows and files they hold."""
        out = {"available": False, "own_entries": 0, "waiting": 0, "projects": 0, "files": 0}
        if not who.can("brain.read"):
            return out
        status = self.rt.brain.status()
        if not status.get("available"):
            return out
        # the catalog is what the Brain holds in memory: cheap to read on every page
        own = [e for e in self.rt.brain.catalog().entries if e.area not in ("system", "skills")]
        projects = self.rt.brain.projects()
        return {
            "available": True,
            "own_entries": len(own),
            "waiting": len(self.rt.brain.proposals()),
            "projects": len(projects),
            "files": sum(p.files for p in projects),  # filed in a project
        }


def _counter(tx: Any, workspace_id: str) -> Any:
    def count(table: sa.Table, *where: Any, archived: bool = True, alive: Any = None) -> int:
        query = sa.select(sa.func.count()).select_from(table)
        if "workspace_id" in table.c:
            query = query.where(table.c.workspace_id == workspace_id)
        if archived and "archived_at" in table.c:
            query = query.where(table.c.archived_at.is_(None))
        if alive is not None:
            query = query.where(alive)
        for condition in where:
            query = query.where(condition)
        return int(tx.scalar(query) or 0)

    return count
