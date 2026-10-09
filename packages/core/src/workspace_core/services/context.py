"""Working context: the messy, human-authored material a scope collects (spec section 07).

Items are typed, scoped, searchable and versioned. An upload keeps its original bytes beside a
generated text shadow; the same bytes linked from several places are stored once. Ideas have a
light lifecycle, and promoting one turns it into a task with the idea pinned.

A person's notes are items too (kind "page", made through services/notes.py), and private: a
model never finds one by searching and opens one only when work assigned to it pins it. Project
memory ("memory"), sheets and canvases are kept from the earlier workspace (services/legacy.py).
"""

from __future__ import annotations

import builtins
import mimetypes
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import ContextItem, Task
from workspace_core.domain.scope import ScopeRef
from workspace_core.domain.states import IDEA
from workspace_core.errors import PermissionDenied, ValidationFailed
from workspace_core.storage.objects import StoredObject

from .runtime import Runtime

# Notes (services/notes.py), the sheets and canvases kept from before, and prompts saved in
# Compose (services/prompts.py): a person's own material, never captured, listed or searched
# here, and read by a model only when work assigned to it pins it.
WORK_KINDS = ("page", "sheet", "canvas", "prompt")
KINDS = (
    "note",
    "idea",
    "link",
    "file",
    "document",
    "image",
    "audio",
    "transcript",
    "memory",
    *WORK_KINDS,
)
CAPTURED = tuple(k for k in KINDS if k != "memory" and k not in WORK_KINDS)
MAX_UPLOAD = 50 * 1024 * 1024
TEXT_MIMES = ("text/", "application/json", "application/xml", "application/x-yaml")
SCOPE_TABLES = {"goal": "goals", "project": "projects", "task": "tasks", "meeting": "meetings"}


def _is_text(mime: str | None) -> bool:
    return bool(mime) and any(str(mime).startswith(p) for p in TEXT_MIMES)


def scope_project(tx: Tx, scope: ScopeRef) -> str | None:
    """The project a scope belongs to (for authority), or None for workspace-wide scopes."""
    if scope.kind == "project":
        return scope.id
    if scope.kind == "task":
        task = tx.one(schema.tasks, str(scope.id), "task")
        return task["project_id"]
    if scope.kind == "meeting":
        meeting = tx.one(schema.meetings, str(scope.id), "meeting")
        return meeting["project_id"]
    return None


@dataclass(frozen=True)
class Prepared:
    """A capture checked, with its file stored and read, ready to write."""

    kind: str
    title: str
    body: str
    url: str | None
    stored: StoredObject | None
    filename: str | None
    mime: str | None
    shadow: str | None
    shadow_status: str
    labels: builtins.list[str]
    source_label: str | None
    provenance: dict[str, Any]


