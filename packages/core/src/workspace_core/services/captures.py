"""Captures: what a person brings into the app before any of it becomes Brain knowledge.

A capture is a note (services/notes.py): a Markdown page in the person's own space, private until
they act on it, with versions, "Add to the Brain" and "Find what to remember". It also says where
it came from (the item's `source_label`): spoken ("talk": dictated, seconds to minutes), recorded
("recording": a meeting or a talk in the room, or an audio file), a transcript made elsewhere
("transcript": Teams, Zoom or Otter exports) or a document ("document"). It keeps what was brought
in as its original, in the object store (never in the Brain's git).

Audio becomes text on this computer. The server's transcription worker claims the oldest capture
waiting for it (`shadow_status` pending), reports how far it got, and fills in the note's text
when it is done; until then the note is empty and cannot be edited.

Once its text is in, a model writes its digest (a `digest` task with the capture pinned): a
summary, its key points each marked by how it fits what the Brain holds now (new, repeats,
updates, clashes), decisions, actions, open questions, people. The digest is shown beside the
capture; nothing reaches the Brain until the person pulls something in ("Find what to
remember", with their own words for what to pull). With the setting on (the default), what is
brought in is summarized as it arrives.
"""

from __future__ import annotations

import builtins
import os
import re
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Task
from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed

from .context import open_to
from .distill import Distillation
from .notes import KIND, SPOKEN, Note, Notes, _person, clean_body, first_line
from .runtime import Runtime
from .tasks import Tasks

MAX_ORIGINAL = 500 * 1024 * 1024  # an hour of audio is well under this
AUDIO = (
    ".mp3",
    ".m4a",
    ".wav",
    ".webm",
    ".ogg",
    ".oga",
    ".opus",
    ".flac",
    ".aac",
    ".wma",
    ".mp4",
    ".m4v",
    ".mov",
)
TRANSCRIPT_FILES = (".vtt", ".srt")
PLAIN = (".txt", ".md", ".markdown")
TIMESTAMP = re.compile(r"\[?\b\d{1,2}:\d{2}(?::\d{2})?\b\]?")
# "Dana Ruiz: ...", "**Dana** [04:12] ...", "Dana (04:12):": a line that says who spoke
SPEAKER = re.compile(
    r"^\s*(?:\*\*)?[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3}(?:\*\*)?\s*"
    r"(?:\[[\d:]+\]|\(\d{1,2}:\d{2}(?::\d{2})?\)|\d{1,2}:\d{2}(?::\d{2})?)?\s*:",
    re.MULTILINE,
)
TALK_TITLE = "Talk"  # until its text is in: then its first line
BETWEEN_WORDS = re.compile(r"(?<!\d)-|-(?!\d)")  # a dash in a date stays
LABEL = "Transcribed on this computer"
DIGEST = "digest"
FITS = ("new", "repeats", "updates", "clashes")
RELATED_PARTS = 12  # a long transcript is read for related entries in this many places
RELATED_FLOOR = 0.45  # a search hit this relevant counts as related
SETTINGS_DEFAULTS: dict[str, Any] = {"summarize": True}
DIGEST_CONTRACT = {
    "artifacts": [],
    "notes": "One digest: call save_digest once with this run's run_id and the item's id. "
    "Nothing reaches the Brain from it; the person chooses what to pull in.",
    "tool": "save_digest",
}
DIGEST_INSTRUCTIONS = """\
Read the pinned item: something the person said, recorded or brought in (a talk, a meeting's \
transcript, a document). Write its digest for someone who was not there and wants the gist in a \
minute. Use only what the item says: no guesses and nothing from outside it. Leave out small \
talk. The person's goals for this Brain and their active projects are pinned too: they say \
what matters to this person.

- about: one line saying what it is mostly about, naming the goal or project it serves, for \
example "Mostly about: Q4 webinar series; the goal to stop dropping follow-ups".

- summary: two or three plain sentences: what it is and what came of it.
- points: its key points, at most ten, each one short plain sentence that stands on its own, \
the ones that matter to the Brain's goals and projects (quoted below, when it has them) first. \
For each, say how it fits what the Brain holds now. The Relevant context section shows some of \
it; search_context in your own words finds the rest, and get_brain_entry opens an entry. Mark \
it new (the Brain has nothing on it), repeats (an entry says the same; give its id as entry), \
updates (it changes or adds to an entry; give its id) or clashes (it contradicts an entry; give \
its id, and say what differs in why). In serves, name the project it moves forward, or "goals" \
when it serves what the Brain is for without one; leave it empty when it serves neither.
- decisions: what was decided, each in a sentence.
- actions: who will do what, by when, as said.
- questions: what was left open.
- people: who spoke or was named.
- new_project: when it is mostly about work that is not one of the active projects yet, a \
short name for that work; otherwise leave it out.
- off_goal: when it is mostly about a subject none of the goals or projects covers, that \
subject in two or three words; otherwise leave it out.

Call save_digest once with this run's run_id, the item's id and the digest, then complete the \
task. Do not propose Brain entries: the person chooses what to pull in."""


