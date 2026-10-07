"""BrainPort, implemented with the `brainkit` engine (packages/brain).

The workspace reads the Brain as its owner and proposes into it with `force_pending`, so every
proposal made from the workspace, by a model or by a person, waits for an explicit approval:
no proposal changes long-term context on its own (V1 acceptance).
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
import threading
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from brainkit import util as brain_util
from brainkit.api import Brain, Result
from brainkit.governance import summary_from
from brainkit.scopes import Scopes
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

# Sections of a Brain packet that serve a chat session rather than a workspace task: how to
# call the Brain's own tools, session continuity, capture nudges, and an echo of the request.
SESSION_SECTIONS = (
    "Start",
    "Working with the brain",
    "Capture",
    "Continuity",
    "Task",
    "Skills",
    "Next",
)
RETITLE = {"Startup context": "# Standing context", "Task context": "# Relevant context"}
WORKSPACE_SOURCE = "contxt, proposed by "
SOURCE_LABELS = (WORKSPACE_SOURCE, "workspace, proposed by ")  # the earlier label too
RELATED = re.compile(r"\bbrain:([A-Za-z0-9][A-Za-z0-9_.-]*[A-Za-z0-9])")
TOOL_NAMES = {"search_notes": "search_context", "get_note": "get_brain_entry"}
# Decisions about a live (or archived) entry rather than a waiting proposal.
ENTRY_ACTIONS = ("archive", "edit", "restore", "unarchive", "update", "verify", "mark")


def workspace_view(text: str) -> str:
    """The Brain's knowledge for a task packet, without its chat-session plumbing."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if line.startswith("# "):
            skipping = False
            heading = line[2:].split(" (", 1)[0].strip()
            out.append(RETITLE.get(heading, line))
            continue
        if line.startswith("## "):
            skipping = line[3:].strip() in SESSION_SECTIONS
            if skipping:
                continue
        if not skipping:
            out.append(line)
    view = "\n".join(out)
    for old, new in TOOL_NAMES.items():
        view = view.replace(old, new)
    view = re.sub(r"(## Skill candidates\n(?:.*\n)*?)(?=\n## |\n# |\Z)", _skill_hint, view)
    view = re.sub(r"\n{3,}", "\n\n", view)
    return view.strip() + "\n"


def _skill_hint(match: re.Match[str]) -> str:
    return (
        match.group(1).rstrip("\n") + "\n\nOpen a procedure with "
        'get_brain_skill(name="...") when the task follows it.\n'
    )


KIND_MAP = {
    "fact": "fact",
    "rule": "rule",
    "preference": "fact",
    "decision": "fact",
    "procedure": "rule",
    "identity": "identity",
    "state": "state",
}

# The folders the workspace serves files from. Notes are read through entries; the inbox,
# the runtime folder and the configuration are never served.
SERVED = ("references", "assets", "skills")
FILED = re.compile(r"\b((?:references|assets)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)")
SOURCE = re.compile(r"^> Source: `([^`]+)`, sha256 `([0-9a-f]{64})`", re.MULTILINE)
ASSET_TITLE = re.compile(r"^Asset: (.+?) \(")
# Named here rather than left to the platform's MIME table, which differs between Windows and
# the Linux container (and knows neither fonts nor webp on some machines).
KNOWN_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".dotx": "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".potx": "application/vnd.openxmlformats-officedocument.presentationml.template",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xltx": "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
}


def clean_path(path: str) -> str | None:
    """A path inside one of the served folders, or None for anything else."""
    text = str(path or "").replace("\\", "/").strip()
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return None
    parts = text.split("/")
    if parts[0] not in SERVED or len(parts) < 2:
        return None
    if any(part in ("", ".", "..") or part.startswith(".") for part in parts):
        return None
    return "/".join(parts)


