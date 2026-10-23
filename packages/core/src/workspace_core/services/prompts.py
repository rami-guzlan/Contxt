"""Saved prompts: the person's own words for later, kept in the Brain's Library.

A prompt is kept word for word, with its title, its tags, the project it is for and what it was
used with (skills in order, an agent, Workspace docs, Library items to read whole), versioned by
the Brain's history. It lives in the person's own scope and is never routed into a brief unless
a request names it: any AI connected to the Brain finds it by name or by search, and saves one
from a conversation with files_upload (kind prompt). Each run from it counts as a use, so the
often-used ones are suggested as skills.

Prompts saved before they moved into the Brain (context items of kind "prompt" in the app's own
database) move once, the first time the list is read: each goes in as a prompt with its title,
its picks and every version of its words, and its old row is set aside, saying where it went.
"""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.ids import is_id

from .runtime import Runtime
from .skills import Skills

if TYPE_CHECKING:
    from .brain import Brain

KIND = "prompt"  # the old store: context items of this kind, read once to move them
MAX_TITLE = 200
MAX_BODY = 20000
MAX_SKILLS = 6
MAX_DOCS = 5
MAX_LIBRARY = 5
MAX_TAGS = 12


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


def clean_tags(tags: Any) -> builtins.list[str]:
    items = tags.split(",") if isinstance(tags, str) else list(tags or [])
    found = list(dict.fromkeys(" ".join(str(t).split())[:40] for t in items if str(t).strip()))
    if len(found) > MAX_TAGS:
        raise ValidationFailed(f"At most {MAX_TAGS} tags.", field="tags")
    return found


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


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "prompt"


@dataclass(frozen=True)
class SavedPrompt:
    id: str
    title: str
    body: str
    picks: dict[str, Any]
    revision: int
    version: int
    created_at: str | None
    updated_at: str | None
    archived_at: str | None
    uses: int = 0
    last_used: str | None = None
    versions: builtins.list[dict[str, Any]] = field(default_factory=list)
    path: str = ""
    tags: builtins.list[str] = field(default_factory=list)
    project: str | None = None
    project_title: str | None = None
    origin: str | None = None
    scope: str | None = None
    attachments: builtins.list[dict[str, Any]] = field(default_factory=list)


