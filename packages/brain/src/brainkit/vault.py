"""The vault on disk: read it into a `Snapshot`, and write the few files a brain changes.

Layout (every path relative to the vault root):

    brain.json  topics.md  routing.json  aliases.json      declared shape and policy
    knowledge/<area>/<topic>/<added>-<note id>.md         governed notes (scope is in the
                                                          front matter, not the path)
    knowledge/<scope path>/<layer>/<topic>/<note id>.md   the same, in older vaults
    skills/<category>/<name>/SKILL.md                     procedures (plus their assets)
    references/**.md                                      long source documents
    inbox/<proposal id>.md                                pending proposals
    journal/focus/<focus id>.jsonl                        append-only Focus updates
    journal/decisions.jsonl                               governance decisions
    journal/sessions/*.md                                 optional session receipts

Folders named `private`, or starting with `.` or `_`, are never read. Files starting with `_`
(generated topic maps, READMEs) are not notes.
"""
from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass, field

from . import frontmatter as fm
from . import util
from .model import FocusUpdate, Note, Proposal, Reference, Skill

CONFIG_FILES = ("brain.json", "topics.md", "routing.json", "aliases.json",
                os.path.join("skills", "CATEGORIES.md"))
NOTE_KEY_ORDER = (
    "id", "title", "summary", "area", "layer", "topic", "kind", "scope", "partition", "status",
    "load", "startup_text", "index_line", "added", "updated", "revised", "source", "origin",
    "evidence", "supersedes", "owner", "review_by", "review_days", "verified", "confidence",
    "stale", "classification",
)


def _skip_dir(name: str) -> bool:
    return name.startswith((".", "_")) or name in ("private", "__pycache__", "node_modules")


@dataclass
class Snapshot:
    fingerprint: str
    notes: dict = field(default_factory=dict)          # id -> Note
    skills: dict = field(default_factory=dict)         # name -> Skill
    references: dict = field(default_factory=dict)     # path -> Reference
    focus_updates: dict = field(default_factory=dict)  # focus id -> [FocusUpdate]
    proposals: dict = field(default_factory=dict)      # id -> Proposal
    problems: list = field(default_factory=list)       # (path, message)