def mime_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return KNOWN_TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def modified(path: str) -> str | None:
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    return datetime.fromtimestamp(stamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def excerpt(text: str, limit: int = 180) -> str:
    """The first line of prose, as plain text: not a heading, quote, table or front matter."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", ">", "---", "|", "```", "<!--")):
            line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)  # [text](link) -> text
            line = re.sub(r"\*\*|__|`", "", line).strip()
            return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"
    return ""


class BrainKitAdapter:
    def __init__(
        self, vault: str, *, embeddings: bool = False, principal: str | None = None
    ) -> None:
        if not os.path.isfile(os.path.join(vault, "brain.json")):
            raise FileNotFoundError(f"No brain.json in {vault}: not a Brain vault.")
        self.vault = os.path.abspath(vault)
        # Models only from the Brain's own folder: a server never downloads one by itself.
        self.brain = Brain(
            self.vault, principal=principal, embeddings=embeddings, local_models=True
        )
        self._lock = threading.Lock()

    def close(self) -> None:
        self.brain.close()

    # ---------------------------------------------------------------- reads

    def status(self) -> dict[str, Any]:
        st = self.brain.state()
        pending = len(st.snapshot.proposals)
        return {
            "available": True,
            "name": st.config.name,
            "vault": self.vault,
            "principal": self.brain.principal(),
            "notes": len(st.index.notes),
            "pending_proposals": pending,
        }

    def context(self, request: str, *, session_id: str | None = None) -> BrainContext:
        with self._lock:
            result = self.brain.context(
                request, session_id=session_id, record=False, include_kernel=True
            )
        if result.is_error:
            return BrainContext(available=True, reason=result.text)
        data = result.data
        ids = list(
            dict.fromkeys(list(data.get("standing_ids") or []) + list(data.get("note_ids") or []))
        )
        index = self.brain.state().index
        entries = [
            {"id": note.id, "hash": note.body_hash, "tokens": note.tokens}
            for note in (index.note(i) for i in ids)
            if note is not None
        ]
        return BrainContext(
            available=True,
            text=workspace_view(result.text),
            entry_ids=ids,
            entries=entries,
            data={
                k: data.get(k)
                for k in (
                    "mode",
                    "topics",
                    "skill_id",
                    "focus_id",
                    "related_ids",
                    "reference_paths",
                    "kernel_fingerprint",
                    "vault_fingerprint",
                )
            },
        )

    def search(self, query: str, limit: int = 10) -> list[BrainHit]:
        result = self.brain.search(query, limit=limit)
        return [
            BrainHit(
                id=h["id"],
                title=h.get("title") or h["id"],
                summary=h.get("summary") or "",
                scope=h.get("scope") or "",
                kind=h.get("route_key") or "",
                score=float(h.get("score") or 0),
            )
            for h in result.data.get("hits", [])
        ]

    def entry(self, entry_id: str) -> BrainEntry | None:
        # A note sealed to a partition (a client, say) opens within that partition, which
        # the owner owns.
        note = self.brain.state().index.note(entry_id)
        result = self.brain.note(entry_id, partition=note.partition if note else None)
        if result.is_error:
            return None
        data, meta = result.data, result.data.get("meta") or {}
        return BrainEntry(
            id=data["id"],
            title=data.get("title") or data["id"],
            text=data.get("body") or "",
            scope=str(meta.get("scope") or ""),
            kind=str(data.get("kind") or ""),
            status=str(meta.get("status") or ""),
            revision=_revision(meta),
            summary=data.get("summary") or "",
            confidence=data.get("confidence"),
            verified=data.get("verified") or None,
            stale=bool(data.get("stale")),
            stale_reason=data.get("stale"),
            source=meta.get("source"),
            path=data.get("path"),
        )

    def verify(self, entry_id: str, *, confidence: str | None = None) -> BrainEntry:
        with self._lock:
            result = self.brain.verify(entry_id, confidence=confidence)
        return self._after_freshness(entry_id, result)

    def mark(self, entry_id: str, state: str, *, reason: str) -> BrainEntry:
        with self._lock:
            result = self.brain.mark(entry_id, state, reason=reason)
        return self._after_freshness(entry_id, result)

    def _after_freshness(self, entry_id: str, result: Any) -> BrainEntry:
        if result.is_error:
            status = result.data.get("status")
            if status == "missing":
                raise NotFound(result.text)
            if status == "invalid":
                raise ValidationFailed(result.text)
            raise Conflict(result.text)
        entry = self.entry(entry_id)
        if entry is None:
            raise NotFound(f"No Brain entry {entry_id}.")
        return entry

    def skill(self, name: str) -> BrainDocument | None:
        result = self.brain.skill(name.lstrip("/"))
        if result.is_error:
            return None
        return BrainDocument(
            kind="skill",
            name=name.lstrip("/"),
            text=result.text,
            loads=[str(item) for item in result.data.get("loads") or []],
        )

    def reference(self, path: str) -> BrainDocument | None:
        result = self.brain.reference(path)
        if result.is_error:
            return None
        return BrainDocument(kind="reference", name=path, text=result.text)

    # ---------------------------------------------------------------- browsing

    def _view(self, st: Any) -> tuple[list[str], list[str]]:
        """What the owner sees: their scope chain, and every partition they own."""
        caller = self.brain.caller(st=st)
        if isinstance(caller, Result):
            return [], []
        chain = list(caller[0])
        owned = {
            name
            for partition in st.scopes.partitions
            for name in (st.scopes.partition_chain(partition, chain) or [])
        }
        return chain, sorted(owned)

    def _visible_notes(self, st: Any) -> list[Any]:
        chain, partitions = self._view(st)
        return [
            n
            for n in st.index.notes.values()
            if Scopes.admits(n.scope, n.partition, chain, partitions)
        ]

    def _filed(self, body: str) -> str | None:
        """The reference or asset a pointer note points at, when it exists."""
        for match in FILED.finditer(body or ""):
            path = match.group(1).rstrip(".")
            if os.path.isfile(self.brain.vault.path(*path.split("/"))):
                return path
        return None

    def catalog(self) -> BrainCatalog:
        st = self.brain.state()
        config = st.config
        today = brain_util.now().date()
        order = {area: i for i, area in enumerate(config.area_order())}
        notes = sorted(
            self._visible_notes(st),
            key=lambda n: (order.get(n.area, 99), n.route_key, not n.standing, n.title.lower()),
        )
        entries = [
            BrainEntrySummary(
                id=n.id,
                title=n.title,
                summary=n.summary,
                area=n.area,
                topic=n.route_key,
                kind=n.kind,
                scope=n.scope,
                partition=n.partition,
                added=n.added or None,
                verified=n.verified or None,
                confidence=n.confidence,
                stale_reason=n.stale_reason(today, config.review_days_for(n)),
                standing=n.standing,
                file=self._filed(n.body),
            )
            for n in notes
        ]
        counts: dict[str, int] = {}
        for entry in entries:
            counts[entry.topic] = counts.get(entry.topic, 0) + 1
        described = {
            row["key"]: row.get("description") or ""
            for row in (self.brain.topics().data.get("topics") or [])
        }
        structure = config.data.get("structure") or {}
        declared = {**(structure.get("layers") or {}), **(structure.get("areas") or {})}
        areas = []
        for area in sorted({e.area for e in entries}, key=lambda a: (order.get(a, 99), a)):
            keys = sorted(k for k in counts if k.split("/", 1)[0] == area)
            areas.append(
                BrainArea(
                    key=area,
                    label=config.area_label(area),
                    description=str((declared.get(area) or {}).get("description") or ""),
                    topics=[
                        BrainTopic(
                            key=key,
                            label=st.index.topic_label(key),
                            description=described.get(key, ""),
                            entries=counts[key],
                        )
                        for key in keys
                    ],
                )
            )
        return BrainCatalog(areas=areas, entries=entries)

    def files(self) -> BrainFiles:
        st = self.brain.state()
        vault = self.brain.vault
        chain, partitions = self._view(st)
        notes = self._visible_notes(st)
        pointers: dict[str, Any] = {}
        for note in notes:
            path = self._filed(note.body)
            if path:
                pointers.setdefault(path, note)
        parts: dict[str, int] = {}
        for section in st.index.sections.values():
            parts[section.path] = parts.get(section.path, 0) + 1
        references = []
        for path, ref in sorted(st.index.references.items()):
            if os.path.basename(path).lower() == "readme.md":
                continue
            full = vault.path(*path.split("/"))
            card = st.index.cards.get(path)
            pointer = card if card is not None else pointers.get(path)
            original = self._original(ref.body)
            meta = card.meta if card is not None else {}
            home = st.index.file_project(path)
            references.append(
                BrainFile(
                    path=path,
                    kind="reference",
                    title=st.index.file_title(path),
                    size=_size(full),
                    mime="text/markdown",
                    updated=modified(full),
                    # The entry that sends models here says what the document is for; a
                    # document's own first line is often a status stamp.
                    description=pointer.summary if pointer else excerpt(ref.body),
                    entry_id=pointer.id if pointer else None,
                    original=original[0] if original else None,
                    project=home.id if home is not None else None,
                    project_title=home.title if home is not None else None,
                    version=_number(meta.get("version")),
                    file_status=str(meta.get("file_status") or "") or None,
                    dated=str(meta.get("dated") or "")[:10] or None,
                    sections=parts.get(path, 0),
                    work=str(meta.get("type") or "") == "file",
                )
            )
        assets = []
        for full in _walk(vault.path("assets")):
            path = brain_util.rel(full, vault.root)
            pointer = pointers.get(path)
            title = pointer.meta.get("title") if pointer else None
            if pointer and not title:
                found = ASSET_TITLE.match(pointer.body.strip())
                title = found.group(1) if found else None
            assets.append(
                BrainFile(
                    path=path,
                    kind="asset",
                    title=str(title or _humanize(os.path.basename(path))),
                    size=_size(full),
                    mime=mime_of(path),
                    updated=modified(full),
                    description=pointer.summary if pointer else "",
                    entry_id=pointer.id if pointer else None,
                )
            )
        skills = []
        for skill in sorted(st.index.skills.values(), key=lambda s: (s.category, s.name)):
            if not Scopes.admits(skill.scope, skill.partition, chain, partitions):
                continue
            folder = os.path.dirname(skill.path)
            members = sorted(
                _walk(vault.path(*folder.split("/"))),
                key=lambda p: (os.path.basename(p) != "SKILL.md", p),
            )
            skills.append(
                BrainSkill(
                    name=skill.name,
                    category=skill.category,
                    description=skill.description,
                    when_to_use=skill.when_to_use,
                    triggers=list(skill.triggers),
                    artifacts=list(skill.artifacts),
                    loads=list(skill.loads),
                    depends_on=list(skill.depends_on),
                    scope=skill.scope,
                    invocation=str(skill.meta.get("invocation") or "").strip().lower(),
                    path=folder,
                    files=[
                        BrainFile(
                            path=brain_util.rel(full, vault.root),
                            kind="skill",
                            title=brain_util.rel(full, vault.path(*folder.split("/"))),
                            size=_size(full),
                            mime=mime_of(full),
                            updated=modified(full),
                        )
                        for full in members
                    ],
                )
            )
        return BrainFiles(references=references, assets=assets, skills=skills)

    def file_content(self, path: str, *, original: bool = False) -> BrainFileContent | None:
        rel = clean_path(path)
        if rel is None:
            return None
        vault = self.brain.vault
        parts = rel.split("/")
        base = os.path.realpath(vault.path(parts[0]))
        full = os.path.realpath(vault.path(*parts))
        try:
            inside = os.path.commonpath([base, full]) == base
        except ValueError:  # another drive
            inside = False
        if not inside or not os.path.isfile(full):
            return None
        if parts[0] == "skills" and not self._skill_visible(rel):
            return None
        if original:
            if parts[0] != "references":
                return None
            with open(full, encoding="utf-8", errors="replace") as handle:
                found = self._original(handle.read())
            if found is None:
                return None
            name, library_path = found
            with open(library_path, "rb") as handle:
                return BrainFileContent(filename=name, mime=mime_of(name), data=handle.read())
        with open(full, "rb") as handle:
            data = handle.read()
        return BrainFileContent(filename=parts[-1], mime=mime_of(rel), data=data)

    def skill_folder(self, name: str) -> str | None:
        st = self.brain.state()
        chain, partitions = self._view(st)
        skill = st.index.skills.get(str(name or "").strip().lstrip("/"))
        if skill is None or not Scopes.admits(skill.scope, skill.partition, chain, partitions):
            return None
        folder = self.brain.vault.path(*os.path.dirname(skill.path).split("/"))
        return folder if os.path.isdir(folder) else None

    def skill_source(self, name: str) -> str | None:
        st = self.brain.state()
        chain, partitions = self._view(st)
        skill = st.index.skills.get(str(name or "").strip().lstrip("/"))
        if skill is None or not Scopes.admits(skill.scope, skill.partition, chain, partitions):
            return None
        return str(skill.body)

    def skill_versions(self, name: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        result = self.brain.skill_versions(name, with_text=with_text)
        if result.is_error:
            return None
        return list(result.data.get("versions") or [])

    def propose_skill(
        self,
        *,
        proposer: str,
        sources: list[str],
        body: str,
        target: str | None = None,
        name: str | None = None,
        category: str | None = None,
        description: str | None = None,
        when_to_use: str | None = None,
        triggers: list[str] | None = None,
        artifacts: list[str] | None = None,
        loads: list[str] | None = None,
        reason: str = "",
        evidence: str = "",
    ) -> BrainProposal:
        source = f"{WORKSPACE_SOURCE}{proposer}"
        if sources:
            source += "; sources: " + ", ".join(sources)
        scope = None
        if not target:
            # A new skill joins the scope its category's skills share, when they share one.
            st = self.brain.state()
            kin = Counter(
                s.scope for s in st.index.skills.values() if s.category == (category or "")
            ).most_common(1)
            scope = kin[0][0] if kin else None
        with self._lock:
            result = self.brain.propose_skill(
                target=target,
                name=name,
                category=category,
                description=description,
                when_to_use=when_to_use,
                triggers=triggers,
                artifacts=artifacts,
                loads=loads,
                body=body,
                scope=scope,
                reason=reason or ("a change proposed from the workspace" if target else ""),
                evidence=evidence,
                source=source,
                force_pending=True,
            )
        data = result.data
        status = str(data.get("status") or ("refused" if result.is_error else "pending"))
        if status == "duplicate":
            return BrainProposal(
                status="duplicate", message=result.text, proposal_id=data.get("proposal_id")
            )
        if result.is_error:
            return BrainProposal(status="refused", message=result.text)
        return BrainProposal(
            status=status, message=result.text, proposal_id=data.get("proposal_id")
        )

    def _skill_visible(self, rel: str) -> bool:
        st = self.brain.state()
        chain, partitions = self._view(st)
        for skill in st.index.skills.values():
            folder = os.path.dirname(skill.path) + "/"
            if rel.startswith(folder):
                return Scopes.admits(skill.scope, skill.partition, chain, partitions)
        return False

    def _original(self, text: str) -> tuple[str, str] | None:
        """A reference's original file (its name and where the library keeps it)."""
        found = SOURCE.search(text or "")
        if not found:
            return None
        name, digest = found.group(1), found.group(2)
        path = os.path.join(
            self.brain.vault.runtime_dir, "library", digest + os.path.splitext(name)[1]
        )
        return (name, path) if os.path.isfile(path) else None

    def attention(self) -> dict[str, Any]:
        st = self.brain.state()
        data = dict(self.brain.attention().data)
        # Only what the owner can see; the usage of anything else stays out too.
        visible = {n.id for n in self._visible_notes(st)}
        for key in ("twins",):
            data[key] = [r for r in data[key] if r["a"] in visible and r["b"] in visible]
        for key in ("flagged", "recheck"):
            data[key] = [r for r in data[key] if r["id"] in visible]
        data["usage"] = {k: v for k, v in data["usage"].items() if k in visible}
        return data

    def history(self, entry_id: str) -> list[dict[str, Any]]:
        rows = []
        for record in reversed(self.brain.vault.decisions()):
            target = record.get("target")
            ids = (
                record.get("note"),
                record.get("pointer"),
                target.get("id") if isinstance(target, dict) else None,
            )
            if entry_id in ids:
                rows.append(
                    {
                        key: record[key]
                        for key in (
                            "at",
                            "action",
                            "by",
                            "proposer",
                            "reason",
                            "state",
                            "confidence",
                            "proposal",
                            "kind",
                            "reverted",
                            "redone",
                        )
                        if record.get(key) not in (None, "")
                    }
                )
        return rows[:50]

    # ---- the supply chain. Everything the owner cannot see stays out, and its use too.

    def _seen(self, st: Any) -> set[str]:
        """Ids of every entry, live or archived, the owner may see."""
        chain, partitions = self._view(st)
        notes = list(st.index.notes.values()) + list(st.index.archived.values())
        return {n.id for n in notes if Scopes.admits(n.scope, n.partition, chain, partitions)}

    def _visible_id(self, entry_id: str) -> str | None:
        """The id an entry is filed under (an old id resolves), when the owner may see it."""
        st = self.brain.state()
        note = st.index.note(entry_id, include_archived=True)
        return note.id if note is not None and note.id in self._seen(st) else None

    def record_use(self, ref: str, entries: list[dict[str, Any]]) -> None:
        with self._lock:
            self.brain.record_use(ref, entries)

    def inventory(self) -> list[dict[str, Any]]:
        st = self.brain.state()
        seen = self._seen(st)
        chain, partitions = self._view(st)
        rows = self.brain.inventory().data["items"]
        return [
            r
            for r in rows
            if (r["type"] == "note" and r["id"] in seen)
            or (
                r["type"] == "skill"
                and Scopes.admits(r["scope"], r["partition"], chain, partitions)
            )
            or r["type"] == "reference"
        ]

    def entry_details(self, entry_id: str) -> dict[str, Any] | None:
        found = self._visible_id(entry_id)
        if found is None:
            return None
        data: dict[str, Any] = self.brain.entry(found).data
        return data

    def versions(self, entry_id: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        found = self._visible_id(entry_id)
        if found is None:
            return None
        rows: list[dict[str, Any]] = self.brain.versions(found, with_text=with_text).data[
            "versions"
        ]
        return rows

    def version(self, entry_id: str, ref: str) -> dict[str, Any] | None:
        found = self._visible_id(entry_id)
        if found is None:
            return None
        result = self.brain.version(found, ref)
        return None if result.is_error else dict(result.data)

    def activity(
        self,
        *,
        entry_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        actions: list[str] | None = None,
        by: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        st = self.brain.state()
        seen = self._seen(st)
        if entry_id is not None:
            found = self._visible_id(entry_id)
            if found is None:
                return []
            entry_id = found
        rows = self.brain.activity(
            note_id=entry_id, since=since, until=until, actions=actions, by=by, limit=limit * 2
        ).data["events"]
        out = []
        for row in rows:
            note_id = row.get("note")
            known = st.index.note(note_id, include_archived=True) if note_id else None
            if known is not None and known.id not in seen:
                continue  # an entry the owner cannot see: its events stay out too
            row = dict(row)
            if known is not None:
                row["title"] = known.title
            out.append(row)
        return out[:limit]

    def use(self, entry_id: str, *, days: int = 90) -> dict[str, Any] | None:
        found = self._visible_id(entry_id)
        if found is None:
            return None
        data: dict[str, Any] = self.brain.use(found, days=days).data
        return data

    def gaps(self, *, days: int = 30) -> list[dict[str, Any]]:
        st = self.brain.state()
        seen = self._seen(st)
        rows = self.brain.gaps(days=days).data["gaps"]
        out = []
        for row in rows:
            if row.get("entry") and row["entry"] not in seen:
                continue
            out.append(dict(row, close=[c for c in row.get("close") or [] if c["id"] in seen]))
        return out

    def dismiss_gap(self, key: str) -> None:
        self.brain.dismiss_gap(key)

    def flow(self, *, days: int = 7) -> dict[str, Any]:
        data: dict[str, Any] = self.brain.flow(days=days).data
        return data

    def policies(self) -> dict[str, Any]:
        data: dict[str, Any] = self.brain.policies().data
        return data

    def set_policies(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            result = self.brain.set_policies(changes)
        if result.is_error:
            raise ValidationFailed(result.text)
        data: dict[str, Any] = result.data
        return data

    def add_file(
        self,
        *,
        filename: str,
        data: bytes,
        title: str,
        description: str,
        topic: str | None,
        proposer: str,
        project: str | None = None,
        status: str | None = None,
        origin: str = "app",
    ) -> BrainProposal:
        with self._lock:
            result = self.brain.add_file(
                filename=filename,
                content_base64=base64.b64encode(data).decode("ascii"),
                title=title or None,
                description=description,
                topic=topic,
                project=project or None,
                status=status or None,
                origin=origin,
                source=f"{WORKSPACE_SOURCE}{proposer}",
            )
        found = result.data
        outcome = str(found.get("status") or ("refused" if result.is_error else "pending"))
        if result.is_error:
            return BrainProposal(status="refused", message=result.text)
        checkpoint = found.get("checkpoint") or {}
        return BrainProposal(
            status=outcome,
            message=result.text,
            proposal_id=found.get("proposal_id"),
            entry_id=found.get("id") if outcome == "applied" else None,
            path=found.get("path") or found.get("target"),
            version=_number(found.get("version")),
            replaced=found.get("replaced") or found.get("replaces"),
            sections=int(found.get("sections") or 0),
            project=found.get("project"),
            checkpoint_id=checkpoint.get("id") if isinstance(checkpoint, dict) else None,
        )

    # ---------------------------------------------------------------- projects

    def projects(self) -> list[BrainProject]:
        st = self.brain.state()
        counts: dict[str, int] = {}
        for path in st.index.cards:
            home = st.index.file_project(path)
            if home is not None:
                counts[home.id] = counts.get(home.id, 0) + 1
        result = self.brain.focus_list()
        rows = result.data.get("focuses") or [] if not result.is_error else []
        out = []
        for row in rows:
            focus = st.index.focuses.get(row["id"])
            if focus is None:
                continue
            out.append(
                BrainProject(
                    id=focus.id,
                    title=focus.title,
                    summary=str(focus.note.summary or ""),
                    status=str(row.get("status") or "active"),
                    active=bool(row.get("active", True)),
                    current=str(row.get("current") or ""),
                    next=str(row.get("next") or ""),
                    blockers=str(row.get("blockers") or ""),
                    updated=str(row.get("updated") or "") or None,
                    aliases=list(focus.aliases),
                    files=counts.get(focus.id, 0),
                    updates=len(focus.updates),
                    topic=focus.note.route_key,
                )
            )
        return out

    def project(self, project_id: str) -> dict[str, Any] | None:
        result = self.brain.project(project_id)
        if result.is_error:
            return None
        data: dict[str, Any] = dict(result.data)
        return data

    def project_update(
        self, project_id: str, *, summary: str, changes: dict[str, str], evidence: str = ""
    ) -> dict[str, Any]:
        with self._lock:
            result = self.brain.focus_update(project_id, summary, changes, evidence=evidence)
        if result.is_error:
            if result.data.get("status") == "missing":
                raise NotFound(result.text)
            raise ValidationFailed(result.text)
        data: dict[str, Any] = dict(result.data)
        return data

    def create_project(
        self, *, name: str, summary: str, aliases: list[str], proposer: str
    ) -> BrainProject:
        with self._lock:
            result = self.brain.focus_create(name, summary, aliases=aliases)
        if result.is_error:
            if result.data.get("status") == "exists":
                raise Conflict(result.text)
            raise ValidationFailed(result.text)
        made = result.data.get("id")
        found = next((p for p in self.projects() if p.id == made), None)
        if found is None:
            # It waits for review (another person's scope): say so rather than pretend.
            raise Conflict(result.text)
        return found

    def preview(self, request: str, *, project: str | None = None) -> dict[str, Any]:
        result = self.brain.preview(request, focus=project or None)
        if result.is_error:
            raise ValidationFailed(result.text)
        data: dict[str, Any] = dict(result.data)
        data["text"] = result.text  # as a conversation gets it, so the person sees the same
        return data

    # ---------------------------------------------------------------- governance

    def propose(
        self,
        *,
        title: str,
        statement: str,
        kind: str,
        scope: str | None,
        evidence: str,
        sources: list[str],
        proposer: str,
        replaces: list[str] | None = None,
        contradicts: list[str] | None = None,
        topic: str | None = None,
        revises: str | None = None,
        summary: str | None = None,
        origin: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> BrainProposal:
        source = f"{WORKSPACE_SOURCE}{proposer}"
        if sources:
            source += "; sources: " + ", ".join(sources)
        area, _, topic_name = (topic or "").partition("/")
        if kind == "decision" and not revises:
            # A decision is a fact the capture policy knows as a decision.
            extra = dict(extra or {}, type="decision")
        with self._lock:
            result = self.brain.propose(
                title=title,
                text=statement,
                # Always one: a change to an entry must not keep the old text's summary.
                summary=summary or summary_from(statement),
                # A change to an entry keeps the entry's kind, scope and place.
                note_kind=None if revises else KIND_MAP.get(kind, "fact"),
                scope=None if revises else scope or None,
                evidence=evidence,
                source=source,
                reason=f"{kind} proposed from the workspace"
                + (f", a change to {revises}" if revises else ""),
                force_pending=True,
                supersedes=", ".join(replaces or []) or None,
                conflicts=", ".join(contradicts or []) or None,
                area=area or None,
                topic=topic_name or None,
                target_id=revises or None,
                origin=origin,
                extra=extra or None,
            )
        data = result.data
        status = str(data.get("status") or ("refused" if result.is_error else "pending"))
        if result.is_error and status not in ("duplicate",):
            return BrainProposal(status="refused", message=result.text)
        return BrainProposal(
            status=status,
            message=result.text,
            proposal_id=data.get("proposal_id"),
            entry_id=data.get("id"),
        )

    def propose_many(self, items: list[dict[str, Any]], *, proposer: str) -> list[BrainProposal]:
        """Many proposals as one change: the index is rebuilt after each, the startup files
        and the commit once at the end."""
        out = []
        with self.brain.deferring() as deferred:
            deferred.message = f"{len(items)} proposal(s) from the workspace"
            for item in items:
                out.append(self.propose(proposer=proposer, **item))
        return out

    # ---------------------------------------------------------------- keeping up

    def recap(self, since: str) -> dict[str, Any]:
        st = self.brain.state()
        seen = self._seen(st)
        data: dict[str, Any] = dict(self.brain.recap(since).data)
        data["went_in"] = [
            row
            for row in data.get("went_in") or []
            if row.get("kind") == "file.add" or row.get("id") in seen
        ]
        data["projects"] = [p for p in data.get("projects") or [] if p.get("id") in seen]
        return data

    def requests(
        self, *, limit: int = 50, before: str | None = None, client: str | None = None
    ) -> dict[str, Any]:
        st = self.brain.state()
        seen = self._seen(st)
        data: dict[str, Any] = dict(
            self.brain.requests(limit=limit, before=before, client=client).data
        )
        for row in data.get("requests") or []:
            # Only what the owner may see, and its use too.
            for key in ("got", "opened"):
                row[key] = [p for p in row[key] if p["kind"] != "note" or p["id"] in seen]
        return data

    def made_from(self, path: str) -> dict[str, Any] | None:
        found = self.brain.made_from(path).data.get("found")
        if found is None:
            return None
        st = self.brain.state()
        seen = self._seen(st)
        for row in found.get("requests") or []:
            for key in ("got", "opened"):
                row[key] = [p for p in row[key] if p["kind"] != "note" or p["id"] in seen]
        return dict(found)

    def work_given(self, run_id: str) -> list[dict[str, Any]]:
        st = self.brain.state()
        seen = self._seen(st)
        pieces = self.brain.work_given(run_id).data.get("pieces") or []
        return [p for p in pieces if p["kind"] != "note" or p["id"] in seen]

    def kernel(self) -> dict[str, Any]:
        found = self.brain.kernel()
        return {"text": found.text, "tokens": int(found.data.get("tokens") or 0)}

    def weekly(self, weeks: int = 8) -> list[dict[str, Any]]:
        return list(self.brain.weekly(weeks).data.get("weeks") or [])

    def goals(self) -> dict[str, Any]:
        return dict(self.brain.goals().data)

    def set_goals(self, answers: dict[str, str]) -> dict[str, Any]:
        with self._lock:
            result = self.brain.set_goals(answers)
        if result.is_error:
            if result.data.get("status") == "forbidden":
                raise Conflict(result.text)
            raise ValidationFailed(result.text, field=result.data.get("field"))
        return dict(result.data)

    def builtin_skills(self) -> dict[str, Any]:
        return dict(self.brain.builtin_skills().data)

    def add_builtin_skills(self, names: list[str] | None = None) -> dict[str, Any]:
        with self._lock:
            result = self.brain.add_builtin_skills(names)
        if result.is_error:
            raise Conflict(result.text)
        return dict(result.data)

    def move_in(self, sources: list[dict[str, Any]], *, name: str = "") -> dict[str, Any]:
        result = self.brain.move_in(sources, name=name)
        if result.is_error:
            raise ValidationFailed(result.text)
        return dict(result.data)

    def proposals(self) -> list[dict[str, Any]]:
        """Waiting proposals. For ones made in the workspace, `proposer` names the real actor
        (the Brain itself records its owner, as whom the workspace writes), `sources` lists
        what it came from, and `task_id` the work (a distillation request) that made it."""
        rows = []
        scopes = self.brain.state().scopes
        for row in self.brain.inbox().data.get("proposals") or []:
            source = str((row.get("target") or {}).get("source") or "")
            label = next((x for x in SOURCE_LABELS if source.startswith(x)), None)
            if label:
                who, _, refs = source[len(label) :].partition("; sources: ")
                sources = [s.strip() for s in refs.split(",") if s.strip()]
                row = dict(row, proposer=who.strip(), sources=sources)
                task = next((s[len("task:") :] for s in sources if s.startswith("task:")), None)
                if task:
                    row["task_id"] = task
            else:  # proposed through the Brain itself: its principal, by the name it is known by
                row = dict(row, proposer=scopes.label(str(row.get("proposer") or "")))
            rows.append(row)
        return rows

    def review(self) -> list[dict[str, Any]]:
        """The Brain's analysis of each waiting proposal, plus the entries a workspace
        proposal says it was checked against (`brain:<id>` among its sources)."""
        result = self.brain.review()
        if result.is_error:
            raise Conflict(result.text)
        st = self.brain.state()
        rows = []
        for found in result.data.get("proposals") or []:
            row = dict(found)
            proposal = st.snapshot.proposals.get(str(row.get("id")))
            source = str((proposal.target if proposal else {}).get("source") or "")
            named = {e.get("id") for e in row.get("replaces", []) + row.get("conflicts", [])}
            related = []
            for ref in dict.fromkeys(RELATED.findall(source)):
                if ref in named:
                    continue
                note = st.index.note(ref, include_archived=True)
                related.append(
                    {
                        "id": ref,
                        "title": note.title if note else ref,
                        "live": bool(note and note.live),
                    }
                )
            row["related"] = related
            rows.append(row)
        return rows

    def decide_many(
        self,
        decisions: list[dict[str, Any]],
        *,
        label: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Decide as the Brain's owner (a human release gate), as one undo point."""
        st = self.brain.state()
        items = []
        for decision in decisions:
            edits: dict[str, Any] = {}
            for key in ("title", "summary"):
                if decision.get(key):
                    edits[key] = decision[key]
            if decision["action"] in ENTRY_ACTIONS:
                items.append(
                    {
                        "id": decision["entry_id"],
                        "action": decision["action"],
                        "reason": decision.get("reason") or "",
                        "body": decision.get("body"),
                        "edits": edits or None,
                        "minor": bool(decision.get("minor")),
                        "ref": decision.get("ref"),
                        "fields": decision.get("fields"),
                        "state": decision.get("state"),
                        "confidence": decision.get("confidence"),
                    }
                )
                continue
            if decision.get("replaces"):
                edits["supersedes"] = ", ".join(decision["replaces"])
            if decision.get("topic"):
                area, _, topic = str(decision["topic"]).partition("/")
                proposal = st.snapshot.proposals.get(decision["proposal_id"])
                target = proposal.target if proposal else {}
                edits["layer" if "layer" in target and "area" not in target else "area"] = area
                edits["topic"] = topic
                edits["placement"] = "chosen"
            items.append(
                {
                    "id": decision["proposal_id"],
                    "action": decision["action"],
                    "reason": decision.get("reason") or "",
                    "edits": edits or None,
                    # Approved in the person's own words: the engine files this text instead.
                    "body": decision.get("body"),
                }
            )
        with self._lock:
            result = self.brain.decide(items, label=label, source=source)
        if "results" not in result.data:
            raise Conflict(result.text)
        return {"results": result.data["results"], "checkpoint": result.data.get("checkpoint")}

    def checkpoints(self, limit: int = 50) -> list[dict[str, Any]]:
        scopes = self.brain.state().scopes
        return [
            dict(point, by=scopes.label(str(point.get("by") or "")))
            for point in self.brain.checkpoints(limit).data.get("checkpoints") or []
        ]

    def undo(self, checkpoint_id: str) -> dict[str, Any]:
        with self._lock:
            result = self.brain.undo(checkpoint_id)
        if result.is_error:
            if result.data.get("status") == "missing":
                raise NotFound(result.text)
            raise Conflict(result.text, blocked=result.data.get("blocked") or [])
        return {"undone": result.data.get("undone"), "checkpoint": result.data.get("checkpoint")}


def _revision(meta: dict[str, Any]) -> str | None:
    for key in ("revision", "updated", "added"):
        if meta.get(key):
            return str(meta[key])
    return None


def _number(value: Any) -> int | None:
    """A positive whole number from a card's field (front matter reads it as text)."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _walk(root: str) -> list[str]:
    """Every file under a folder, skipping hidden names; empty when the folder is absent."""
    out: list[str] = []
    if not os.path.isdir(root):
        return out
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        out += [os.path.join(folder, n) for n in sorted(names) if not n.startswith(".")]
    return out


def _humanize(filename: str) -> str:
    stem = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip()
    return stem[:1].upper() + stem[1:] if stem else filename