@dataclass(frozen=True)
class Claim:
    """A capture the transcription worker took: where its audio is on disk."""

    id: str
    kind: str
    path: str
    filename: str


def is_audio(filename: str, mime: str | None) -> bool:
    ext = os.path.splitext(str(filename or "").lower())[1]
    kind = str(mime or "").lower()
    return ext in AUDIO or kind.startswith("audio/") or kind.startswith("video/")


def looks_like_transcript(text: str) -> bool:
    """A text whose lines mostly carry times or say who spoke: a meeting's transcript."""
    lines = [line for line in str(text or "").splitlines() if line.strip()][:200]
    if len(lines) < 4:
        return False
    stamped = sum(1 for line in lines if TIMESTAMP.search(line))
    spoken = len(SPEAKER.findall("\n".join(lines)))
    return stamped >= 0.3 * len(lines) or spoken >= 0.3 * len(lines)


def _line(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def _lines(values: Any, count: int, limit: int = 400) -> list[str]:
    out = [_line(v, limit) for v in (values or []) if _line(v, limit)]
    return list(dict.fromkeys(out))[:count]


def _point(value: Any) -> dict[str, Any]:
    """One key point and how it fits the Brain: new, repeats, updates or clashes (an entry)."""
    data = value if isinstance(value, dict) else {"text": value}
    fit = str(data.get("fit") or "new").lower()
    point = {"text": _line(data.get("text"), 400), "fit": fit if fit in FITS else "new"}
    entry = _line(data.get("entry"), 160)
    if entry and point["fit"] != "new":
        point["entry"] = entry.removeprefix("brain:")
    why = _line(data.get("why"), 300)
    if why:
        point["why"] = why
    serves = _line(data.get("serves"), 80)
    if serves:
        point["serves"] = serves  # the project it moves forward, or "goals"
    return point


def _name(filename: str) -> str:
    """A title from a file name: no extension, spaces for underscores and for dashes between
    words ("weekly-sync_2026-10-05.vtt" is "weekly sync 2026-10-05")."""
    stem = os.path.splitext(os.path.basename(str(filename or "")))[0]
    return " ".join(BETWEEN_WORDS.sub(" ", stem.replace("_", " ")).split())[:200]


class Captures:
    def __init__(self, rt: Runtime, tasks: Tasks, distill: Distillation) -> None:
        self.rt = rt
        self.tasks = tasks
        self.distill = distill
        self.notes = Notes(rt)

    # ---------------------------------------------------------------- bringing in

    def bring_in(
        self,
        who: Principal,
        *,
        data: bytes,
        filename: str,
        mime: str | None = None,
        title: str = "",
        talk: bool = False,
    ) -> Note:
        """A file or a spoken clip, kept as the capture's original. Audio waits for its text;
        a transcript or a document becomes the note's text at once."""
        who.require("context.write")
        _person(who)
        if not data:
            raise ValidationFailed("That file is empty.")
        if len(data) > MAX_ORIGINAL:
            raise ValidationFailed(
                f"Keep a file under {MAX_ORIGINAL // (1024 * 1024)} MB; split a long recording."
            )
        name = os.path.basename(str(filename or "").replace("\\", "/")) or (
            "talk.webm" if talk else "upload"
        )
        body = ""
        if talk:
            kind = "talk"
        elif is_audio(name, mime):
            kind = "recording"
        else:
            text = self._text(data, name)
            if text is None:
                raise ValidationFailed(
                    f"{name} can't be read here. Bring in audio, a transcript (.vtt, .srt, "
                    ".txt, .docx) or a document (.pdf, .docx, .pptx, .md, .html)."
                )
            ext = os.path.splitext(name.lower())[1]
            kind = (
                "transcript"
                if ext in TRANSCRIPT_FILES or looks_like_transcript(text)
                else "document"
            )
            body = clean_body(text)
        stored = self.rt.objects.put(data)
        spoken = kind in SPOKEN
        with self.rt.read() as tx:
            summarize = bool(self._settings(tx)["summarize"])
        named = " ".join(str(title or "").split())[:300]
        if not named:
            generic = _name(name).lower() in ("", "talk", "recording", "upload", "audio")
            named = (
                TALK_TITLE
                if kind == "talk"
                else f"Recording, {self.rt.clock.now().isoformat()[:10]}"
                if generic
                else _name(name)
            )
        with self.rt.write() as tx:
            row = tx.insert(
                schema.context_items,
                {
                    "id": tx.new_id("ctx"),
                    "workspace_id": self.rt.workspace_id,
                    "scope_kind": "workspace",
                    "scope_id": None,
                    "kind": KIND,
                    "title": named,
                    "body": body,
                    "url": None,
                    "object_key": stored.key,
                    "filename": name,
                    "mime": mime or None,
                    "size": stored.size,
                    "content_hash": stored.key,
                    "text_shadow": None,
                    "shadow_status": "pending" if spoken else "none",
                    "idea_state": None,
                    "memory_state": None,
                    "labels": [],
                    "source_label": kind,
                    "revision": 1,
                    "last_referenced_at": None,
                    "provenance": {
                        "made_by": who.actor_id,
                        "capture": kind,
                        **({"transcription": {"progress": 0.0}} if spoken else {}),
                        # summarized once its text is in, when the setting says so
                        **({"summarize": "auto"} if summarize else {}),
                    },
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                    "updated_at": tx.now,
                    "version": 1,
                    "archived_at": None,
                },
            )
            self._revision(tx, row, who.actor_id, None)
            tx.emit(
                "capture.added",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={"title": row["title"], "kind": kind, "filename": name},
            )
            return self.notes._notes(tx, [row])[0]

    def _text(self, data: bytes, name: str) -> str | None:
        ext = os.path.splitext(name.lower())[1]
        if ext in PLAIN:
            text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
            if text.startswith("---\n"):
                end = text.find("\n---", 4)
                if end > 0:
                    text = text[end + 4 :]
            return text.strip() or None
        extractor = self.rt.extractor
        return extractor.markdown(data, name) if extractor is not None else None

    def original(self, who: Principal, capture_id: str) -> tuple[str, str, str]:
        """(filename, mime, path on disk) of what was brought in."""
        with self.rt.read() as tx:
            row = self._row(tx, capture_id)
            who.require("context.read")
            if not open_to(tx, who, row) or not row["object_key"]:
                raise NotFound("This note has no original.", id=capture_id)
            key = row["object_key"]
        if not self.rt.objects.exists(key):
            raise NotFound("The original is missing from the file store.", id=capture_id)
        return row["filename"] or "original", row["mime"] or "", self.rt.objects.path(key)

    def retry(self, who: Principal, capture_id: str) -> Note:
        """Try the transcription again after it failed."""
        _person(who)
        with self.rt.write() as tx:
            row = self._row(tx, capture_id)
            who.require("context.write")
            if row["shadow_status"] != "failed":
                raise Conflict("Only a transcription that failed can be tried again.")
            row = tx.update(
                schema.context_items,
                row,
                {
                    "shadow_status": "pending",
                    "provenance": self._info(row, progress=0.0, error=None),
                },
            )
            return self.notes._notes(tx, [row])[0]

    # ---------------------------------------------------------------- digests

    def settings(self, who: Principal) -> dict[str, Any]:
        who.require("context.read")
        with self.rt.read() as tx:
            return self._settings(tx)

    def configure(self, who: Principal, *, summarize: bool) -> dict[str, Any]:
        """Whether what is brought in is summarized as it arrives."""
        who.require("workspace.admin")
        with self.rt.write() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            current = {**self._settings(tx, row), "summarize": bool(summarize)}
            tx.update(
                schema.workspaces, row, {"settings": {**row["settings"], "captures": current}}
            )
            tx.emit(
                "captures.configured",
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=row["id"],
                data=dict(current),
            )
        return current

    def summarize(self, who: Principal, capture_id: str, *, guidance: str = "") -> Task:
        """Ask a model for the capture's digest. Without a model to name, the request waits
        for one (the local CLI takes it when it runs)."""
        who.require("tasks.write")
        with self.rt.read() as tx:
            row = self._row(tx, capture_id)
            if not open_to(tx, who, row):
                raise NotFound(f"No note with id {capture_id}.", id=capture_id)
            if row["archived_at"]:
                raise ValidationFailed("It is set aside: bring it back first.")
            text = str(row["body"] or "").strip()
            if not text:
                raise ValidationFailed("There is no text to summarize yet.")
            try:
                assignee: str | None = self.distill._default_assignee(tx)
            except ValidationFailed:
                assignee = None
        instructions = DIGEST_INSTRUCTIONS
        if str(guidance or "").strip():
            instructions += f"\n\nGuidance from {who.name}: {str(guidance).strip()}"
        task = self.tasks.create(
            who,
            title=f"Summarize “{row['title']}”",
            purpose="Write the digest shown beside what the person brought in.",
            instructions=instructions,
            assignee_id=assignee,
            schedule={"kind": "manual"},
            output_contract=DIGEST_CONTRACT,
            review_policy="auto",
            brain_request=f"{row['title']}. {text}"[:2000],
            template=DIGEST,
            provenance={"digest": {"item": row["id"], "waiting": assignee is None}},
        )
        self.tasks.pin(
            who, task.id, ref_type="context_item", ref_id=row["id"], version=row["revision"]
        )
        self.distill.pin_lens(who, task.id)
        with self.rt.write() as tx:
            row = self._row(tx, capture_id)
            provenance = dict(row["provenance"] or {})
            provenance["digest"] = {"task_id": task.id, "state": "waiting", "asked_at": tx.now}
            provenance.pop("summarize", None)
            tx.update(schema.context_items, row, {"provenance": provenance})
        return self.tasks.mark_ready(who, task.id) if assignee else task

    def save_digest(
        self,
        who: Principal,
        *,
        run_id: str,
        item_id: str,
        summary: str,
        points: list[dict[str, Any]] | None = None,
        decisions: list[str] | None = None,
        actions: list[str] | None = None,
        questions: list[str] | None = None,
        people: list[str] | None = None,
        about: str = "",
        new_project: str = "",
        off_goal: str = "",
    ) -> dict[str, Any]:
        """A model's digest of a capture its run reads, shown beside the capture: what it is
        mostly about (and which goal or project that serves), its key points (each with how it
        fits the Brain and what it serves), and two nudges: work that is not a project yet,
        and a subject none of the goals covers."""
        who.require("runs.write")
        digest = {
            "about": _line(about, 240),
            "new_project": _line(new_project, 80),
            "off_goal": _line(off_goal, 60),
            "summary": _line(summary, 1200),
            "points": [_point(p) for p in (points or [])[:12]],
            "decisions": _lines(decisions, 12),
            "actions": _lines(actions, 15),
            "questions": _lines(questions, 10),
            "people": _lines(people, 30, 120),
        }
        if not digest["summary"]:
            raise ValidationFailed("Write the summary: two or three sentences.", field="summary")
        with self.rt.write() as tx:
            run = tx.one(schema.task_runs, run_id, "run")
            if run["actor_id"] != who.actor_id:
                raise PermissionDenied("That run belongs to someone else.", run_id=run_id)
            task = tx.one(schema.tasks, run["task_id"], "task")
            if task["template"] != DIGEST:
                raise ValidationFailed("This run is not a digest.", run_id=run_id)
            pins = schema.task_pins
            pinned = tx.first(
                sa.select(pins).where(
                    pins.c.task_id == task["id"],
                    pins.c.ref_type == "context_item",
                    pins.c.ref_id == item_id,
                )
            )
            if pinned is None:
                raise NotFound("That item is not what this run reads.", id=item_id)
            row = self._row(tx, item_id)
            provenance = dict(row["provenance"] or {})
            provenance["digest"] = {
                **digest,
                "task_id": task["id"],
                "run_id": run_id,
                "state": "ready",
                "at": tx.now,
                "by": who.name,
                "revision": pinned["pinned_version"],
            }
            tx.update(schema.context_items, row, {"provenance": provenance})
            tx.emit(
                "capture.summarized",
                actor_id=who.actor_id,
                subject_type="context_item",
                subject_id=row["id"],
                data={
                    "title": row["title"],
                    "points": len(digest["points"]),
                    "task_id": task["id"],
                },
            )
        return provenance["digest"]

    def related(
        self, who: Principal, capture_id: str, *, limit: int = 6
    ) -> builtins.list[dict[str, Any]]:
        """What the Brain already holds that the capture touches, found by meaning part by
        part (a long transcript covers many subjects): shown at once, before any digest."""
        with self.rt.read() as tx:
            row = self._row(tx, capture_id)
            who.require("context.read")
            if not open_to(tx, who, row):
                raise NotFound(f"No note with id {capture_id}.", id=capture_id)
        words = str(row["body"] or "").split()
        if len(words) < 3:
            return []
        size = 120
        parts = [" ".join(words[i : i + size]) for i in range(0, len(words), size)]
        if len(parts) > RELATED_PARTS:  # spread over the whole text, not its start alone
            step = len(parts) / RELATED_PARTS
            parts = [parts[int(i * step)] for i in range(RELATED_PARTS)]
        best: dict[str, dict[str, Any]] = {}
        for part in parts:
            for hit in self.rt.brain.search(part, limit=3):
                if hit.score < RELATED_FLOOR:
                    continue
                known = best.get(hit.id)
                if known is None or hit.score > known["score"]:
                    best[hit.id] = {
                        "id": hit.id,
                        "title": hit.title,
                        "summary": hit.summary,
                        "topic": hit.kind,
                        "score": round(hit.score, 3),
                    }
        return sorted(best.values(), key=lambda h: -h["score"])[:limit]

    def to_summarize(self, limit: int = 20) -> builtins.list[str]:
        """Captures brought in with summaries on whose text is in and which have no digest
        asked for yet, oldest first: the digest worker's queue."""
        table = schema.context_items
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table)
                .where(
                    table.c.workspace_id == self.rt.workspace_id,
                    table.c.kind == KIND,
                    table.c.archived_at.is_(None),
                    table.c.shadow_status.in_(("none", "ready")),
                )
                # ids count up in creation order, so two made in one moment keep theirs
                .order_by(table.c.created_at.desc(), table.c.id.desc())
                .limit(200)
            )
        waiting = [
            r["id"]
            for r in rows
            if (r["provenance"] or {}).get("summarize") == "auto"
            and not (r["provenance"] or {}).get("digest")
            and str(r["body"] or "").strip()
        ]
        return list(reversed(waiting))[:limit]

    # ---------------------------------------------------------------- the transcription worker

    def claim(self) -> Claim | None:
        """The oldest capture waiting for its text, now being transcribed."""
        table = schema.context_items
        with self.rt.write() as tx:
            row = tx.first(
                sa.select(table)
                .where(
                    table.c.workspace_id == self.rt.workspace_id,
                    table.c.kind == KIND,
                    table.c.shadow_status == "pending",
                    table.c.archived_at.is_(None),
                )
                .order_by(table.c.created_at, table.c.id)
                .limit(1)
            )
            if row is None:
                return None
            if not row["object_key"] or not self.rt.objects.exists(row["object_key"]):
                self._fail(tx, row, "The recording is missing from the file store.")
                return None
            row = tx.update(
                table,
                row,
                {
                    "shadow_status": "working",
                    "provenance": self._info(row, progress=0.0, started_at=tx.now, error=None),
                },
            )
            return Claim(
                id=row["id"],
                kind=str(row["source_label"] or "recording"),
                path=self.rt.objects.path(row["object_key"]),
                filename=row["filename"] or "",
            )

    def progress(self, capture_id: str, fraction: float) -> None:
        with self.rt.write() as tx:
            row = tx.get(schema.context_items, capture_id)
            if row is None or row["shadow_status"] != "working":
                return
            done = round(max(0.0, min(1.0, float(fraction))), 3)
            tx.update(schema.context_items, row, {"provenance": self._info(row, progress=done)})

    def transcribed(self, capture_id: str, *, text: str, duration: float, model: str) -> None:
        """The text is in: it becomes the note's text (a talk's first line its title)."""
        with self.rt.write() as tx:
            row = tx.get(schema.context_items, capture_id)
            if row is None or row["shadow_status"] != "working":
                return  # set aside or retried meanwhile
            body = clean_body(text).strip()
            changes: dict[str, Any] = {
                "shadow_status": "ready",
                "provenance": self._info(
                    row,
                    progress=1.0,
                    duration=round(float(duration), 1),
                    model=model,
                    finished_at=tx.now,
                ),
                "revision": row["revision"] + 1,
            }
            if not str(row["body"] or "").strip():
                changes["body"] = body
            if row["source_label"] == "talk" and row["title"] == TALK_TITLE and body:
                changes["title"] = first_line(body) or TALK_TITLE
            row = tx.update(schema.context_items, row, changes)
            self._revision(tx, row, row["created_by"], LABEL)
            tx.emit(
                "capture.transcribed",
                actor_id=row["created_by"],
                subject_type="context_item",
                subject_id=row["id"],
                data={"title": row["title"], "kind": row["source_label"], "duration": duration},
            )

    def failed(self, capture_id: str, error: str) -> None:
        with self.rt.write() as tx:
            row = tx.get(schema.context_items, capture_id)
            if row is None or row["shadow_status"] != "working":
                return
            self._fail(tx, row, error)

    def requeue(self) -> int:
        """Captures a stopped server left half transcribed wait again: done on start."""
        table = schema.context_items
        with self.rt.write() as tx:
            rows = tx.rows(
                sa.select(table).where(
                    table.c.workspace_id == self.rt.workspace_id,
                    table.c.kind == KIND,
                    table.c.shadow_status == "working",
                )
            )
            for row in rows:
                tx.update(
                    table,
                    row,
                    {"shadow_status": "pending", "provenance": self._info(row, progress=0.0)},
                )
            return len(rows)

    # ---------------------------------------------------------------- helpers

    def _settings(self, tx: Tx, row: dict[str, Any] | None = None) -> dict[str, Any]:
        row = row or tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        stored = dict((row["settings"] or {}).get("captures") or {})
        return {**SETTINGS_DEFAULTS, **{k: v for k, v in stored.items() if k in SETTINGS_DEFAULTS}}

    def _row(self, tx: Tx, capture_id: str) -> dict[str, Any]:
        row = tx.get(schema.context_items, str(capture_id or ""))
        if row is None or row["workspace_id"] != self.rt.workspace_id or row["kind"] != KIND:
            raise NotFound(f"No note with id {capture_id}.", id=capture_id)
        return row

    def _info(self, row: dict[str, Any], **changes: Any) -> dict[str, Any]:
        """The item's provenance with its transcription details changed."""
        provenance = dict(row["provenance"] or {})
        info = dict(provenance.get("transcription") or {})
        info.update(changes)
        provenance["transcription"] = info
        return provenance

    def _fail(self, tx: Tx, row: dict[str, Any], error: str) -> None:
        message = " ".join(str(error or "The transcription failed.").split())[:500]
        tx.update(
            schema.context_items,
            row,
            {"shadow_status": "failed", "provenance": self._info(row, error=message)},
        )
        tx.emit(
            "capture.failed",
            actor_id=row["created_by"],
            subject_type="context_item",
            subject_id=row["id"],
            data={"title": row["title"], "error": message},
        )

    def _revision(self, tx: Tx, row: dict[str, Any], by: str, label: str | None) -> None:
        tx.insert(
            schema.context_item_revisions,
            {
                "item_id": row["id"],
                "revision": row["revision"],
                "title": row["title"],
                "body": row["body"],
                "object_key": row["object_key"],
                "content_hash": row["content_hash"],
                "created_by": by,
                "created_at": tx.now,
                **({"label": label, "sealed": True} if label else {}),
            },
        )
