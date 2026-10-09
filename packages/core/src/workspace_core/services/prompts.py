"""Saved prompts: requests the owner wrote in Compose, kept with what they were picked with.

A saved prompt is the request as written, its title, and its picks (skills in order, an agent,
Workspace docs, documents to read whole, a project), with a version for each change of its
words. It is private to the app: a context item of its own kind ("prompt"), which nothing lists,
searches or hands a model, until the owner turns it into a skill. Each run from it counts as a
use, so the often-used ones can be suggested as skills.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed

from .context import record_revision
from .runtime import Runtime
from .skills import Skills

KIND = "prompt"
MAX_TITLE = 200
MAX_BODY = 8000
MAX_SKILLS = 6
MAX_DOCS = 5
MAX_LIBRARY = 5


def clean_picks(picks: dict[str, Any] | None) -> dict[str, Any]:
    """What a prompt is picked with, in the shape Compose sends: names and ids, not checked
    against the Brain here (a pick may go away later; Compose says so when it loads)."""
    picks = dict(picks or {})

    def names(key: str, limit: int) -> builtins.list[str]:
        value = picks.get(key) or []
        if not isinstance(value, list):
            raise ValidationFailed(f"{key} is a list.", field=key)
        found = list(dict.fromkeys(str(v).strip().lstrip("/") for v in value if str(v).strip()))
        if len(found) > limit:
            raise ValidationFailed(f"At most {limit} in {key}.", field=key)
        return [v[:300] for v in found]

    def one(key: str) -> str | None:
        value = str(picks.get(key) or "").strip()
        return value[:200] or None

    return {
        "skills": names("skills", MAX_SKILLS),
        "agent": one("agent"),
        "docs": names("docs", MAX_DOCS),
        "library": names("library", MAX_LIBRARY),
        "project": one("project"),
    }


def _title(value: Any) -> str:
    title = " ".join(str(value or "").split())[:MAX_TITLE]
    if not title:
        raise ValidationFailed("Name the prompt.", field="title")
    return title


def _body(value: Any) -> str:
    body = str(value or "").replace("\r\n", "\n").strip()
    if not body:
        raise ValidationFailed("Write the prompt first.", field="body")
    if len(body) > MAX_BODY:
        raise ValidationFailed(f"Keep a prompt under {MAX_BODY:,} characters.", field="body")
    return body


@dataclass(frozen=True)
class SavedPrompt:
    id: str
    title: str
    body: str
    picks: dict[str, Any]
    revision: int
    version: int
    created_at: str
    updated_at: str
    archived_at: str | None
    uses: int = 0
    last_used: str | None = None
    versions: builtins.list[dict[str, Any]] = field(default_factory=list)


class Prompts:
    def __init__(self, rt: Runtime, skills: Skills) -> None:
        self.rt = rt
        self.skills = skills

    # ---------------------------------------------------------------- reading

    def list(
        self, who: Principal, *, archived: bool = False, query: str = ""
    ) -> builtins.list[SavedPrompt]:
        """Every saved prompt, the most used first, then the newest; `query` keeps those whose
        title or words hold every word asked for."""
        who.require("context.read")
        table = schema.context_items
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table)
                .where(
                    table.c.workspace_id == self.rt.workspace_id,
                    table.c.kind == KIND,
                    table.c.archived_at.is_not(None) if archived else table.c.archived_at.is_(None),
                )
                .order_by(table.c.updated_at.desc())
                .limit(500)
            )
        terms = [t for t in str(query or "").lower().split() if len(t) > 1]
        if terms:
            rows = [r for r in rows if all(t in f"{r['title']} {r['body']}".lower() for t in terms)]
        used = self._uses(who)
        found = [self._shaped(r, used) for r in rows]
        return sorted(found, key=lambda p: -p.uses)

    def get(self, who: Principal, prompt_id: str) -> SavedPrompt:
        who.require("context.read")
        with self.rt.read() as tx:
            row = self._row(tx, prompt_id)
            versions = self._versions(tx, row)
        return self._shaped(row, self._uses(who), versions)

    # ---------------------------------------------------------------- writing

    def create(
        self, who: Principal, *, title: str, body: str, picks: dict[str, Any] | None = None
    ) -> SavedPrompt:
        """Save a prompt, with what it was picked with."""
        self._person(who)
        who.require("context.write")
        with self.rt.write() as tx:
            row = tx.insert(
                schema.context_items,
                {
                    "id": tx.new_id("ctx"),
                    "workspace_id": self.rt.workspace_id,
                    "scope_kind": "workspace",
                    "scope_id": None,
                    "kind": KIND,
                    "title": _title(title),
                    "body": _body(body),
                    "url": None,
                    "object_key": None,
                    "filename": None,
                    "mime": None,
                    "size": None,
                    "content_hash": None,
                    "text_shadow": None,
                    "shadow_status": "none",
                    "idea_state": None,
                    "memory_state": None,
                    "labels": [],
                    "source_label": None,
                    "revision": 1,
                    "last_referenced_at": None,
                    "provenance": {"made_by": who.actor_id, "picks": clean_picks(picks)},
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                    "updated_at": tx.now,
                    "version": 1,
                    "archived_at": None,
                },
            )
            record_revision(tx, who, row)
            tx.emit(
                "prompt.saved",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"title": row["title"]},
            )
        return self.get(who, row["id"])

    def update(
        self,
        who: Principal,
        prompt_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        picks: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> SavedPrompt:
        """Change a saved prompt: new words are a new version; new picks replace the old."""
        self._person(who)
        who.require("context.write")
        with self.rt.write() as tx:
            row = self._row(tx, prompt_id)
            if row["archived_at"]:
                raise Conflict(f"“{row['title']}” is set aside. Bring it back first.")
            changes: dict[str, Any] = {}
            if title is not None and _title(title) != row["title"]:
                changes["title"] = _title(title)
            if body is not None and _body(body) != row["body"]:
                changes["body"] = _body(body)
            if picks is not None:
                cleaned = clean_picks(picks)
                if cleaned != (row["provenance"] or {}).get("picks"):
                    changes["provenance"] = {**(row["provenance"] or {}), "picks": cleaned}
            if not changes:
                return self.get(who, prompt_id)
            worded = "title" in changes or "body" in changes
            if worded:
                changes["revision"] = row["revision"] + 1
            row = tx.update(schema.context_items, row, changes, expected_version=expected_version)
            if worded:
                record_revision(tx, who, row)
            tx.emit(
                "prompt.saved",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"title": row["title"], "revision": row["revision"]},
                noise=not worded,
            )
        return self.get(who, prompt_id)

    def archive(self, who: Principal, prompt_id: str, archived: bool = True) -> SavedPrompt:
        """Set a saved prompt aside (or bring it back); nothing is deleted."""
        self._person(who)
        who.require("context.write")
        with self.rt.write() as tx:
            row = self._row(tx, prompt_id)
            tx.update(schema.context_items, row, {"archived_at": tx.now if archived else None})
            tx.emit(
                "prompt.archived" if archived else "prompt.restored",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"title": row["title"]},
            )
        return self.get(who, prompt_id)

    # ---------------------------------------------------------------- inside

    @staticmethod
    def _person(who: Principal) -> None:
        if not who.is_human:
            raise PermissionDenied("Only a person saves prompts.")

    def _row(self, tx: Tx, prompt_id: str) -> dict[str, Any]:
        row = tx.get(schema.context_items, str(prompt_id or ""))
        if row is None or row["workspace_id"] != self.rt.workspace_id or row["kind"] != KIND:
            raise NotFound(f"No saved prompt {prompt_id}.", id=prompt_id)
        return row

    @staticmethod
    def _versions(tx: Tx, row: dict[str, Any]) -> builtins.list[dict[str, Any]]:
        revisions = schema.context_item_revisions
        rows = tx.rows(
            sa.select(revisions)
            .where(revisions.c.item_id == row["id"])
            .order_by(revisions.c.revision.desc())
            .limit(50)
        )
        return [
            {
                "revision": r["revision"],
                "title": r["title"],
                "body": r["body"],
                "at": r["created_at"],
            }
            for r in rows
        ]

    def _uses(self, who: Principal) -> dict[str, dict[str, Any]]:
        if not who.can("tasks.read"):
            return {}
        return self.skills.tally(who, lambda about: (about.get("prompt") or {}).get("id"))

    @staticmethod
    def _shaped(
        row: dict[str, Any],
        used: dict[str, dict[str, Any]],
        versions: builtins.list[dict[str, Any]] | None = None,
    ) -> SavedPrompt:
        hit = used.get(row["id"]) or {}
        return SavedPrompt(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            picks=clean_picks((row["provenance"] or {}).get("picks")),
            revision=row["revision"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived_at=row["archived_at"],
            uses=int(hit.get("uses") or 0),
            last_used=hit.get("last"),
            versions=versions or [],
        )
