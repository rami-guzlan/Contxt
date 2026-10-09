"""Notes: the person's scratchpad, private until they add a note to the Brain.

A note is a working-context item of kind `page` (Markdown), in the person's own space (scope
`workspace`). No AI reads it until the person shares it: "Add to the Brain" files it as a
document (in a project when one is chosen, as a new version when one by that name is there),
and "Find what to remember" asks a model to propose what in it should last (a distillation
request with the note pinned at its current version).

Its versions are the item's revisions, grouped the way people write: saves by the same person
join the version they are in until they pause for `IDLE`; a pause, another author, a restore
or a named version starts the next one. A restore and a name seal their version.

A note can also be a capture (services/captures.py): something spoken, recorded or brought in,
which says what it is (`capture`), keeps what was brought in (`original`) and, for audio, how far
its transcription is (`transcription`). A note being transcribed cannot be edited yet.
"""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import parse_iso
from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.ports import BrainProposal

from .context import open_to, record_revision
from .runtime import Runtime

KIND = "page"
UNTITLED = "Untitled note"
IDLE = timedelta(minutes=10)  # a pause this long starts the next version
MAX_BODY = 2_000_000  # characters: a long note
MAX_TITLE = 300
MARKUP = re.compile(r"^(?:#{1,6}\s+|>\s*|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)+")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# *a*, **a**, ***a***, and _a_ or __a__ standing alone (not inside a snake_case word)
EMPHASIS = re.compile(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1|(?<!\w)(_{1,3})(?=\S)(.+?)(?<=\S)\3(?!\w)")
STATUS = re.compile(r"^[a-z][a-z -]{0,29}$")
# What a capture is (its item's `source_label`); anything else is a note typed here. A "link"
# is a Workspace item that points somewhere (a calendar, a sheet, a folder): its `url`.
CAPTURE_KINDS = ("note", "talk", "recording", "transcript", "document", "link")
# A note linked to a project carries a label naming it: linked, never copied, still private.
PROJECT_LABEL = "project:"
MAX_PROJECTS = 10
SPOKEN = ("talk", "recording")
TRANSCRIBING = ("pending", "working")
TRANSCRIPTION_STATES = ("pending", "working", "ready", "failed")


def cut(text: str, limit: int) -> str:
    """Text on one line, cut at a word to fit `limit`."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


def first_line(body: str, limit: int = 80) -> str:
    """A note's first line of text, without Markdown, cut at a word: the title of a note
    nobody has named yet."""
    for line in body.splitlines():
        text = LINK.sub(r"\1", MARKUP.sub("", line.strip()))
        text = EMPHASIS.sub(lambda m: m.group(2) or m.group(4), text)
        text = text.replace("`", "").replace("\\", "")
        if not text.strip() or set(text.strip()) <= set("-*_=|: "):
            continue
        return cut(text, limit)
    return ""


def clean_body(body: Any) -> str:
    text = str(body or "").replace("\r\n", "\n")
    if len(text) > MAX_BODY:
        raise ValidationFailed(
            f"Keep a note under {MAX_BODY:,} characters; split it.", field="body"
        )
    return text


def _title(value: Any) -> str:
    return " ".join(str(value or "").split())[:MAX_TITLE] or UNTITLED


def _named(row: dict[str, Any], title: str | None, body: str | None) -> str | None:
    """The title a save gives a note: the one asked for, or, for a note still untitled, its
    first line. None leaves the title as it is."""
    if title is not None:
        return _title(title)
    if body is not None and row["title"] == UNTITLED:
        return first_line(body) or None
    return None


def _person(who: Principal) -> None:
    """Notes are written by people; a model's work comes back as proposals instead."""
    if not who.is_human:
        raise PermissionDenied("Only a person writes in their notes.")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug[:60].rstrip("-") or "note"


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    body: str
    revision: int
    version: int
    created_by: str
    created_at: str
    updated_at: str
    edited_by: str | None  # who made the current version (a name)
    archived_at: str | None
    capture: str = "note"  # note, talk, recording, transcript or document
    original: dict[str, Any] | None = None  # what was brought in: filename, mime, size
    transcription: dict[str, Any] | None = None  # state, progress, duration, error
    digest: dict[str, Any] | None = None  # its summary and key points, or how far it is
    projects: builtins.list[str] = field(default_factory=list)  # the projects it is linked to
    url: str | None = None  # where a link points


@dataclass(frozen=True)
class NoteVersion:
    revision: int
    title: str
    body: str | None  # left out of listings
    size: int
    by: str  # a name
    at: str
    label: str | None
    sealed: bool
    current: bool


class Notes:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    # ---------------------------------------------------------------- reading

    def list(
        self, who: Principal, *, archived: bool = False, limit: int = 200
    ) -> builtins.list[Note]:
        """The caller's notes, most recently changed first."""
        who.require("context.read")
        table = schema.context_items
        query = sa.select(table).where(
            table.c.workspace_id == self.rt.workspace_id,
            table.c.kind == KIND,
            table.c.archived_at.is_not(None) if archived else table.c.archived_at.is_(None),
        )
        with self.rt.read() as tx:
            rows = tx.rows(query.order_by(table.c.updated_at.desc()).limit(min(limit, 1000)))
            rows = [r for r in rows if who.sees_project(_project(r)) and open_to(tx, who, r)]
            return self._notes(tx, rows)

    def search(self, who: Principal, query: str, *, limit: int = 10) -> builtins.list[Note]:
        """The caller's notes whose title or text holds every word asked for, titles first."""
        terms = [t for t in str(query or "").lower().split() if len(t) > 1][:8]
        if not terms:
            return []
        found = [
            n
            for n in self.list(who, limit=1000)
            if all(t in f"{n.title} {n.body}".lower() for t in terms)
        ]
        found.sort(key=lambda n: -sum(t in n.title.lower() for t in terms))
        return found[:limit]

    def get(self, who: Principal, note_id: str) -> Note:
        with self.rt.read() as tx:
            row = self._readable(tx, who, note_id)
            return self._notes(tx, [row])[0]

    def versions(self, who: Principal, note_id: str) -> builtins.list[NoteVersion]:
        """Every version, newest first, without their text."""
        with self.rt.read() as tx:
            row = self._readable(tx, who, note_id)
            return self._versions(tx, row, with_body=False)

    def version(self, who: Principal, note_id: str, revision: int) -> NoteVersion:
        with self.rt.read() as tx:
            row = self._readable(tx, who, note_id)
            found = [v for v in self._versions(tx, row, with_body=True) if v.revision == revision]
            if not found:
                raise NotFound(f"No version {revision} of this note.")
            return found[0]

    # ---------------------------------------------------------------- writing

    def create(
        self,
        who: Principal,
        *,
        title: str = "",
        body: Any = None,
        projects: builtins.list[str] | None = None,
        url: str | None = None,
    ) -> Note:
        """A new note in the caller's own space, linked to projects when given; with `url`, a
        link (a calendar, a sheet, a folder) kept as a note that points there."""
        who.require("context.write")
        _person(who)
        text = clean_body(body)
        link = _url(url) if url else None
        if link and not text.strip():
            text = link
        with self.rt.write() as tx:
            row = tx.insert(
                schema.context_items,
                {
                    "id": tx.new_id("ctx"),
                    "workspace_id": self.rt.workspace_id,
                    "scope_kind": "workspace",
                    "scope_id": None,
                    "kind": KIND,
                    "title": _named({"title": UNTITLED}, title or None, text) or UNTITLED,
                    "body": text,
                    "url": link,
                    "object_key": None,
                    "filename": None,
                    "mime": None,
                    "size": None,
                    "content_hash": None,
                    "text_shadow": None,
                    "shadow_status": "none",
                    "idea_state": None,
                    "memory_state": None,
                    "labels": project_labels([], projects or []),
                    "source_label": "link" if link else None,
                    "revision": 1,
                    "last_referenced_at": None,
                    "provenance": {"made_by": who.actor_id},
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                    "updated_at": tx.now,
                    "version": 1,
                    "archived_at": None,
                },
            )
            record_revision(tx, who, row)
            tx.emit(
                "note.created",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"title": row["title"]},
            )
            return self._notes(tx, [row])[0]

    def save(
        self,
        who: Principal,
        note_id: str,
        *,
        title: str | None = None,
        body: Any = None,
        expected_version: int | None = None,
    ) -> Note:
        """Save what the caller wrote. It joins the version the caller is in (theirs, not
        sealed, saved less than IDLE ago), or starts the next one."""
        with self.rt.write() as tx:
            row = self._writable(tx, who, note_id)
            if row["archived_at"]:
                raise Conflict(f"“{row['title']}” is archived. Restore it first.")
            if row["shadow_status"] in TRANSCRIBING and _capture(row) in SPOKEN:
                raise Conflict("It is still being turned into text. Edit it once the text is in.")
            changes: dict[str, Any] = {}
            if body is not None:
                changes["body"] = clean_body(body)
            named = _named(row, title, changes.get("body"))
            if named is not None:
                changes["title"] = named
            changes = {k: v for k, v in changes.items() if v != row[k]}
            if not changes:
                return self._notes(tx, [row])[0]
            current = self._current(tx, row)
            joins = (
                current is not None
                and current["created_by"] == who.actor_id
                and not current["sealed"]
                and parse_iso(row["updated_at"]) > tx.moment - IDLE
            )
            if not joins:
                changes["revision"] = row["revision"] + 1
            row = tx.update(schema.context_items, row, changes, expected_version=expected_version)
            if joins:
                revisions = schema.context_item_revisions
                tx.conn.execute(
                    revisions.update()
                    .where(
                        revisions.c.item_id == row["id"],
                        revisions.c.revision == row["revision"],
                    )
                    .values(title=row["title"], body=row["body"])
                )
            else:
                record_revision(tx, who, row)
            tx.emit(
                "note.saved" if joins else "note.edited",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"revision": row["revision"], "title": row["title"]},
                noise=joins,  # each autosave is noise; a new version is news
            )
            return self._notes(tx, [row])[0]

    def set_projects(self, who: Principal, note_id: str, projects: builtins.list[str]) -> Note:
        """Link a note to these projects (and no others). A link is a label: the note stays
        private, and is never copied."""
        with self.rt.write() as tx:
            row = self._writable(tx, who, note_id)
            labels = project_labels(row["labels"] or [], projects)
            if labels != sorted(row["labels"] or []):
                row = tx.update(schema.context_items, row, {"labels": labels})
                tx.emit(
                    "note.linked",
                    actor_id=who.actor_id,
                    subject_type="context_item",
                    subject_id=row["id"],
                    data={"projects": _projects(row)},
                    noise=True,
                )
            return self._notes(tx, [row])[0]

    def name_version(self, who: Principal, note_id: str, label: str) -> Note:
        """Name the current version and seal it: the next save starts a new one."""
        text = " ".join(str(label or "").split())[:200]
        if not text:
            raise ValidationFailed("Give the version a name.", field="label")
        with self.rt.write() as tx:
            row = self._writable(tx, who, note_id)
            revisions = schema.context_item_revisions
            tx.conn.execute(
                revisions.update()
                .where(revisions.c.item_id == row["id"], revisions.c.revision == row["revision"])
                .values(label=text, sealed=True)
            )
            tx.emit(
                "note.named",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"revision": row["revision"], "label": text},
            )
            return self._notes(tx, [row])[0]

    def add_version(self, who: Principal, note_id: str, *, body: Any, label: str) -> Note:
        """Text from elsewhere (what an AI made, taken by the owner) as a new version of its own,
        named and sealed: the version before it stays whole, and the next edit starts afresh."""
        text = " ".join(str(label or "").split())[:200]
        if not text:
            raise ValidationFailed("Give the version a name.", field="label")
        with self.rt.write() as tx:
            row = self._writable(tx, who, note_id)
            if row["archived_at"]:
                raise Conflict(f"“{row['title']}” is archived. Restore it first.")
            revisions = schema.context_item_revisions
            # Seal the version the owner was writing in, so the next one never joins it.
            tx.conn.execute(
                revisions.update()
                .where(revisions.c.item_id == row["id"], revisions.c.revision == row["revision"])
                .values(sealed=True)
            )
            row = tx.update(
                schema.context_items,
                row,
                {"body": clean_body(body), "revision": row["revision"] + 1},
            )
            record_revision(tx, who, row)
            tx.conn.execute(
                revisions.update()
                .where(revisions.c.item_id == row["id"], revisions.c.revision == row["revision"])
                .values(label=text, sealed=True)
            )
            tx.emit(
                "note.edited",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"revision": row["revision"], "title": row["title"], "label": text},
            )
            return self._notes(tx, [row])[0]

    def restore(self, who: Principal, note_id: str, revision: int) -> Note:
        """Put an earlier version back, as a new sealed version (so it can be undone too)."""
        with self.rt.write() as tx:
            row = self._writable(tx, who, note_id)
            revisions = schema.context_item_revisions
            old = tx.first(
                sa.select(revisions).where(
                    revisions.c.item_id == note_id, revisions.c.revision == int(revision)
                )
            )
            if old is None:
                raise NotFound(f"No version {revision} of this note.")
            row = tx.update(
                schema.context_items,
                row,
                {"title": old["title"], "body": old["body"], "revision": row["revision"] + 1},
            )
            tx.insert(
                schema.context_item_revisions,
                {
                    "item_id": row["id"],
                    "revision": row["revision"],
                    "title": row["title"],
                    "body": row["body"],
                    "object_key": None,
                    "content_hash": None,
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                    "label": f"Restored version {revision}",
                    "sealed": True,
                },
            )
            tx.emit(
                "note.edited",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"revision": row["revision"], "title": row["title"], "restored": revision},
            )
            return self._notes(tx, [row])[0]

    def archive(self, who: Principal, note_id: str, archived: bool = True) -> Note:
        with self.rt.write() as tx:
            row = self._writable(tx, who, note_id)
            row = tx.update(
                schema.context_items, row, {"archived_at": tx.now if archived else None}
            )
            tx.emit(
                "note.archived" if archived else "note.restored",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"title": row["title"]},
            )
            return self._notes(tx, [row])[0]

    # ---------------------------------------------------------------- into the Brain

    def to_brain(
        self,
        who: Principal,
        note_id: str,
        *,
        project: str | None = None,
        status: str | None = None,
    ) -> BrainProposal:
        """File the note in the Brain as a document, as it reads now: in a project when one
        is named (a note filed before by the same name becomes its new version). The Brain's
        capture policy decides whether it is in at once or waits for review."""
        who.require("brain.propose")
        _person(who)
        copy = " ".join(str(status or "").split()).lower() or None
        if copy is not None and not STATUS.match(copy):
            raise ValidationFailed("A status is a word or two, such as draft or final.")
        note = self.get(who, note_id)
        if not note.body.strip():
            raise ValidationFailed("The note is empty: write something first.")
        # A document brought in is filed as itself, so the Brain keeps its shape (headings,
        # slides, pages); everything else is filed as the text it reads now.
        name, data = f"{_slug(note.title)}.md", f"# {note.title}\n\n{note.body.strip()}\n".encode()
        if note.capture == "document" and note.original:
            with self.rt.read() as tx:
                row = self._readable(tx, who, note_id)
                if row["object_key"] and self.rt.objects.exists(row["object_key"]):
                    name, data = row["filename"] or name, self.rt.objects.read(row["object_key"])
        filed = self.rt.brain.add_file(
            filename=name,
            data=data,
            title=note.title,
            description="",
            topic=None,
            proposer=f"{who.kind}:{who.name} ({who.actor_id})",
            project=str(project or "").strip() or None,
            status=copy,
            origin="app",
        )
        if filed.status == "refused":
            raise ValidationFailed(filed.message)
        with self.rt.write() as tx:
            tx.emit(
                "note.filed",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=note_id,
                data={
                    "title": note.title,
                    "status": filed.status,
                    "path": filed.path,
                    "project": filed.project,
                    "checkpoint": filed.checkpoint_id,
                },
            )
        return filed

    # ---------------------------------------------------------------- helpers

    def _row(self, tx: Tx, note_id: str) -> dict[str, Any]:
        row = tx.get(schema.context_items, str(note_id or ""))
        if row is None or row["workspace_id"] != self.rt.workspace_id or row["kind"] != KIND:
            raise NotFound(f"No note with id {note_id}.", id=note_id)
        return row

    def _readable(self, tx: Tx, who: Principal, note_id: str) -> dict[str, Any]:
        row = self._row(tx, note_id)
        who.require("context.read", _project(row))
        if not open_to(tx, who, row):
            raise NotFound(f"No note with id {note_id}.", id=note_id)
        return row

    def _writable(self, tx: Tx, who: Principal, note_id: str) -> dict[str, Any]:
        _person(who)
        row = self._row(tx, note_id)
        who.require("context.write", _project(row))
        return row

    def _current(self, tx: Tx, row: dict[str, Any]) -> dict[str, Any] | None:
        revisions = schema.context_item_revisions
        return tx.first(
            sa.select(revisions).where(
                revisions.c.item_id == row["id"], revisions.c.revision == row["revision"]
            )
        )

    def _versions(
        self, tx: Tx, row: dict[str, Any], *, with_body: bool
    ) -> builtins.list[NoteVersion]:
        revisions = schema.context_item_revisions
        rows = tx.rows(
            sa.select(revisions)
            .where(revisions.c.item_id == row["id"])
            .order_by(revisions.c.revision.desc())
        )
        names = _names(tx, {r["created_by"] for r in rows})
        return [
            NoteVersion(
                revision=r["revision"],
                title=r["title"],
                body=r["body"] if with_body else None,
                size=len(r["body"] or ""),
                by=names.get(r["created_by"]) or "Someone",
                at=r["created_at"],
                label=r["label"],
                sealed=bool(r["sealed"]),
                current=r["revision"] == row["revision"],
            )
            for r in rows
        ]

    def _notes(self, tx: Tx, rows: builtins.list[dict[str, Any]]) -> builtins.list[Note]:
        if not rows:
            return []
        revisions = schema.context_item_revisions
        current = {
            (r["item_id"], r["revision"]): r["created_by"]
            for r in tx.rows(
                sa.select(revisions.c.item_id, revisions.c.revision, revisions.c.created_by).where(
                    revisions.c.item_id.in_([r["id"] for r in rows])
                )
            )
        }
        names = _names(tx, set(current.values()))
        return [
            Note(
                id=row["id"],
                title=row["title"],
                body=row["body"],
                revision=row["revision"],
                version=row["version"],
                created_by=row["created_by"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                edited_by=names.get(current.get((row["id"], row["revision"])) or ""),
                archived_at=row["archived_at"],
                capture=_capture(row),
                original=_original(row),
                transcription=_transcription(row),
                digest=_digest(row),
                projects=_projects(row),
                url=row.get("url"),
            )
            for row in rows
        ]


def _project(row: dict[str, Any]) -> str | None:
    return row["scope_id"] if row["scope_kind"] == "project" else None


def project_labels(labels: builtins.list[str], projects: builtins.list[str]) -> builtins.list[str]:
    """A note's labels with its project links set to `projects` (other labels kept)."""
    wanted = list(dict.fromkeys(str(p).strip() for p in projects if str(p).strip()))
    if len(wanted) > MAX_PROJECTS:
        raise ValidationFailed(f"Link a note to at most {MAX_PROJECTS} projects.", field="projects")
    for project in wanted:
        if len(project) > 120 or not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$", project):
            raise ValidationFailed(f"{project!r} is not a project's id.", field="projects")
    kept = [str(label) for label in labels if not str(label).startswith(PROJECT_LABEL)]
    return sorted(set(kept + [PROJECT_LABEL + p for p in wanted]))


def _projects(row: dict[str, Any]) -> builtins.list[str]:
    return [
        str(label)[len(PROJECT_LABEL) :]
        for label in row.get("labels") or []
        if str(label).startswith(PROJECT_LABEL)
    ]


def _url(url: str) -> str:
    text = str(url or "").strip()
    if not re.match(r"^https?://\S+$", text) or len(text) > 2000:
        raise ValidationFailed("A link is an http:// or https:// address.", field="url")
    return text


def _capture(row: dict[str, Any]) -> str:
    kind = row.get("source_label")
    return str(kind) if kind in CAPTURE_KINDS else "note"


def _original(row: dict[str, Any]) -> dict[str, Any] | None:
    if not row.get("object_key"):
        return None
    return {
        "filename": row.get("filename") or "",
        "mime": row.get("mime") or "",
        "size": row.get("size") or 0,
    }


def _digest(row: dict[str, Any]) -> dict[str, Any] | None:
    """A capture's digest (summary, key points and how each fits the Brain), the request for
    one (`waiting` for a model), or `queued` when it will be asked for once its text is in."""
    provenance = row.get("provenance") or {}
    digest = provenance.get("digest")
    if digest:
        return dict(digest)
    if provenance.get("summarize") == "auto":
        return {"state": "queued"}
    return None


def _transcription(row: dict[str, Any]) -> dict[str, Any] | None:
    """How far a spoken capture's text is: pending, working (with its progress), ready, failed."""
    state = row.get("shadow_status")
    if _capture(row) not in SPOKEN or state not in TRANSCRIPTION_STATES:
        return None
    info = dict((row.get("provenance") or {}).get("transcription") or {})
    return {
        "state": state,
        "progress": float(info.get("progress") or (1.0 if state == "ready" else 0.0)),
        "duration": info.get("duration"),
        "error": info.get("error"),
    }


def _names(tx: Tx, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    actors = schema.actors
    return {
        r["id"]: r["name"]
        for r in tx.rows(sa.select(actors.c.id, actors.c.name).where(actors.c.id.in_(ids)))
    }