class Context:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    # ---------------------------------------------------------------- queries

    def get(self, who: Principal, item_id: str) -> ContextItem:
        with self.rt.read() as tx:
            row = tx.one(schema.context_items, item_id, "working-context item")
            self._require(tx, who, "context.read", row)
        return ContextItem.from_row(row)

    def list(
        self,
        who: Principal,
        *,
        scope: str | None = None,
        kind: str | None = None,
        exclude_kinds: builtins.list[str] | None = None,
        idea_state: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> builtins.list[ContextItem]:
        who.require("context.read")
        table = schema.context_items
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id)
        if scope:
            ref = ScopeRef.parse(scope)
            query = query.where(table.c.scope_kind == ref.kind)
            query = query.where(
                table.c.scope_id.is_(None) if ref.id is None else table.c.scope_id == ref.id
            )
        if kind:
            query = query.where(table.c.kind == kind)
        else:  # notes are listed by Notes, not with captured context
            query = query.where(table.c.kind.not_in(WORK_KINDS))
        if exclude_kinds:
            query = query.where(table.c.kind.not_in(exclude_kinds))
        if idea_state:
            query = query.where(table.c.idea_state == idea_state)
        if not include_archived:
            query = query.where(table.c.archived_at.is_(None))
        with self.rt.read() as tx:
            rows = tx.rows(query.order_by(table.c.updated_at.desc()).limit(limit))
            return [ContextItem.from_row(r) for r in rows if self._visible(tx, who, r)]

    def search(
        self,
        who: Principal,
        query: str,
        *,
        scope: str | None = None,
        include_archived: bool = False,
        limit: int = 20,
    ) -> builtins.list[ContextItem]:
        """Lexical search over titles, bodies and text shadows (active and archived), notes
        aside."""
        who.require("context.read")
        terms = [t for t in str(query or "").lower().split() if len(t) > 1][:8]
        if not terms:
            return []
        table = schema.context_items
        stmt = sa.select(table).where(
            table.c.workspace_id == self.rt.workspace_id, table.c.kind.not_in(WORK_KINDS)
        )
        haystack = sa.func.lower(
            table.c.title + " " + table.c.body + " " + sa.func.coalesce(table.c.text_shadow, "")
        )
        for term in terms:
            stmt = stmt.where(haystack.contains(term, autoescape=True))
        if scope:
            ref = ScopeRef.parse(scope)
            stmt = stmt.where(table.c.scope_kind == ref.kind)
            if ref.id is not None:
                stmt = stmt.where(table.c.scope_id == ref.id)
        if not include_archived:
            stmt = stmt.where(table.c.archived_at.is_(None))
        with self.rt.read() as tx:
            rows = [r for r in tx.rows(stmt.limit(500)) if self._visible(tx, who, r)]

        def rank(row: dict[str, Any]) -> tuple[int, str]:
            title = row["title"].lower()
            return (-sum(term in title for term in terms), row["updated_at"])

        rows.sort(key=rank)
        return [ContextItem.from_row(r) for r in rows[:limit]]

    def revisions(self, who: Principal, item_id: str) -> builtins.list[dict[str, Any]]:
        self.get(who, item_id)
        table = schema.context_item_revisions
        with self.rt.read() as tx:
            return tx.rows(
                sa.select(table).where(table.c.item_id == item_id).order_by(table.c.revision)
            )

    def content(self, who: Principal, item_id: str) -> tuple[ContextItem, bytes]:
        item = self.get(who, item_id)
        if not item.object_key:
            raise ValidationFailed("This item has no file.")
        return item, self.rt.objects.read(item.object_key)

    def uploads(self, who: Principal, *, limit: int = 200) -> builtins.list[ContextItem]:
        """Every uploaded file in working context, newest first. Each keeps its original
        bytes beside the text read from it."""
        who.require("context.read")
        table = schema.context_items
        query = (
            sa.select(table)
            .where(
                table.c.workspace_id == self.rt.workspace_id,
                table.c.object_key.is_not(None),
                table.c.archived_at.is_(None),
            )
            .order_by(table.c.created_at.desc())
            .limit(max(1, min(limit, 500)))
        )
        with self.rt.read() as tx:
            return [ContextItem.from_row(r) for r in tx.rows(query) if self._visible(tx, who, r)]

    def markdown(self, who: Principal, item_id: str) -> tuple[str, str]:
        """An uploaded file's text as a Markdown document: (file name, text)."""
        item = self.get(who, item_id)
        if not item.object_key:
            raise ValidationFailed("This item has no file.")
        if item.shadow_status != "ready" or not (item.text_shadow or "").strip():
            raise ValidationFailed("No text could be read from this file.")
        original = item.filename or item.title
        stem = original.rsplit(".", 1)[0] if "." in original else original
        heading = " ".join(stem.replace("_", " ").replace("-", " ").split()) or "Document"
        text = (
            f"# {heading}\n\n> Text read from {original} on {item.created_at[:10]}. "
            "The original file is kept in the workspace.\n\n"
            f"{str(item.text_shadow).strip()}\n"
        )
        return f"{stem or 'document'}.md", text

    # ---------------------------------------------------------------- writes

    def capture(
        self,
        who: Principal,
        *,
        scope: str,
        kind: str = "note",
        title: str = "",
        body: str = "",
        url: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime: str | None = None,
        labels: builtins.list[str] | None = None,
        source_label: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> ContextItem:
        ref = ScopeRef.parse(scope)
        prepared = self.prepare(
            kind=kind,
            title=title,
            body=body,
            url=url,
            data=data,
            filename=filename,
            mime=mime,
            labels=labels,
            source_label=source_label,
            provenance=provenance,
        )
        with self.rt.write() as tx:
            row = self.insert(tx, who, ref, prepared)
        return ContextItem.from_row(row)

    def prepare(
        self,
        *,
        kind: str = "note",
        title: str = "",
        body: str = "",
        url: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime: str | None = None,
        labels: builtins.list[str] | None = None,
        source_label: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Prepared:
        """Check a capture and do its slow part (store the file, read its text) before any
        transaction opens."""
        if kind == "memory":
            raise ValidationFailed(
                "Project memory is kept from the project's Memory tab, or suggested by a model "
                "during a run.",
                field="kind",
            )
        if kind not in CAPTURED:
            raise ValidationFailed(f"Kind must be one of {', '.join(CAPTURED)}.", field="kind")
        body = str(body or "")
        stored = None
        shadow, shadow_status = None, "none"
        if data is not None:
            if len(data) > MAX_UPLOAD:
                raise ValidationFailed("Files are at most 50 MB.", field="file")
            mime = mime or mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
            stored = self.rt.objects.put(data)
            shadow, shadow_status = self._shadow(data, filename or "", mime)
        if not (body.strip() or url or stored):
            raise ValidationFailed("Capture needs some text, a link or a file.")
        title = (
            " ".join(str(title or "").split())
            or (filename or "")
            or _first_line(body)
            or (url or "Untitled")
        )
        return Prepared(
            kind=kind,
            title=title[:300],
            body=body,
            url=url,
            stored=stored,
            filename=filename,
            mime=mime if stored else None,
            shadow=shadow,
            shadow_status=shadow_status,
            labels=sorted(set(labels or [])),
            source_label=source_label,
            provenance=provenance or {},
        )

    def insert(self, tx: Tx, who: Principal, ref: ScopeRef, prepared: Prepared) -> dict[str, Any]:
        """Write a prepared capture inside the caller's transaction."""
        self._check_scope(tx, who, ref)
        who.require("context.write", scope_project(tx, ref))
        stored = prepared.stored
        row = tx.insert(
            schema.context_items,
            {
                "id": tx.new_id("ctx"),
                "workspace_id": self.rt.workspace_id,
                "scope_kind": ref.kind,
                "scope_id": ref.id,
                "kind": prepared.kind,
                "title": prepared.title,
                "body": prepared.body,
                "url": prepared.url,
                "object_key": stored.key if stored else None,
                "filename": prepared.filename,
                "mime": prepared.mime,
                "size": stored.size if stored else None,
                "content_hash": stored.key if stored else None,
                "text_shadow": prepared.shadow,
                "shadow_status": prepared.shadow_status,
                "idea_state": IDEA.initial if prepared.kind == "idea" else None,
                "memory_state": None,
                "labels": prepared.labels,
                "source_label": prepared.source_label,
                "revision": 1,
                "last_referenced_at": None,
                "provenance": prepared.provenance,
                "created_by": who.actor_id,
                "created_at": tx.now,
                "updated_at": tx.now,
                "version": 1,
                "archived_at": None,
            },
        )
        self._revision(tx, who, row)
        tx.emit(
            "context.captured",
            actor_id=who.actor_id,
            subject_type="context_item",
            subject_id=row["id"],
            project_id=scope_project(tx, ref),
            data={"kind": prepared.kind, "title": row["title"], "scope": str(ref)},
        )
        return row

    def update(
        self,
        who: Principal,
        item_id: str,
        *,
        expected_version: int | None = None,
        title: str | None = None,
        body: str | None = None,
        url: str | None = None,
        labels: builtins.list[str] | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime: str | None = None,
    ) -> ContextItem:
        with self.rt.write() as tx:
            row = tx.one(schema.context_items, item_id, "working-context item")
            self._require(tx, who, "context.write", row)
            changes: dict[str, Any] = {}
            if title is not None:
                changes["title"] = " ".join(title.split())[:300] or row["title"]
            if body is not None:
                changes["body"] = body
            if url is not None:
                changes["url"] = url or None
            if labels is not None:
                changes["labels"] = sorted(set(labels))
            if data is not None:
                mime = (
                    mime
                    or mimetypes.guess_type(filename or row["filename"] or "")[0]
                    or "application/octet-stream"
                )
                stored = self.rt.objects.put(data)
                shadow, status = self._shadow(data, filename or row["filename"] or "", mime)
                changes.update(
                    object_key=stored.key,
                    content_hash=stored.key,
                    size=stored.size,
                    mime=mime,
                    filename=filename or row["filename"],
                    text_shadow=shadow,
                    shadow_status=status,
                )
            changes = {k: v for k, v in changes.items() if v != row[k]}
            if not changes:
                return ContextItem.from_row(row)
            content_changed = bool({"title", "body", "object_key"} & set(changes))
            if content_changed:
                changes["revision"] = row["revision"] + 1
            row = tx.update(schema.context_items, row, changes, expected_version=expected_version)
            if content_changed:
                self._revision(tx, who, row)
            tx.emit(
                "context.updated",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=item_id,
                project_id=self._project(tx, row),
                data={"fields": sorted(changes), "revision": row["revision"]},
            )
        return ContextItem.from_row(row)

    def set_idea_state(self, who: Principal, item_id: str, state: str) -> ContextItem:
        with self.rt.write() as tx:
            row = tx.one(schema.context_items, item_id, "working-context item")
            self._require(tx, who, "context.write", row)
            if row["kind"] != "idea":
                raise ValidationFailed("Only ideas have an idea state.")
            IDEA.check(row["idea_state"], state)
            row = tx.update(schema.context_items, row, {"idea_state": state})
            tx.emit(
                "context.idea_state",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=item_id,
                project_id=self._project(tx, row),
                data={"state": state},
            )
        return ContextItem.from_row(row)

    def archive(self, who: Principal, item_id: str, archived: bool = True) -> ContextItem:
        with self.rt.write() as tx:
            row = tx.one(schema.context_items, item_id, "working-context item")
            self._require(tx, who, "context.write", row)
            row = tx.update(
                schema.context_items, row, {"archived_at": tx.now if archived else None}
            )
            tx.emit(
                "context.archived" if archived else "context.restored",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=item_id,
                project_id=self._project(tx, row),
            )
        return ContextItem.from_row(row)

    def mark_promoted(self, tx: Tx, who: Principal, item: dict[str, Any], task_id: str) -> None:
        if item["kind"] == "idea" and item["idea_state"] != "promoted":
            IDEA.check(item["idea_state"], "promoted")
            tx.update(schema.context_items, item, {"idea_state": "promoted"})
        tx.emit(
            "context.promoted",
            actor_id=who.actor_id,
            subject_type="context_item",
            subject_id=item["id"],
            project_id=self._project(tx, item),
            data={"task_id": task_id},
        )

    def promote(self, who: Principal, item_id: str, tasks: Any, **task_fields: Any) -> Task:
        """Turn an idea (or any item) into a draft task with the item pinned to it."""
        item = self.get(who, item_id)
        project_id = task_fields.pop("project_id", None)
        if project_id is None and item.scope_kind == "project":
            project_id = item.scope_id
        task = tasks.create(
            who,
            project_id=project_id,
            title=task_fields.pop("title", None) or item.title,
            purpose=task_fields.pop("purpose", None) or item.body[:2000],
            **task_fields,
        )
        tasks.pin(who, task.id, ref_type="context_item", ref_id=item.id)
        with self.rt.write() as tx:
            row = tx.one(schema.context_items, item_id, "working-context item")
            self.mark_promoted(tx, who, row, task.id)
        return task

    # ---------------------------------------------------------------- internals

    def _shadow(self, data: bytes, filename: str, mime: str) -> tuple[str | None, str]:
        if _is_text(mime):
            return data.decode("utf-8", errors="replace"), "ready"
        if mime.startswith("audio/") or mime.startswith("video/"):
            return None, "pending"  # transcription is a worker job, when one is configured
        if self.rt.extractor is None:
            return None, "unavailable"
        try:
            text = self.rt.extractor.extract(data, filename, mime)
        except Exception:  # noqa: BLE001 - a bad file must not fail the capture
            return None, "failed"
        return (text, "ready") if text else (None, "unavailable")

    def _revision(self, tx: Tx, who: Principal, row: dict[str, Any]) -> None:
        record_revision(tx, who, row)

    def _check_scope(self, tx: Tx, who: Principal, ref: ScopeRef) -> None:
        if ref.kind in SCOPE_TABLES:
            tx.one(getattr(schema, SCOPE_TABLES[ref.kind]), str(ref.id), ref.kind)
        if ref.kind == "inbox" and ref.id != who.actor_id and not who.is_human:
            raise PermissionDenied("A model can only capture into its own inbox.")

    def _project(self, tx: Tx, row: dict[str, Any]) -> str | None:
        return scope_project(tx, ScopeRef(row["scope_kind"], row["scope_id"]))

    def _require(self, tx: Tx, who: Principal, action: str, row: dict[str, Any]) -> None:
        who.require(action, self._project(tx, row))
        if not open_to(tx, who, row):
            raise PermissionDenied(
                "A person's notes reach a model only through work that pins them.",
                item_id=row["id"],
            )

    def _visible(self, tx: Tx, who: Principal, row: dict[str, Any]) -> bool:
        if row["scope_kind"] == "inbox" and row["scope_id"] != who.actor_id and not who.is_human:
            return False
        return who.sees_project(self._project(tx, row)) and open_to(tx, who, row)


def open_to(tx: Tx, who: Principal, row: dict[str, Any]) -> bool:
    """Whether `who` may read this item at all: a person's notes are theirs, so a model reads
    one only when work assigned to it pins it ("Find what to remember", say)."""
    if who.kind != "model" or row["kind"] not in WORK_KINDS:
        return True
    pins, tasks = schema.task_pins, schema.tasks
    pinned = tx.first(
        sa.select(pins.c.task_id)
        .join(tasks, tasks.c.id == pins.c.task_id)
        .where(
            pins.c.ref_type == "context_item",
            pins.c.ref_id == row["id"],
            tasks.c.assignee_id == who.actor_id,
        )
    )
    return pinned is not None


def record_revision(tx: Tx, who: Principal, row: dict[str, Any]) -> None:
    """Keep the item's text as it now stands, as its current revision."""
    tx.insert(
        schema.context_item_revisions,
        {
            "item_id": row["id"],
            "revision": row["revision"],
            "title": row["title"],
            "body": row["body"],
            "object_key": row["object_key"],
            "content_hash": row["content_hash"],
            "created_by": who.actor_id,
            "created_at": tx.now,
        },
    )


def _first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        line = line.strip(" #*-\t")
        if line:
            return line[:120]
    return ""