class Vault:
    """File access for one vault. Parsed files are cached by (mtime, size)."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self._cache: dict = {}
        self._lock = threading.Lock()
        # The undo point being recorded (checkpoints.batch), if any: every change below
        # reports the file first, so the batch keeps what it held before.
        self.recording = None
        self.writes = 0  # changes made through this object, so a batch knows when to re-read

    def touch(self, path) -> None:
        """Say a file (or every file in a folder) is about to change or go."""
        self.writes += 1
        # A fast same-size edit or undo can keep the same filesystem timestamp.
        # Known writes invalidate parsed content even when its stat key is unchanged.
        target = os.path.normcase(os.path.abspath(path))
        prefix = target + os.sep
        with self._lock:
            for cached in list(self._cache):
                key = os.path.normcase(os.path.abspath(cached))
                if key == target or key.startswith(prefix):
                    self._cache.pop(cached)
        if self.recording is not None:
            self.recording.capture(path)

    # ------------------------------------------------------------------ paths
    def path(self, *parts) -> str:
        return os.path.join(self.root, *parts)

    @property
    def runtime_dir(self) -> str:
        folder = self.path(".brain")
        os.makedirs(folder, exist_ok=True)
        return folder

    def _entries(self, base, suffix=".md", max_depth=None, name=None):
        """(vault-relative path, mtime_ns, size) of matching files under `base`, sorted.

        Built on os.scandir, whose entries carry size and modification time from the
        directory listing itself on Windows, so a fingerprint costs one listing per folder
        rather than one stat per file. `max_depth` bounds how many folders deep it looks
        (skills keep SKILL.md two levels down; their templates and assets never matter)."""
        top = self.path(base)
        out = []

        def visit(folder, rel, depth):
            try:
                with os.scandir(folder) as listing:
                    entries = sorted(listing, key=lambda e: e.name)
            except OSError:
                return
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if not _skip_dir(entry.name) and (max_depth is None or depth < max_depth):
                        visit(entry.path, f"{rel}/{entry.name}", depth + 1)
                elif entry.name.endswith(suffix) and (name is None or entry.name == name):
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    out.append((f"{rel}/{entry.name}", stat.st_mtime_ns, stat.st_size))

        if os.path.isdir(top):
            visit(top, base.replace(os.sep, "/"), 0)
        return out

    def _walk(self, base, suffix=".md", max_depth=None, name=None):
        for relpath, _mtime, _size in self._entries(base, suffix, max_depth, name):
            yield self.path(*relpath.split("/"))

    def _content_entries(self):
        """Every file whose change can change what the brain knows or how it routes."""
        out = []
        for name in CONFIG_FILES:
            try:
                stat = os.stat(self.path(name))
            except OSError:
                continue
            out.append((name.replace(os.sep, "/"), stat.st_mtime_ns, stat.st_size))
        out += self._entries("knowledge")
        out += self._entries("skills", max_depth=2, name="SKILL.md")
        out += self._entries("references")
        out += self._entries("inbox")
        out += self._entries("journal/focus", ".jsonl")
        return out

    def content_files(self):
        for relpath, _mtime, _size in self._content_entries():
            yield self.path(*relpath.split("/"))

    def listing(self) -> list:
        """Every content file as (vault-relative path, mtime_ns, size), from one walk. A
        fingerprint and a scan can share it, so reading the vault walks it once."""
        return self._content_entries()

    def fingerprint(self, listing=None) -> str:
        digest = hashlib.sha256()
        for relpath, mtime, size in (self._content_entries() if listing is None else listing):
            digest.update(f"{relpath}|{mtime}|{size}\n".encode("utf-8"))
        return digest.hexdigest()

    def _cached(self, path, parse, key=None):
        if key is None:
            try:
                stat = os.stat(path)
            except OSError:
                return None
            key = (stat.st_mtime_ns, stat.st_size)
        hit = self._cache.get(path)
        if hit and hit[0] == key:
            return hit[1]
        try:
            value = parse(path)
        except FileNotFoundError:  # gone since the listing was taken
            return None
        self._cache[path] = (key, value)
        return value

    # ------------------------------------------------------------------ reading
    def _parse_note(self, path):
        meta, body, errors = fm.parse(util.read_text(path))
        return meta, body.strip("\n"), errors

    def _parse_skill(self, path):
        meta, body, errors = fm.parse(util.read_text(path))
        return meta, body.strip("\n"), errors

    def scan(self, listing=None) -> Snapshot:
        with self._lock:
            return self._scan(self._content_entries() if listing is None else listing)

    def _scan(self, listing) -> Snapshot:
        snap = Snapshot(fingerprint=self.fingerprint(listing))
        keys = {}

        def walk(base, suffix=".md"):
            prefix = base + "/"
            for relpath, mtime, size in listing:
                if relpath.startswith(prefix) and relpath.endswith(suffix):
                    path = self.path(*relpath.split("/"))
                    keys[path] = (mtime, size)
                    yield path

        for path in walk("knowledge"):
            if os.path.basename(path).startswith("_"):
                continue
            parsed = self._cached(path, self._parse_note, keys[path])
            if parsed is None:
                continue
            meta, body, errors = parsed
            relpath = util.rel(path, self.root)
            for message in errors:
                snap.problems.append((relpath, message))
            note_id = str(meta.get("id") or "").strip()
            if not note_id:
                snap.problems.append((relpath, "note has no id"))
                continue
            if note_id in snap.notes:
                snap.problems.append((relpath, f"duplicate note id {note_id} "
                                               f"(also {snap.notes[note_id].path})"))
                continue
            area = str(meta.get("area") or meta.get("layer") or "").strip()
            topic = str(meta.get("topic") or area).strip()
            if not area:
                snap.problems.append((relpath, f"note {note_id} has no area"))
                continue
            snap.notes[note_id] = Note(
                id=note_id, area=area, topic=topic,
                scope=str(meta.get("scope") or "company").strip(),
                status=str(meta.get("status") or "approved").strip().lower(),
                load=str(meta.get("load") or "on-demand").strip().lower(),
                body=body, path=relpath, meta=meta)
        for path in walk("skills", "/SKILL.md"):
            parsed = self._cached(path, self._parse_skill, keys[path])
            if parsed is None:
                continue
            meta, body, errors = parsed
            relpath = util.rel(path, self.root)
            for message in errors:
                snap.problems.append((relpath, message))
            parts = relpath.split("/")
            folder_name = parts[-2]
            category = parts[1] if len(parts) >= 4 else ""
            name = str(meta.get("name") or folder_name).strip()
            if name in snap.skills:
                snap.problems.append((relpath, f"duplicate skill name {name}"))
                continue
            snap.skills[name] = Skill(
                name=name, category=category,
                scope=str(meta.get("scope") or "company").strip(),
                body=body, path=relpath, meta=meta)
        for path in walk("references"):
            relpath = util.rel(path, self.root)
            body = self._cached(path, util.read_text, keys[path])
            snap.references[relpath] = Reference(path=relpath, body=body or "")
        for path in walk("journal/focus", ".jsonl"):
            focus_id = os.path.basename(path)[:-len(".jsonl")]
            rows = self._cached(path, util.read_jsonl, keys[path]) or []
            updates = []
            for index, row in enumerate(rows, 1):
                updates.append(FocusUpdate(
                    seq=int(row.get("seq") or index), at=str(row.get("at") or ""),
                    summary=str(row.get("summary") or ""),
                    changes=dict(row.get("changes") or {}),
                    evidence=str(row.get("evidence") or ""),
                    session=str(row.get("session") or ""),
                    actor=str(row.get("actor") or "")))
            updates.sort(key=lambda u: (u.at, u.seq))
            snap.focus_updates[focus_id] = updates
        for path in walk("inbox"):
            relpath = util.rel(path, self.root)
            if os.path.basename(path).lower() == "readme.md" or "/skills/" in relpath:
                continue
            proposal = self._cached(path, self._parse_proposal, keys[path])
            if proposal is not None:
                proposal.path = relpath
                snap.proposals[proposal.id] = proposal
        return snap

    def _parse_proposal(self, path):
        meta, body, _errors = fm.parse(util.read_text(path))
        if not meta.get("proposal"):
            return None
        header = {k[len("proposal_"):]: v for k, v in meta.items() if k.startswith("proposal_")}
        header["id"] = str(meta.get("proposal"))
        target = {k: v for k, v in meta.items()
                  if k != "proposal" and not k.startswith("proposal_")}
        return Proposal(id=header["id"], kind=str(header.get("kind") or "note.create"),
                        scope=str(target.get("scope") or header.get("scope") or "company"),
                        meta=header, target=target, body=body.strip("\n"), path="")

    # ------------------------------------------------------------------ writing
    def scope_path(self, scope: str, levels: list) -> str:
        """`company` -> ``, `dept:marketing` -> `departments/marketing`."""
        scope = str(scope or "").strip()
        for level in levels:
            prefix = level.get("prefix") or ""
            if prefix and scope.startswith(prefix):
                return f"{level.get('container') or level['kind']}/{scope[len(prefix):]}"
        return ""

    def note_path(self, meta: dict, levels: list, partitions: list | None = None) -> str:
        """Where a new note is written.

        Area layout: `knowledge/<area>/<topic>/<added>-<id>.md`, so a folder reads as a dated
        list of what each note is for. Scope lives in the front matter. Older vaults: the
        scope path, then `<layer>/<topic>/<id>.md`. A sealed partition keeps its own folder
        in both, so it can be moved or removed as a unit.
        """
        parts = ["knowledge"]
        dated = bool(meta.get("area"))
        partition = str(meta.get("partition") or "").strip()
        if partition:
            for kind in partitions or []:
                prefix = kind.get("prefix") or ""
                if prefix and partition.startswith(prefix):
                    parts += [kind.get("container") or kind["kind"], partition[len(prefix):]]
                    break
        elif not dated:
            base = self.scope_path(str(meta.get("scope") or "company"), levels)
            if base:
                parts += base.split("/")
        area = str(meta.get("area") or meta["layer"])
        topic = str(meta.get("topic") or area)
        parts.append(area)
        if topic != area:
            parts.append(topic)
        added = str(meta.get("added") or "")[:10]
        parts.append(f"{added}-{meta['id']}.md" if dated and added else f"{meta['id']}.md")
        return "/".join(parts)

    def write_note(self, relpath: str, meta: dict, body: str) -> str:
        self.touch(self.path(relpath))
        util.atomic_write(self.path(relpath), fm.dump(meta, body.strip() + "\n",
                                                      order=NOTE_KEY_ORDER))
        return relpath

    def file_hash(self, relpath: str) -> str | None:
        """The hash of a file's text as it is on disk (line ends read as LF), which the
        journal records after each change so history can match the change to its commit."""
        try:
            with open(self.path(*relpath.split("/")), "rb") as handle:
                data = handle.read()
        except OSError:
            return None
        return util.sha256(data.decode("utf-8", "replace").replace("\r\n", "\n"))

    def write_proposal(self, proposal_id: str, header: dict, target: dict, body: str) -> str:
        relpath = f"inbox/{proposal_id}.md"
        meta = {"proposal": proposal_id}
        meta.update({f"proposal_{k}": v for k, v in header.items() if v not in (None, "")})
        meta.update({k: v for k, v in target.items() if v not in (None, "")})
        order = ["proposal", "proposal_kind", "proposal_status", "proposal_created",
                 "proposal_proposer", "proposal_reason"] + list(NOTE_KEY_ORDER)
        self.touch(self.path(relpath))
        util.atomic_write(self.path(relpath), fm.dump(meta, body.strip() + "\n", order=order))
        return relpath

    def remove_file(self, relpath: str) -> None:
        self.touch(self.path(relpath))
        try:
            os.remove(self.path(relpath))
        except FileNotFoundError:
            pass

    def append_focus_update(self, focus_id: str, record: dict) -> str:
        relpath = f"journal/focus/{focus_id}.jsonl"
        util.append_jsonl(self.path(relpath), record)
        return relpath

    def append_goal_entry(self, goal_id: str, record: dict) -> str:
        """A line in a goal's journal: a check-in, an agent's progress note, a decision."""
        relpath = f"journal/goals/{goal_id}.jsonl"
        self.touch(self.path(relpath))
        util.append_jsonl(self.path(relpath), record)
        return relpath

    def goal_journal(self, goal_id: str) -> list[dict]:
        return util.read_jsonl(self.path("journal", "goals", f"{goal_id}.jsonl"))

    def write_goal_plan(self, goal_id: str, text: str) -> str:
        """A goal's shared plan (`goals/<id>/plan.md`): generated from the board's shared
        blocks, rewritten on save. Empty text removes it."""
        relpath = f"goals/{goal_id}/plan.md"
        if not text.strip():
            self.remove_file(relpath)
            return relpath
        self.touch(self.path(relpath))
        os.makedirs(os.path.dirname(self.path(relpath)), exist_ok=True)
        util.atomic_write(self.path(relpath), text.strip() + "\n")
        return relpath

    def goal_plan(self, goal_id: str) -> str:
        try:
            with open(self.path("goals", goal_id, "plan.md"), encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError:
            return ""

    def append_decision(self, record: dict) -> str:
        relpath = "journal/decisions.jsonl"
        util.append_jsonl(self.path(relpath), record)
        return relpath

    def decisions(self) -> list[dict]:
        return util.read_jsonl(self.path("journal", "decisions.jsonl"))