class Prompts:
    def __init__(self, rt: Runtime, skills: Skills, brain: Brain) -> None:
        self.rt = rt
        self.skills = skills
        self.brain = brain

    # ---------------------------------------------------------------- reading

    def list(
        self, who: Principal, *, archived: bool = False, query: str = ""
    ) -> builtins.list[SavedPrompt]:
        """Every prompt, the most used first, then the newest; `query` keeps those whose
        title, words or tags hold every word asked for."""
        who.require("brain.read")
        if who.is_human and not archived:
            self._move_in(who)
        rows = self.rt.brain.prompts(archived=archived)
        terms = [t for t in str(query or "").lower().split() if len(t) > 1]
        if terms:
            rows = [
                r
                for r in rows
                if all(
                    t in f"{r['title']} {r['body']} {' '.join(r['tags'])}".lower() for t in terms
                )
            ]
        used = self._uses(who)
        found = [self._shaped(r, used) for r in rows]
        return sorted(found, key=lambda p: -p.uses)

    def get(self, who: Principal, prompt_id: str) -> SavedPrompt:
        """One prompt; an id from before prompts moved into the Brain finds where it went."""
        who.require("brain.read")
        wanted = str(prompt_id or "")
        row = self.rt.brain.prompt(wanted)
        if row is None and is_id(wanted, "ctx"):
            if who.is_human and wanted not in self._moved():
                self._move_in(who)
            moved = self._moved().get(wanted)
            row = self.rt.brain.prompt(moved) if moved else None
        if row is None:
            raise NotFound(f"No prompt {prompt_id}.", id=prompt_id)
        return self._shaped(row, self._uses(who))

    # ---------------------------------------------------------------- writing

    def create(
        self,
        who: Principal,
        *,
        title: str,
        body: str,
        picks: dict[str, Any] | None = None,
        tags: Any = None,
        came_from: str = "upload",
    ) -> SavedPrompt:
        """Keep a prompt in the Brain, word for word, with what it was picked with."""
        self._person(who)
        cleaned = clean_picks(picks)
        title = _title(title)
        result = self.brain.add_file(
            who,
            filename=f"{_slug(title)}.md",
            data=_body(body).encode("utf-8"),
            title=title,
            project=cleaned["project"],
            library=self._card(cleaned, clean_tags(tags)),
            came_from=came_from,
        )
        return self._filed(who, result)

    def update(
        self,
        who: Principal,
        prompt_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        picks: dict[str, Any] | None = None,
        tags: Any = None,
        expected_version: int | None = None,
    ) -> SavedPrompt:
        """New words are a new version; a new title, new tags or new picks change its card.
        Each is one undo point."""
        self._person(who)
        current = self.get(who, prompt_id)
        if current.archived_at:
            raise Conflict(f"“{current.title}” is set aside. Bring it back first.")
        if expected_version is not None and expected_version != current.version:
            raise Conflict("It changed since you opened it: reload and try again.")
        if body is not None and _body(body) != current.body:
            result = self.brain.add_file(
                who,
                filename=current.path.rsplit("/", 1)[-1],
                data=_body(body).encode("utf-8"),
                title=current.title,
                replaces=current.path,
            )
            if result.status not in ("applied", "duplicate"):
                raise Conflict(result.message)
        fields: dict[str, str] = {}
        if title is not None and _title(title) != current.title:
            fields["title"] = _title(title)
        if tags is not None and clean_tags(tags) != current.tags:
            fields["tags"] = ", ".join(clean_tags(tags))
        if picks is not None:
            cleaned = clean_picks(picks)
            for key, name in (
                ("skills", "prompt_skills"),
                ("docs", "prompt_docs"),
                ("library", "prompt_reads"),
            ):
                if cleaned[key] != current.picks.get(key):
                    fields[name] = ", ".join(cleaned[key])
            if cleaned["agent"] != current.picks.get("agent"):
                fields["prompt_agent"] = cleaned["agent"] or ""
            if cleaned["project"] != current.project:
                fields["project_id"] = cleaned["project"] or ""
        if fields:
            self._decide(who, current.id, "update", f"Prompt: {current.title}", fields=fields)
        return self.get(who, current.id)

    def archive(self, who: Principal, prompt_id: str, archived: bool = True) -> SavedPrompt:
        """Set a prompt aside (or bring it back); nothing is deleted."""
        self._person(who)
        current = self.get(who, prompt_id)
        if bool(current.archived_at) != archived:
            self._decide(
                who,
                current.id,
                "archive" if archived else "unarchive",
                f"Prompt {'set aside' if archived else 'brought back'}: {current.title}",
                reason="set aside" if archived else "",
            )
        return self.get(who, current.id)

    # ---------------------------------------------------------------- moving in

    def _move_in(self, who: Principal) -> int:
        """Move prompts saved in the app's own database into the Brain, once each, with every
        version of their words: the first is kept, then each later one as a new version."""
        table = schema.context_items
        revisions = schema.context_item_revisions
        with self.rt.read() as tx:
            rows = [
                row
                for row in tx.rows(
                    sa.select(table).where(
                        table.c.workspace_id == self.rt.workspace_id,
                        table.c.kind == KIND,
                        table.c.archived_at.is_(None),
                    )
                )
                if not (row["provenance"] or {}).get("moved_to")
            ]
            earlier = {
                row["id"]: [
                    r["body"]
                    for r in tx.rows(
                        sa.select(revisions.c.body)
                        .where(revisions.c.item_id == row["id"])
                        .order_by(revisions.c.revision)
                    )
                ]
                for row in rows
            }
        moved = 0
        for row in rows:
            history: builtins.list[str] = []
            for body in [*earlier.get(row["id"], []), row["body"]]:
                words = str(body or "").replace("\r\n", "\n").strip()
                if words and (not history or history[-1] != words):
                    history.append(words)
            if not history:
                continue
            provenance = dict(row["provenance"] or {})
            try:
                made = self.create(
                    who,
                    title=row["title"],
                    body=history[0],
                    picks=provenance.get("picks"),
                    came_from="upload",
                )
            except (ValidationFailed, Conflict):
                continue
            for words in history[1:]:
                try:
                    made = self.update(who, made.id, body=words)
                except (ValidationFailed, Conflict):
                    break  # kept with the versions that went in; the old row says where
            with self.rt.write() as tx:
                fresh = tx.get(table, row["id"])
                if fresh is not None:
                    tx.update(
                        table,
                        fresh,
                        {
                            "provenance": {**provenance, "moved_to": made.id},
                            "archived_at": tx.now,
                        },
                    )
            moved += 1
        return moved

    # ---------------------------------------------------------------- inside

    @staticmethod
    def _card(picks: dict[str, Any], tags: builtins.list[str]) -> dict[str, Any]:
        return {
            "library": "prompt",
            "tags": tags,
            "prompt_skills": picks["skills"],
            "prompt_agent": picks["agent"],
            "prompt_docs": picks["docs"],
            "prompt_reads": picks["library"],
        }

    def _filed(self, who: Principal, result: Any) -> SavedPrompt:
        if result.status == "pending":
            raise Conflict(f"{result.message} It waits for your review in Catch up.")
        if result.status not in ("applied", "duplicate") or not result.path:
            raise Conflict(result.message or "The prompt could not be kept.")
        row = next(
            (r for r in self.rt.brain.prompts() if r["path"] == result.path),
            None,
        )
        if row is None:
            raise Conflict(f"{result.path} was filed, but not as a prompt.")
        return self._shaped(row, self._uses(who))

    def _decide(
        self,
        who: Principal,
        prompt_id: str,
        action: str,
        label: str,
        *,
        fields: dict[str, str] | None = None,
        reason: str = "",
    ) -> None:
        decision: dict[str, Any] = {"action": action, "entry_id": prompt_id}
        if fields:
            decision["fields"] = fields
        if reason:
            decision["reason"] = reason
        result = self.brain.decide_many(who, [decision], label=label)
        (outcome,) = result["results"]
        if not outcome.get("ok"):
            raise ValidationFailed(str(outcome.get("message") or "Not changed."))

    @staticmethod
    def _person(who: Principal) -> None:
        if not who.is_human:
            raise PermissionDenied(
                "Only a person saves prompts here; an AI keeps one with files_upload in a "
                "conversation."
            )

    def _uses(self, who: Principal) -> dict[str, dict[str, Any]]:
        """Runs by prompt; a run from before the move counts for where its prompt went."""
        if not who.can("tasks.read"):
            return {}
        tally = self.skills.tally(who, lambda about: (about.get("prompt") or {}).get("id"))
        moved = self._moved() if any(is_id(key, "ctx") for key in tally) else {}
        out: dict[str, dict[str, Any]] = {}
        for key, hit in tally.items():
            into = out.setdefault(moved.get(key, key), {"uses": 0, "last": None})
            into["uses"] += int(hit.get("uses") or 0)
            if hit.get("last") and str(hit["last"]) > str(into["last"] or ""):
                into["last"] = hit["last"]
        return out

    def _moved(self) -> dict[str, str]:
        """{old saved prompt id: its prompt in the Brain}, so runs before the move count."""
        table = schema.context_items
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table.c.id, table.c.provenance).where(
                    table.c.workspace_id == self.rt.workspace_id, table.c.kind == KIND
                )
            )
        return {
            r["id"]: str((r["provenance"] or {}).get("moved_to"))
            for r in rows
            if (r["provenance"] or {}).get("moved_to")
        }

    @staticmethod
    def _shaped(row: dict[str, Any], used: dict[str, dict[str, Any]]) -> SavedPrompt:
        hit = used.get(row["id"]) or {}
        version = int(row.get("version") or 1)
        return SavedPrompt(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            picks=clean_picks(row.get("picks")),
            revision=version,
            version=version,
            created_at=row.get("added"),
            updated_at=row.get("updated"),
            # Set aside: when its file last changed, which is when it was set aside.
            archived_at=(row.get("updated") or "set aside") if row.get("archived") else None,
            uses=int(hit.get("uses") or 0),
            last_used=hit.get("last"),
            versions=[
                {
                    "revision": len(row.get("versions") or []) - i,
                    "title": row["title"],
                    "body": v["body"],
                    "at": v.get("at"),
                }
                for i, v in enumerate(row.get("versions") or [])
            ],
            path=row.get("path") or "",
            tags=list(row.get("tags") or []),
            project=row.get("project"),
            project_title=row.get("project_title"),
            origin=row.get("origin"),
            scope=row.get("scope"),
            attachments=list(row.get("attachments") or []),
        )
