"""BrainPort, implemented with the `brainkit` engine (packages/brain).

The workspace reads the Brain as its owner and proposes into it with `force_pending`, so a
proposal made from the workspace waits for an explicit approval, unless it says who brought it
(`capture_origin`: the owner's AI at work in the app, a swept folder, a heartbeat read): the
Brain's governance then decides, and in Auto it goes in with an undo point unless it must wait
(Release 1 ships auto-governed).
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re
import threading
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from brainkit import statements
from brainkit import util as brain_util
from brainkit.api import Brain, Result
from brainkit.governance import summary_from
from brainkit.model import listish
from brainkit.scopes import Scopes
from workspace_core.domain import statements as statements_core
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

log = logging.getLogger(__name__)
MATCHING_MB = 70  # the model that matches by meaning (bge-small, quantized), about this size

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
SOURCE_FIELDS = (
    "source_id",
    "source_version",
    "source_locator",
    "source_speaker",
    "source_excerpt",
)
RELATED = re.compile(r"\bbrain:([A-Za-z0-9][A-Za-z0-9_.-]*[A-Za-z0-9])")
TOOL_NAMES = {"notes_search": "search_context", "notes_get": "get_brain_entry"}
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
        self._fetching = False  # the matching model is being downloaded
        self._fetch_error: str | None = None
        # Skills' git history for the Skills page, kept while the Brain's files are unchanged.
        self._skills_history: tuple[str, dict[str, dict[str, Any]]] | None = None
        self._held_texts: tuple[str, set[str]] | None = None  # live notes' fingerprints
        self._local_fetching: set[str] = set()  # local models being downloaded
        self._local_errors: dict[str, str] = {}

    def close(self) -> None:
        self.brain.close()

    # ---------------------------------------------------------------- local models

    def models(self) -> dict[str, Any]:
        """The model that matches by meaning: here, being fetched, or not yet (the owner
        downloads it; a server never does on its own)."""
        embedder = self.brain.embedder
        if embedder is None:
            return {
                "matching": {
                    "enabled": False,
                    "present": False,
                    "downloading": False,
                    "error": None,
                    "model": None,
                    "about_mb": MATCHING_MB,
                }
            }
        return {
            "matching": {
                "enabled": True,
                "model": embedder.model_name,
                "present": embedder.present(),
                "downloading": self._fetching,
                "error": self._fetch_error,
                "about_mb": MATCHING_MB,
            }
        }

    def download_models(self) -> dict[str, Any]:
        """Fetch the matching model into the Brain's model folder, in the background, with
        the certificates the operating system trusts (a company network's TLS inspection)."""
        embedder = self.brain.embedder
        if embedder is None or self._fetching or embedder.present():
            return self.models()
        self._fetching, self._fetch_error = True, None

        def fetch() -> None:
            try:
                try:
                    import truststore

                    truststore.inject_into_ssl()
                except ImportError:
                    pass
                status = embedder.download()
                if not status.get("available"):
                    self._fetch_error = str(status.get("reason") or "The download failed.")
            except Exception as exc:  # the network, the disk: say what went wrong
                self._fetch_error = f"The model could not be downloaded: {exc}"
                log.warning(self._fetch_error, exc_info=True)
            finally:
                self._fetching = False

        threading.Thread(target=fetch, name="matching-model", daemon=True).start()
        return self.models()

    # ---------------------------------------------------------------- local models

    def local_models(self) -> dict[str, Any]:
        """Settings, On this computer, Local models (brain-logic plan 5.11.16)."""
        from brainkit import machine

        found = machine.overview()
        embedder = self.brain.embedder
        here = bool(embedder is not None and embedder.present())
        for role in found.get("roles") or []:
            for option in role["options"]:
                if option.get("with_brain"):  # the meaning index's model, kept with the Brain
                    option.update(downloaded=here, why_not="" if here else "not downloaded")
        found.update(
            enabled=True,
            downloading=sorted(self._local_fetching),
            errors=dict(self._local_errors),
        )
        return found

    def act_local_models(
        self, action: str, name: str = "", on: bool | None = None
    ) -> dict[str, Any]:
        """One change the owner asked for. A refusal (the lock, the RAM check, a model in
        use) is a ValidationFailed with the reason; a warning that does not refuse comes
        back as `notice`."""
        from brainkit import machine, modellock, models_client

        notice = ""
        try:
            if action == "check":
                machine.check()  # and with the models here, time them again
                if models_client.status(refresh=True).ready:
                    notice = "; ".join(machine.check_speed()["slow"])
            elif action == "default":
                lock = modellock.Lock.load()
                made = machine.choose(lock.pin(name).role, name, lock=lock)
                notice = str(made.get("warning") or "")
                self._reload_local_models()
            elif action == "download":
                self._download_local_model(name)
            elif action == "remove":
                machine.remove(name)
            elif action == "speed":
                notice = "; ".join(machine.check_speed()["slow"])
            elif action == "claude_code":
                machine.set_agent_claude_code(bool(on))
        except (modellock.Refused, ValueError) as exc:
            raise ValidationFailed(str(exc)) from exc
        except (models_client.ServiceError, OSError, RuntimeError) as exc:
            raise Conflict(f"Not done: {exc}") from exc
        found = self.local_models()
        found["notice"] = notice
        return found

    def _reload_local_models(self) -> None:
        """A running model service loads the new default; with none running, one starts when
        this computer's models are here."""
        from brainkit import models_client, modelservice

        found = models_client.status(refresh=True)
        if found.url:
            models_client.reload(found)
        else:
            log.info(modelservice.ensure())

    def _download_local_model(self, name: str) -> None:
        """Fetch a pinned model in the background, then verify it against the lock."""
        from brainkit import machine, modellock

        lock = modellock.Lock.load()
        machine.downloadable(name, lock)  # refused now, not in the background
        with self._lock:
            if name in self._local_fetching:
                return
            self._local_fetching.add(name)
            self._local_errors.pop(name, None)

        def fetch() -> None:
            try:
                verdict = machine.download(name, lock=lock)
                if not verdict.ok:
                    self._local_errors[name] = (
                        f"Downloaded, but it does not match the lock, so it is not used: "
                        f"{verdict.reason}"
                    )
            except Exception as exc:  # the network, the disk: say what went wrong
                self._local_errors[name] = f"{name} could not be downloaded: {exc}"
                log.warning(self._local_errors[name], exc_info=True)
            finally:
                with self._lock:
                    self._local_fetching.discard(name)

        threading.Thread(target=fetch, name=f"local-model-{name}", daemon=True).start()

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

    def search(
        self, query: str, limit: int = 10, *, include_archived: bool = False
    ) -> list[BrainHit]:
        result = self.brain.search(query, limit=limit, include_archived=include_archived)
        return [
            BrainHit(
                id=h["id"],
                title=h.get("title") or h["id"],
                summary=h.get("summary") or "",
                scope=h.get("scope") or "",
                kind=h.get("route_key") or "",
                score=float(h.get("score") or 0),
                excerpt=h.get("excerpt") or "",
            )
            for h in result.data.get("hits", [])
        ]

    def entry(self, entry_id: str, *, include_archived: bool = False) -> BrainEntry | None:
        # A note sealed to a partition (a client, say) opens within that partition, which
        # the owner owns.
        note = self.brain.state().index.note(entry_id, include_archived=include_archived)
        result = self.brain.note(
            entry_id, partition=note.partition if note else None, include_archived=include_archived
        )
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
            said_by=meta.get("said_by"),
            as_of=meta.get("as_of"),
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
                    library=str(meta.get("library") or "") or None,
                    source_url=str(meta.get("source_url") or "") or None,
                    source_repo=str(meta.get("source_repo") or "") or None,
                    source_paths=tuple(str(p) for p in (meta.get("source_paths") or [])),
                    fetched_at=str(meta.get("fetched_at") or "") or None,
                    refresh=str(meta.get("refresh") or "") or None,
                    **_origin(meta, project=home is not None),
                    scope=card.scope if card is not None else None,
                )
            )
        assets = []
        for full in _walk(vault.path("assets")):
            path = brain_util.rel(full, vault.root)
            card = st.index.asset_cards.get(path)
            pointer = card if card is not None else pointers.get(path)
            meta = card.meta if card is not None else {}
            title = pointer.meta.get("title") if pointer else None
            if pointer and not title:
                found = ASSET_TITLE.match(pointer.body.strip())
                title = found.group(1) if found else None
            home = st.index.focuses.get(str(meta.get("project_id") or "")) if meta else None
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
                    project=home.id if home is not None else None,
                    project_title=home.title if home is not None else None,
                    library=str(meta.get("library") or "") or None,
                    **_origin(meta, project=home is not None),
                    scope=card.scope if card is not None else None,
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

    def skill_freshness(self, name: str) -> dict[str, Any] | None:
        st = self.brain.state()
        chain, partitions = self._view(st)
        skill = st.index.skills.get(str(name or "").strip().lstrip("/"))
        if skill is None or not Scopes.admits(skill.scope, skill.partition, chain, partitions):
            return None
        versions = self.skill_versions(skill.name) or []
        edited = str(versions[0].get("at") or "") if versions else ""
        return {"last_edited": edited or None, "changed": self._changed_since(st, skill, edited)}

    def _changed_since(self, st: Any, skill: Any, edited: str) -> list[dict[str, Any]]:
        """What a skill loads that changed after its last edit."""
        changed: list[dict[str, Any]] = []
        for key in skill.loads:
            when, title = self._load_changed(st, str(key))
            if when and edited and when > edited:
                changed.append({"key": str(key), "title": title, "at": when})
        return changed

    def holds_text(self, fingerprints: list[str]) -> set[str]:
        st = self.brain.state()
        with self._lock:
            if self._held_texts is None or self._held_texts[0] != st.fingerprint:
                self._held_texts = (
                    st.fingerprint,
                    {statements_core.fingerprint(n.body) for n in st.index.notes.values()},
                )
            held = self._held_texts[1]
        return {f for f in fingerprints if f in held}

    def skills_history(self, names: list[str]) -> dict[str, dict[str, Any]]:
        """Each skill's versions (their hashes, newest first), its last edit and what it loads
        that changed since, read from git once while the Brain's files stay as they are (git
        is slow, and the Skills page asks for every skill at once)."""
        st = self.brain.state()
        chain, partitions = self._view(st)
        with self._lock:
            if self._skills_history is None or self._skills_history[0] != st.fingerprint:
                self._skills_history = (st.fingerprint, {})
            known = self._skills_history[1]
        out: dict[str, dict[str, Any]] = {}
        for name in names:
            skill = st.index.skills.get(str(name or "").strip().lstrip("/"))
            if skill is None or not Scopes.admits(skill.scope, skill.partition, chain, partitions):
                continue
            if skill.name not in known:
                versions = self.skill_versions(skill.name) or []
                edited = str(versions[0].get("at") or "") if versions else ""
                known[skill.name] = {
                    "hashes": [v.get("hash") for v in versions],
                    "last_edited": edited or None,
                    "changed": self._changed_since(st, skill, edited),
                }
            out[name] = known[skill.name]
        return out

    def _load_changed(self, st: Any, key: str) -> tuple[str | None, str]:
        """When what a skill loads last changed on disk (a document, or the newest note on a
        topic or in an area), and what to call it."""
        clean = key.strip().strip("/")
        if clean.startswith("references/"):
            ref = st.index.references.get(clean)
            paths, title = ([clean], ref.title) if ref is not None else ([], clean)
        else:
            paths = [
                n.path
                for n in st.index.notes.values()
                if n.route_key == clean or n.route_key.startswith(clean + "/") or n.area == clean
            ]
            title = clean
        times = []
        for rel in paths:
            try:
                times.append(os.path.getmtime(self.brain.vault.path(*rel.split("/"))))
            except OSError:
                continue
        if not times:
            return None, title
        return datetime.fromtimestamp(max(times), UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), title

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        embedder = getattr(self.brain, "embedder", None)
        if embedder is None or not texts:
            return None
        try:
            vectors = embedder.embed([str(t) for t in texts])
        except Exception:  # no model here, or it failed: callers compare by words
            log.warning("embedding failed", exc_info=True)
            return None
        return [list(v) for v in vectors] if vectors else None

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
        files: list[dict[str, Any]] | None = None,
        depends_on: list[str] | None = None,
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
                depends_on=depends_on,
                files=files,
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
        data["went_in"] = [
            r
            for r in data.get("went_in") or []
            if r["note"]["id"] in visible and r["with"]["id"] in visible
        ]
        data["dated"] = [
            r
            for r in data.get("dated") or []
            if r["older"]["id"] in visible and r["newer"]["id"] in visible
        ]
        data["usage"] = {k: v for k, v in data["usage"].items() if k in visible}
        return data

    def pending_checks(self, limit: int = 4) -> list[dict[str, Any]]:
        return list(self.brain.pending_checks(limit).data.get("batches") or [])

    def record_checks(self, verdicts: list[dict[str, Any]]) -> int:
        return int(self.brain.record_checks(verdicts).data.get("kept") or 0)

    def challenge(
        self, note_id: str, *, claim: str, evidence: str, source: str, proposer: str
    ) -> BrainProposal:
        found = self._visible_id(note_id)
        if found is None:
            return BrainProposal(status="refused", message=f"No entry {note_id} to challenge.")
        with self._lock:
            result = self.brain.challenge(
                found,
                claim=claim,
                evidence=evidence,
                source=source,
                reason=f"a challenge from {proposer}",
            )
        data = result.data
        status = str(data.get("status") or ("refused" if result.is_error else "pending"))
        if result.is_error and status != "duplicate":
            status = "refused"
        return BrainProposal(
            status=status,
            message=result.text,
            proposal_id=data.get("proposal_id"),
            entry_id=data.get("id"),
        )

    def cross_check(self) -> list[dict[str, Any]]:
        visible = {n.id for n in self._visible_notes(self.brain.state())}
        return [
            f for f in self.brain.cross_check().data.get("findings") or [] if f["id"] in visible
        ]

    def challenge_targets(self, limit: int = 3) -> list[dict[str, Any]]:
        visible = {n.id for n in self._visible_notes(self.brain.state())}
        return [
            t
            for t in self.brain.challenge_targets(limit).data.get("targets") or []
            if t["id"] in visible
        ]

    def apply_scheduled(self) -> dict[str, Any]:
        with self._lock:
            result = self.brain.apply_scheduled()
        if result.is_error:
            raise Conflict(result.text)
        return {
            "applied": list(result.data.get("applied") or []),
            "returned": list(result.data.get("returned") or []),
        }

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

    # ---------------------------------------------------------------- prompts

    def prompts(self, *, archived: bool = False) -> list[dict[str, Any]]:
        """The owner's prompts kept in the Library, newest first: each prompt's card (its
        words exactly, its tags, what it was used with, its project) and the files that came
        with it."""
        st = self.brain.state()
        chain, partitions = self._view(st)
        pool = st.index.archived if archived else st.index.notes
        cards = [
            n
            for n in pool.values()
            if str(n.meta.get("library") or "") == "prompt"
            and Scopes.admits(n.scope, n.partition, chain, partitions)
        ]
        rows = [self._prompt_row(st, card) for card in cards]
        rows.sort(key=lambda r: (str(r["updated"] or ""), r["title"]), reverse=True)
        return rows

    def prompt(self, prompt_id: str) -> dict[str, Any] | None:
        """One prompt, live or set aside, with every version of its words."""
        st = self.brain.state()
        card = st.index.note(prompt_id, include_archived=True)
        if (
            card is None
            or str(card.meta.get("library") or "") != "prompt"
            or card.id not in self._seen(st)
        ):
            return None
        row = self._prompt_row(st, card)
        found = self.brain.versions(card.id, with_text=True).data.get("versions") or []
        kept: list[dict[str, Any]] = []
        for v in found:  # newest first; a version whose words did not change is not one
            words = prompt_words(str(v.get("body") or ""))
            if kept and kept[-1]["body"] == words:
                kept[-1].update(ref=v.get("ref"), at=v.get("at"))
                continue
            kept.append(
                {"ref": v.get("ref"), "at": v.get("at"), "by": v.get("author"), "body": words}
            )
        row["versions"] = kept
        return row

    def _prompt_row(self, st: Any, card: Any) -> dict[str, Any]:
        meta = card.meta
        path = str(meta.get("file") or "")
        home = st.index.focuses.get(str(meta.get("project_id") or "")) or (
            st.index.file_project(path) if path else None
        )
        attached = [
            {
                "path": p,
                "title": c.title,
                "kind": "asset" if p.startswith("assets/") else "reference",
            }
            for p, c in [*st.index.cards.items(), *st.index.asset_cards.items()]
            if str(c.meta.get("attached_to") or "") == path and path
        ]
        full = self.brain.vault.path(*path.split("/")) if path else ""
        return {
            "id": card.id,
            "path": path,
            "title": card.title,
            "body": prompt_words(card.body),
            "tags": [str(t) for t in meta.get("tags") or []],
            "picks": {
                "skills": [str(s) for s in meta.get("prompt_skills") or []],
                "agent": str(meta.get("prompt_agent") or "") or None,
                "docs": [str(d) for d in meta.get("prompt_docs") or []],
                "library": [str(r) for r in meta.get("prompt_reads") or []],
                "project": home.id if home is not None else None,
            },
            "project": home.id if home is not None else None,
            "project_title": home.title if home is not None else None,
            "version": _number(meta.get("version")) or 1,
            "added": str(meta.get("added") or "") or None,
            "updated": modified(full) if full else None,
            "origin": str(meta.get("origin") or "") or None,
            "scope": card.scope,
            "archived": not card.live,
            "attachments": attached,
        }

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

    def taste(self) -> dict[str, Any]:
        return dict(self.brain.taste().data)

    def propose_taste(self, text: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            found = self.brain.propose_taste(text, **fields)
        if found.is_error:
            raise ValidationFailed(found.text)
        return dict(found.data, message=found.text)

    def learned(self) -> list[dict[str, Any]]:
        return list(self.brain.learned().data.get("rules") or [])

    def forget_learned(self, rule_id: str) -> dict[str, Any]:
        with self._lock:
            found = self.brain.forget_learned(rule_id)
        if found.is_error:
            raise NotFound(found.text, id=rule_id)
        return dict(found.data)

    def relevance(self, goal: str, texts: list[str]) -> list[float | None] | None:
        """Meaning scores against a goal by the local meaning model, when it is here."""
        embedder = self.brain.embedder
        if embedder is None or not embedder.present() or not goal or not texts:
            return None
        from brainkit.index import cosine

        try:
            wanted = embedder.embed_query(goal)
            vectors = embedder.embed(texts)
        except Exception:  # noqa: BLE001 - scoring is a hint; capture goes on without it
            return None
        if wanted is None or vectors is None:
            return None
        return [round(float(cosine(wanted, v)), 4) for v in vectors]

    def brain_map(
        self, *, area: str | None = None, page: int = 1, tier: str | None = None
    ) -> dict[str, Any]:
        found = self.brain.brain_map(area=area, page=page, tier=tier)
        if found.is_error:
            raise ValidationFailed(found.text)
        return dict(found.data)

    def map_view(self) -> dict[str, Any]:
        """Every tier whole, the short map as a packet sends it, what it cut, and how many
        sealed projects it leaves out (for the owner's own view only)."""
        return dict(self.brain.map_view().data)

    def sections(self, item_id: str) -> dict[str, Any]:
        found = self.brain.sections(item_id)
        if found.is_error:
            raise NotFound(found.text, id=item_id)
        return dict(found.data)

    def open_address(self, address: str) -> dict[str, Any]:
        """One part by its address, as the owner reads it (no conversation, no budget)."""
        found = self.brain.open(address)
        if found.data.get("status") == "not_found":
            raise NotFound(found.text, address=address, gone_at=found.data.get("gone_at"))
        if found.is_error:
            raise ValidationFailed(found.text)
        return dict(found.data)

    def lore(self) -> list[dict[str, Any]]:
        return list(self.brain.lore().data.get("lessons") or [])

    def lesson(self, lesson_id: str) -> dict[str, Any]:
        found = self.brain.lesson(lesson_id)
        if found.is_error:
            raise NotFound(found.text, id=lesson_id)
        return dict(found.data)

    def propose_lesson(self, **fields: Any) -> dict[str, Any]:
        with self._lock:
            found = self.brain.propose_lesson(**fields)
        if found.is_error:
            raise ValidationFailed(found.text)
        return dict(found.data, message=found.text)

    def sessions_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        found = self.brain.sessions_search(query, limit=limit)
        if found.is_error:
            raise ValidationFailed(found.text)
        return list(found.data.get("sessions") or [])

    def requests_in(self, session_id: str) -> list[dict[str, Any]]:
        found = self.brain.requests(session=session_id, limit=50)
        return list(reversed(found.data.get("requests") or []))

    def receipt(self, packet_id: str) -> dict[str, Any] | None:
        found = self.brain.receipt(packet_id)
        return None if found.is_error else dict(found.data)

    def brain_versions(self) -> list[dict[str, Any]]:
        return self.brain.brain_versions.list()

    def bench_files(self) -> dict[str, str]:
        return dict(self.brain.bench_files())

    def commit_sheets(self, message: str) -> dict[str, Any]:
        with self._lock:
            return dict(self.brain.commit_sheets(message))

    def world_draft(self) -> dict[str, Any]:
        return dict(self.brain.world_draft())

    def propose_world(self, text: str, regions: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return dict(self.brain.propose_world(text, regions))

    def bench_write(self, rel: str, text: str | None, *, message: str) -> dict[str, Any]:
        try:
            with self._lock:
                return dict(self.brain.bench_write(rel, text, message=message))
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc

    def save_version(self, *, cause: str = "manual", note: str = "") -> dict[str, Any]:
        with self._lock:
            result = self.brain.brain_versions.tag(cause=cause, note=note)
        if result.is_error:
            raise Conflict(result.text)
        return dict(result.data, message=result.text)

    def version_diff(self, a: str, b: str) -> dict[str, Any]:
        try:
            return self.brain.brain_versions.diff(a, b)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc

    def restore_version(self, version: str, *, ids: list[str] | None = None) -> dict[str, Any]:
        with self._lock:
            result = self.brain.brain_versions.restore(version, ids=ids)
        if result.is_error:
            if result.data.get("status") == "missing":
                raise NotFound(result.text)
            raise Conflict(result.text, changed_since=result.data.get("changed_since") or [])
        return dict(result.data, message=result.text)

    def correct(
        self, packet_id: str, kind: str, *, item: str = "", note: str = ""
    ) -> dict[str, Any]:
        from brainkit import corrections

        with self._lock:
            result = corrections.correct(self.brain, packet_id, kind, item=item, note=note)
        if result.is_error:
            if result.data.get("status") == "missing":
                raise NotFound(result.text)
            raise ValidationFailed(result.text)
        return dict(result.data, message=result.text)

    def indexed(self, ids: list[str]) -> set[str]:
        # The index the next request is matched against: on a large Brain it is rebuilt in
        # the background, and a kept entry is not searchable until that finishes.
        index = self.brain.state().index
        return {i for i in ids if index.note(str(i)) is not None}

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

    def migrate_governance(self) -> dict[str, Any] | None:
        """Release 1 ships auto-governed: a Brain from before switches to Auto once, with a
        notice the owner can reverse; after that, their choice stands."""
        from brainkit import governance

        with self._lock:
            return governance.migrate(self.brain)

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
        wait: bool = False,
        library: dict[str, Any] | None = None,
        replaces: str | None = None,
        came_from: str | None = None,
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
                wait=wait,
                source=f"{WORKSPACE_SOURCE}{proposer}",
                library=library or None,
                replaces=replaces or None,
                came_from=came_from or None,
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
                    objective=str(focus.note.meta.get("objective") or ""),
                    goals=listish(focus.note.meta.get("goals")),
                )
            )
        return out

    def project(self, project_id: str) -> dict[str, Any] | None:
        result = self.brain.project(project_id)
        if result.is_error:
            return None
        data: dict[str, Any] = dict(result.data)
        return data

    def project_objective(self, project_id: str, objective: str, *, reason: str) -> None:
        with self._lock:
            result = self.brain.update(project_id, {"objective": objective}, reason=reason)
        if result.is_error and result.data.get("status") != "unchanged":
            if result.data.get("status") == "missing":
                raise NotFound(result.text)
            raise ValidationFailed(result.text, field="objective")

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
        self,
        *,
        name: str,
        summary: str,
        aliases: list[str],
        proposer: str,
        objective: str = "",
        goals: list[str] | None = None,
    ) -> BrainProject:
        with self._lock:
            result = self.brain.focus_create(
                name, summary, aliases=aliases, objective=objective, goals=goals or []
            )
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

    def preview(
        self,
        request: str,
        *,
        project: str | None = None,
        tools: bool = True,
        include: dict[str, Any] | None = None,
        exclude: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.brain.preview(
            request, focus=project or None, tools=tools, include=include, exclude=exclude
        )
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
        heard: list[str] | None = None,
        made_by: list[str] | None = None,
        capture_origin: str | None = None,
        reason: str | None = None,
    ) -> BrainProposal:
        source = f"{WORKSPACE_SOURCE}{proposer}"
        door = {"capture_origin": capture_origin} if capture_origin else {}
        if sources:
            source += "; sources: " + ", ".join(sources)
        area, _, topic_name = (topic or "").partition("/")
        if kind == "decision" and not revises:
            # Older readers know a decision by its type as well as its kind.
            extra = dict(extra or {}, type="decision")
        if statements.subtype(kind) and not revises:
            # A preference or a convention is a rule of that subtype (one vocabulary).
            extra = dict(extra or {}, subtype=statements.subtype(kind))
        # A must-hold the proposer suggests: the Brain checks its fields like any other.
        extra = dict(extra or {})
        destination = extra.pop("destination", None)
        place = extra.pop("place", None) or {}
        if destination in ("sheet", "progress", "todo"):
            # A sheet value, a progress update or a task: a typed proposal in the same inbox.
            cited = {k: extra.get(k) for k in SOURCE_FIELDS}
            with self._lock:
                result = self.brain.propose_piece(
                    "task" if destination == "todo" else destination,
                    statement,
                    title=title,
                    reason=reason or f"{destination} proposed from the workspace",
                    as_of=extra.get("as_of"),
                    flags={k: True for k in ("customer_facing", "spends") if extra.get(k)},
                    **cited,
                    **place,
                    **door,
                )
            if result.is_error and result.data.get("status") != "duplicate":
                return BrainProposal(status="refused", message=result.text)
            return BrainProposal(
                status=str(result.data.get("status") or "pending"),
                message=result.text,
                proposal_id=result.data.get("proposal_id"),
                checkpoint_id=_checkpoint_id(result.data),
                waits=[str(w) for w in result.data.get("waits") or []],
            )
        must = extra.pop("must_hold", None) or {}
        # Dates the Brain checks like any other field.
        dated = {name: extra.pop(name) for name in ("as_of", "valid_until") if extra.get(name)}
        must_fields: dict[str, Any] = (
            {
                "load": "domain",
                "applies_to": must.get("applies_to") or None,
                "triggers": must.get("triggers") or None,
                "must_text": must.get("must_text") or None,
            }
            if must
            else {}
        )
        with self._lock:
            result = self.brain.propose(
                title=title,
                text=statement,
                # Always one: a change to an entry must not keep the old text's summary.
                summary=summary or summary_from(statement),
                # A change to an entry keeps the entry's kind, scope and place.
                note_kind=None if revises else statements.filed(kind),
                scope=None if revises else scope or None,
                evidence=evidence,
                source=source,
                reason=reason
                or f"{kind} proposed from the workspace"
                + (f", a change to {revises}" if revises else ""),
                force_pending=not capture_origin,
                supersedes=", ".join(replaces or []) or None,
                conflicts=", ".join(contradicts or []) or None,
                area=area or None,
                topic=topic_name or None,
                target_id=revises or None,
                origin=origin,
                extra=extra or None,
                heard=heard,
                made_by=made_by or None,
                **must_fields,
                **dated,
                **door,
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
            checkpoint_id=_checkpoint_id(data),
            waits=[str(w) for w in data.get("waits") or []],
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

    def request(self, packet_id: str) -> dict[str, Any]:
        result = self.brain.request(packet_id)
        if result.is_error:
            raise NotFound(result.text)
        row: dict[str, Any] = dict(result.data)
        seen = self._seen(self.brain.state())
        hidden = any(
            p["kind"] == "note" and p["id"] not in seen
            for key in ("got", "opened")
            for p in row.get(key) or []
        )
        for key in ("got", "opened"):
            row[key] = [p for p in row.get(key) or [] if p["kind"] != "note" or p["id"] in seen]
        found = row.get("why")
        if found:
            # Candidates the owner may not see are left out of "why", as from what it got.
            for key in ("in", "out"):
                found[key] = [
                    r for r in found.get(key) or [] if r["kind"] != "note" or r["item"] in seen
                ]
        if hidden:
            # It was handed notes the owner does not see: its text would show them.
            row["text"] = None
            row["startup"] = None
        return row

    def unsaved(self) -> list[str]:
        return list(self.brain.unsaved())

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

    def kernel(self, *, tools: bool = True) -> dict[str, Any]:
        found = self.brain.kernel(tools=tools)
        return {
            "text": found.text,
            "tokens": int(found.data.get("tokens") or 0),
            "fingerprint": found.data.get("fingerprint"),
            "budget": found.data.get("budget"),
            "layers": list(found.data.get("layers") or []),
            "over_budget": list(found.data.get("over_budget") or []),
        }

    # ---------------------------------------------------------------- measuring

    def record_model_call(self, job: str, model: str, **figures: Any) -> None:
        """A background call the app made to a model, for the jobs line of the cost report.
        Never raises: a call that ran is not undone by a ledger that could not count it."""
        try:
            self.brain.ledger.record_model_call(job, model, **figures)
        except Exception:
            log.warning("Could not record a model call for %s", job, exc_info=True)

    def report(
        self, *, days: int = 7, claude_code: bool = False, quality: bool = True
    ) -> dict[str, Any]:
        """The report card: cost by day and line, brief sizes by type and, with `quality`,
        the eval results. Evals route on a second instance of the Brain, so the app's own
        ledger and its conversations are never touched."""
        from brainkit import costs, report

        folder = costs.default_transcripts() if claude_code else None
        found = report.card(self.brain, days=days, transcripts=folder, quality=False)
        if quality:
            other = Brain(self.vault, embeddings=self.brain.embedder is not None, local_models=True)
            try:
                scored = report.card(other, days=1, quality=True)
            finally:
                other.close()
            for key in ("eval", "private_eval"):
                if key in scored:
                    found[key] = scored[key]
        found["text"] = report.render(found)
        return dict(found)

    def replay(
        self, packet_ids: list[str], *, at: str | None = None, proposal: str | None = None
    ) -> dict[str, Any]:
        from brainkit import replay

        try:
            return dict(replay.replay(self.brain, packet_ids, at=at, proposal=proposal))
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc

    def eval_case(self, packet_id: str) -> dict[str, Any] | None:
        from brainkit import evalset

        found = evalset.case_for(self.brain, packet_id)
        return dict(found) if found else None

    def eval_label(self, packet_id: str, labels: dict[str, Any]) -> dict[str, Any]:
        """The owner's labels for one logged request: it joins the private eval set first if
        it is not in it yet."""
        from brainkit import evalset

        found = self.brain.ledger.packet(packet_id)
        if found is None:
            raise NotFound(f"No logged request {packet_id}.")
        evalset.add(self.brain, str(found.get("request") or ""), packet_id)
        try:
            return dict(evalset.label(self.brain, packet_id, **labels))
        except (KeyError, ValueError) as exc:
            raise ValidationFailed(str(exc)) from exc

    def eval_status(self) -> dict[str, Any]:
        from brainkit import evalset

        return dict(evalset.status(self.brain))

    def calibration_samples(self) -> list[dict[str, Any]]:
        from brainkit import costs

        return [
            dict(s, estimated=brain_util.tokens(s["text"]))
            for s in costs.calibration_samples(self.brain)
        ]

    def set_calibration(self, pairs: list[tuple[int, int]], *, method: str) -> dict[str, Any]:
        from brainkit import costs

        try:
            return dict(costs.set_factor(self.brain.ledger, pairs, method=method))
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc

    # ---------------------------------------------------------------- the knowledge agent

    def agent_outline(self, *, brief: bool = False) -> dict[str, Any]:
        visible = self._seen(self.brain.state())
        return dict(self.brain.agent_outline(brief=brief, visible=visible).data)

    def agent_gather(self, action: str, *, limit: int = 10) -> dict[str, Any]:
        visible = self._seen(self.brain.state())
        result = self.brain.agent_gather(action, limit=limit, visible=visible)
        if result.is_error:
            raise ValidationFailed(result.text, field="action")
        return dict(result.data)

    def agent_skill(self, name: str) -> str:
        result = self.brain.agent_skill(name)
        if result.is_error:
            raise NotFound(result.text, name=name)
        return str(result.data.get("text") or "")

    def agent_skills(self) -> list[dict[str, Any]]:
        return list(self.brain.agent_skills().data.get("skills") or [])

    # ---- Work: agents

    def agents(self, *, archived: bool = False) -> list[dict[str, Any]]:
        return list(self.brain.agents(archived=archived).data.get("agents") or [])

    def agent(self, name: str) -> dict[str, Any] | None:
        result = self.brain.agent(name)
        if result.is_error:
            return None
        return dict(result.data)

    def save_agent(
        self, name: str, fields: dict[str, Any], prompt: str, *, label: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            result = self.brain.save_agent(name, fields, prompt, label=label)
        if result.is_error:
            raise ValidationFailed(result.text, problems=result.data.get("problems") or [])
        return dict(result.data)

    def archive_agent(self, name: str) -> dict[str, Any]:
        with self._lock:
            result = self.brain.archive_agent(name)
        if result.is_error:
            raise NotFound(result.text, name=name)
        return dict(result.data)

    def agent_versions(self, name: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        result = self.brain.agent_versions(name, with_text=with_text)
        if result.is_error:
            return None
        return list(result.data.get("versions") or [])

    def work_skill(self, name: str) -> str | None:
        result = self.brain.work_skill(name)
        return None if result.is_error else str(result.data.get("text") or "")

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

    def ladder(self, *, with_signals: bool = False) -> dict[str, Any]:
        return dict(self.brain.ladder(with_signals=with_signals).data)

    def goal(self, goal_id: str) -> dict[str, Any]:
        result = self.brain.goal(goal_id)
        if result.is_error:
            raise NotFound(result.text, id=goal_id)
        return dict(result.data)

    def goal_cards(self) -> list[dict[str, Any]]:
        return list(self.brain.goal_cards().data.get("cards") or [])

    def act_goal(
        self, action: str, goal_id: str = "", fields: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._lock:
            result = self.brain.act_goal(action, goal_id, fields or {})
        if result.is_error:
            status = result.data.get("status")
            if status == "missing":
                raise NotFound(result.text, id=goal_id)
            if status in ("forbidden", "busy"):
                raise Conflict(result.text)
            raise ValidationFailed(result.text, field=result.data.get("field"))
        return dict(result.data)

    # ---------------------------------------------------------------- State and tasks

    @staticmethod
    def _raise(result: Any, field: str | None = None) -> None:
        status = result.data.get("status")
        if status == "missing":
            raise NotFound(result.text)
        if status in ("exists", "taken", "forbidden", "busy"):
            raise Conflict(result.text)
        raise ValidationFailed(result.text, field=result.data.get("field") or field)

    def state_act(self, action: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            result = self.brain.state_act(action, fields or {})
        if result.is_error:
            self._raise(result)
        return dict(result.data)

    def update_state(
        self, updates: list[dict[str, Any]], *, evidence: str = "", session_id: str = ""
    ) -> dict[str, Any]:
        with self._lock:
            result = self.brain.update_state(
                updates, evidence=evidence, session_id=session_id or None
            )
        if result.is_error:
            self._raise(result)
        return dict(result.data, text=result.text)

    def get_state(self, *, sheet: str = "", row: str = "", query: str = "") -> dict[str, Any]:
        result = self.brain.get_state(sheet=sheet, row=row, query=query)
        return dict(result.data, text=result.text)

    def hand_off(self, **fields: Any) -> dict[str, Any]:
        with self._lock:
            result = self.brain.hand_off(**fields)
        if result.is_error:
            self._raise(result)
        return dict(result.data, text=result.text)

    def tasks(self, **filters: Any) -> list[dict[str, Any]]:
        return list(self.brain.tasks(**filters).data.get("tasks") or [])

    def task(self, task_id: str) -> dict[str, Any]:
        result = self.brain.task(task_id)
        if result.is_error:
            raise NotFound(result.text, id=task_id)
        return dict(result.data)

    def outputs_for(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        from brainkit.activity import normal_path

        wanted = {normal_path(p): p for p in paths}
        found = self.brain.ledger.outputs_for(list(wanted))
        return {wanted[k]: v for k, v in found.items() if k in wanted}

    # ---------------------------------------------------------------- the updating loop

    def agent_tool(self, name: str, args: Any) -> tuple[Any, list[str]]:
        result = self.brain.agent_tool(name, args)
        if result.is_error:
            return None, list(result.data.get("problems") or [result.text])
        return result.data.get("result"), []

    def agent_menu(self) -> str:
        return self.brain.agent_menu().text

    def sweep(self) -> dict[str, Any]:
        with self._lock:
            result = self.brain.sync()
        return dict(result.data, text=result.text)

    def changes_digest(self) -> str:
        return self.brain.changes_digest().text

    def record_agent_run(
        self, run_id: str, action: str, ending: str, record: dict[str, Any]
    ) -> None:
        self.brain.record_agent_run(run_id, action, ending, record)

    def record_episode(self, **fields: Any) -> None:
        self.brain.record_episode(**fields)

    def enrichment_pending(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.brain.enrichment_pending(limit))

    def enrich_note(
        self, entry_id: str, answer: str, *, by: str, expected_version: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            result = self.brain.enrich_note(
                entry_id, answer, by=by, expected_version=expected_version
            )
        return {"ok": not result.is_error, "text": result.text, **dict(result.data)}

    def _governed(self, result: Any) -> dict[str, Any]:
        if result.is_error:
            status = result.data.get("status")
            if status == "missing":
                raise NotFound(result.text)
            if status == "invalid":
                raise ValidationFailed(result.text)
            raise Conflict(result.text)
        return {"text": result.text, **dict(result.data)}

    def set_asked_as(self, entry_id: str, lines: list[str]) -> dict[str, Any]:
        with self._lock:
            return self._governed(self.brain.set_asked_as(entry_id, lines))

    def accept_triggers(self, entry_id: str) -> dict[str, Any]:
        with self._lock:
            return self._governed(self.brain.accept_triggers(entry_id))

    def learn_from_use(self, days: int = 30) -> dict[str, Any]:
        with self._lock:
            return dict(self.brain.learn_from_use(days=days).data)

    def accept_asked_as(self, entry_id: str) -> dict[str, Any]:
        with self._lock:
            return self._governed(self.brain.accept_asked_as(entry_id))

    def loop_status(self) -> dict[str, Any]:
        return dict(self.brain.loop_status().data)

    def correction(self, text: str, *, session_id: str = "", packet_id: str = "") -> dict[str, Any]:
        return dict(self.brain.correction(text, session_id=session_id, packet_id=packet_id).data)

    def close_correction(self, correction_id: int, status: str) -> None:
        result = self.brain.close_correction(correction_id, status)
        if result.is_error:
            raise ValidationFailed(result.text, field="status")

    def check_output(self, text: str, *, sent_back: str = "") -> list[dict[str, Any]]:
        found = self.brain.check_output(text, sent_back=sent_back)
        return list(found.data.get("violations") or [])

    def agent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(self.brain.agent_runs(limit=limit).data.get("runs") or [])

    def blast_radius(self, proposal_id: str) -> dict[str, Any]:
        result = self.brain.blast_radius(proposal_id)
        if result.is_error:
            raise NotFound(result.text)
        return dict(result.data)

    def link_output(self, path: str, *, project: str | None = None, row: str | None = None) -> None:
        from brainkit.activity import normal_path

        with self._lock:
            self.brain.ledger.link_output(normal_path(path), project=project, row_ref=row)

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
            if decision.get("destination"):
                # Kept in another home: its kind, then that home's own fields.
                moved = dict(decision["destination"])
                edits["destination"] = str(moved.pop("destination", ""))
                edits.update({str(k): v for k, v in moved.items() if v not in (None, "")})
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
        out = {"results": result.data["results"], "checkpoint": result.data.get("checkpoint")}
        if result.data.get("commit_error"):
            # live, but not saved to git: the page says so
            out["commit_error"] = result.data["commit_error"]
        return out

    def checkpoints(self, limit: int = 50) -> list[dict[str, Any]]:
        scopes = self.brain.state().scopes
        return [
            dict(point, by=scopes.label(str(point.get("by") or "")))
            for point in self.brain.checkpoints(limit).data.get("checkpoints") or []
        ]

    def undo(self, checkpoint_id: str, *, together: bool = False) -> dict[str, Any]:
        with self._lock:
            result = self.brain.undo(checkpoint_id, together=together)
        if result.is_error:
            if result.data.get("status") == "missing":
                raise NotFound(result.text)
            raise Conflict(
                result.text,
                blocked=result.data.get("blocked") or [],
                dependents=result.data.get("dependents") or [],
            )
        return {"undone": result.data.get("undone"), "checkpoint": result.data.get("checkpoint")}


def _checkpoint_id(data: dict[str, Any]) -> str | None:
    """The undo point of a change that went in at once, when the Brain made one."""
    found = data.get("checkpoint")
    if isinstance(found, dict):
        found = found.get("id")
    return str(found) if found else None


def _revision(meta: dict[str, Any]) -> str | None:
    for key in ("revision", "updated", "added"):
        if meta.get(key):
            return str(meta[key])
    return None


def prompt_words(card_body: str) -> str:
    """A prompt's words as its card keeps them: everything after the card's first line."""
    text = str(card_body or "").replace("\r\n", "\n")
    if text.startswith("Prompt kept word for word"):
        _first, _sep, rest = text.partition("\n\n")
        return rest.strip()
    return text.strip()


def _origin(meta: dict[str, Any], *, project: bool) -> dict[str, Any]:
    """Where a filed item came from: what its card says, else what its card shows (fetched
    for the Library, filed in a project), marked as inferred; else nobody knows (None)."""
    said = str(meta.get("origin") or "").strip()
    if said:
        return {"origin": said, "origin_inferred": False}
    if meta.get("source_url") or meta.get("source_repo") or meta.get("library"):
        return {"origin": "library", "origin_inferred": True}
    if project:
        return {"origin": "project", "origin_inferred": True}
    return {"origin": None, "origin_inferred": False}


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
