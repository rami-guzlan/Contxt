"""`Brain`: every brain operation, once, for every adapter.

The MCP server, the CLI, the local HTTP API and any application that embeds the engine all
call this class and nothing below it. Each call returns a `Result` carrying `text` (what a
model reads) and `data` (what software reads).

FRESHNESS IS AUTOMATIC. Each call compares the vault fingerprint (a stat of every content
file, about 20 ms) with the one its in-memory index was built from, and rebuilds when they
differ. A note approved in the UI, a Focus update from another process, or a file edited by
hand is visible on the very next request, with no refresh command.
"""
from __future__ import annotations

import contextlib
import os
import threading
from dataclasses import dataclass

from . import config as config_mod
from . import kernel as kernel_mod
from . import packets as packets_mod
from . import runtime as runtime_mod
from . import systemdocs, util
from .index import Embedder, Index, Reranker, configured_model
from .locking import Busy, WriteLock
from .router import Router
from .scopes import Scopes
from .sessions import Ledger
from .vault import Vault



class Result:
    __slots__ = ("text", "data", "is_error")

    def __init__(self, text, data=None, is_error=False):
        self.text = str(text)
        self.data = data if data is not None else {}
        self.is_error = bool(is_error)

    def __repr__(self):
        return f"Result(is_error={self.is_error}, text={self.text[:60]!r})"

    def as_dict(self):
        return {"text": self.text, "data": self.data, "is_error": self.is_error}


def error(message, **data) -> Result:
    return Result(message, dict(data, status="error"), is_error=True)


@dataclass
class State:
    fingerprint: str
    config: object
    snapshot: object
    index: Index
    scopes: Scopes
    router: Router


class Deferred:
    """Changes written inside `Brain.deferring`, refreshed and committed together."""

    def __init__(self):
        self.paths: list = []
        self.messages: list[str] = []
        self.message: str | None = None  # the batch's own summary, when the caller has one
        self.seen = -1  # vault writes the cached state already reflects
        self.outcome: dict | None = None

    def summary(self) -> str:
        """The commit message: one change keeps its own words ("Approved note.create x"), so
        `git log` still names what changed; several get the batch's summary, then each one."""
        if len(self.messages) == 1:
            return self.messages[0]
        head = self.message or f"{len(self.messages)} changes"
        return head + "\n\n" + "\n".join(f"- {m}" for m in self.messages)


def default_vault() -> str:
    """$BRAIN_VAULT, else ./vault in the working directory."""
    return os.path.abspath(os.environ.get("BRAIN_VAULT") or "vault")


class Brain:
    """One vault, read fresh on every call. Thread-safe for concurrent readers."""

    def __init__(self, vault: str | None = None, principal: str | None = None,
                 embeddings: bool | None = None, repo_root: str | None = None,
                 rerank: bool | None = None, local_models: bool | None = None):
        self.vault = Vault(vault or default_vault())
        self.repo_root = os.path.abspath(repo_root or os.environ.get("BRAIN_REPO_ROOT")
                                         or os.path.dirname(self.vault.root))
        self.default_principal = principal or os.environ.get("BRAIN_PRINCIPAL") or None
        if embeddings is None:
            embeddings = os.environ.get("BRAIN_EMBEDDINGS", "1") not in ("0", "false", "off")
        # No Brain fetches a model on its own, its MCP server included: it uses one already in
        # vault/.brain/models, or matches by words until the owner downloads one (`models
        # --download`, or the app's Settings). BRAIN_LOCAL_MODELS=0 lets it fetch on first use.
        if local_models is None:
            local_models = os.environ.get("BRAIN_LOCAL_MODELS", "1") not in ("0", "false", "off")
        self.embedder = (Embedder(self.vault.runtime_dir, configured_model(self.vault.root),
                                  local_only=local_models)
                         if embeddings else None)
        if rerank is None:
            rerank = os.environ.get("BRAIN_RERANK", "1") not in ("0", "false", "off")
        # The reranker only ever loads a model already in vault/.brain/models; without it,
        # routing is unchanged.
        self.reranker = Reranker(self.vault.runtime_dir) if (embeddings and rerank) else None
        self._state: State | None = None
        self._lock = threading.RLock()
        self._ledger: Ledger | None = None
        self._deferred: Deferred | None = None  # a batch of writes in progress
        # The app this process serves (an MCP client's name from its handshake), recorded
        # on each conversation it starts.
        self.client = ""
        self._write_depth = 0
        self._unsaved: list[str] = []  # why this write's commit failed, if it did
        # Shared with every other process that writes this vault (locking.py).
        self._writes = WriteLock(os.path.join(self.vault.runtime_dir, "write.lock"))

    def close(self) -> None:
        """Release the session ledger connection. Safe to call more than once."""
        if self._ledger is not None:
            self._ledger.close()

    # ------------------------------------------------------------------ state
    def state(self) -> State:
        deferred = self._deferred
        if deferred is not None and self._state is not None and deferred.seen == self.vault.writes:
            # Inside a batch, only the batch writes: nothing changed since the last write.
            return self._state
        listing = self.vault.listing()
        fingerprint = self.vault.fingerprint(listing)
        with self._lock:
            if self._state is None or self._state.fingerprint != fingerprint:
                cfg = config_mod.load(self.vault.root)
                snapshot = self.vault.scan(listing)
                index = Index(snapshot, cfg, self.embedder)
                scopes = Scopes(cfg)
                router = Router(index, cfg, scopes, systemdocs.load(),
                                reranker=self.reranker)
                self._state = State(snapshot.fingerprint, cfg, snapshot, index, scopes, router)
            if deferred is not None:
                deferred.seen = self.vault.writes
            return self._state

    @contextlib.contextmanager
    def deferring(self):
        """Write many changes as one: inside, the index is rebuilt only after a write, and the
        derived files (kernel, git commit) are refreshed once at the end, with the message
        the caller sets on the yielded `Deferred` (else the changes' own messages)."""
        with self.writing():
            if self._deferred is not None:
                yield self._deferred
                return
            current = Deferred()
            self._deferred = current
            try:
                yield current
            finally:
                self._deferred = None
            if current.paths:
                current.outcome = self.after_write(current.paths, current.summary())

    @contextlib.contextmanager
    def writing(self):
        """Hold the vault for one change: no other thread or process writes it meanwhile.
        Every method below that changes the vault runs inside this."""
        self._writes.acquire()
        try:
            yield
        finally:
            self._writes.release()

    def _write(self, run) -> Result:
        """Run one change under the vault's write lock. A vault another process holds for
        too long is an error the caller can retry, not a crash. When the change is live but
        its commit failed, the reply says so (and why), so nobody believes a change is in the
        history when it is not."""
        outermost = self._write_depth == 0
        if outermost:
            self._unsaved = []
        self._write_depth += 1
        try:
            with self.writing():
                result = run()
        except Busy as exc:
            return Result(str(exc), {"status": "busy"}, is_error=True)
        finally:
            self._write_depth -= 1
        if outermost and self._unsaved and isinstance(result, Result):
            reason = " ".join(self._unsaved[-1].split())[:300]
            result.text = (str(result.text).rstrip() + "\n\nThis change is live, but saving it "
                           f"to the brain's git history failed: {reason}. Its history is "
                           "incomplete until the next change saves it; brain_health shows it "
                           "until then.")
            result.data = dict(result.data or {}, saved=False, commit_error=reason)
        return result

    def governed_folders(self) -> list[str]:
        """The vault's governed folders, relative to the repository."""
        from . import gitops
        rel = os.path.relpath(self.vault.root, self.repo_root).replace("\\", "/")
        return [name if rel in (".", "") else f"{rel}/{name}" for name in gitops.GOVERNED]

    def unsaved(self) -> list[str]:
        """Governed files whose changes are live but not in git (a commit that failed), when
        this brain commits its changes."""
        from . import gitops
        if not (self.state().config.data.get("git") or {}).get("auto_commit", True):
            return []
        return gitops.uncommitted(self.repo_root, self.governed_folders())

    @property
    def config(self):
        return self.state().config

    @property
    def ledger(self) -> Ledger:
        if self._ledger is None:
            days = int((self.state().config.data.get("sessions") or {}).get("retention_days")
                       or 90)
            self._ledger = Ledger(os.path.join(self.vault.runtime_dir, "sessions.sqlite"), days)
        return self._ledger

    # ------------------------------------------------------------------ callers
    def principal(self, principal=None, st=None) -> str:
        if principal or self.default_principal:
            return str(principal or self.default_principal)
        return str((st or self.state()).config.owner)

    def caller(self, principal=None, via=None, partition=None, st=None):
        """(chain, partitions) for a caller, or an error Result. Pass `st` to reuse the state
        the calling method already holds, so one request reads the vault fingerprint once."""
        st = st or self.state()
        handle = self.principal(principal, st)
        chain = st.scopes.chain(handle, via=via)
        if chain is None:
            return error(f"Unknown scope or membership: {handle}"
                         + (f" via {via}" if via else ""), scope=handle)
        partitions = st.scopes.partition_chain(partition, chain) if partition else []
        if partitions is None:
            return error(f"Partition {partition} does not exist or is not owned by "
                         f"{' > '.join(chain)}.", scope=handle, partition=partition)
        return chain, partitions

    # ------------------------------------------------------------------ kernel
    def kernel(self, principal=None, via=None, tools=True) -> Result:
        """The startup context. Without `tools`, as a model that cannot call the brain needs
        it: nothing in it asks for a tool (its fingerprint is then of that text)."""
        caller = self.caller(principal, via)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        st = self.state()
        text, fingerprint = kernel_mod.render(st.config, st.index, st.scopes, chain, partitions,
                                              tools=tools)
        return Result(text, {"fingerprint": fingerprint, "scope_chain": chain,
                             "tokens": util.tokens(text),
                             "budget": st.config.budgets.get("kernel_tokens")})

    def write_kernel(self) -> Result:
        """Rewrite CLAUDE.md / AGENTS.md for the owner. Returns what changed."""
        return self._write(self._write_kernel)

    def _write_kernel(self) -> Result:
        st = self.state()
        chain = st.scopes.chain(st.config.owner) or [st.scopes.root()]
        outcome = kernel_mod.write_files(self.repo_root, st.config, st.index, st.scopes, chain)
        return Result(
            ("Kernel files " + (", ".join(outcome["written"]) + " rewritten"
                                if outcome["written"] else "already current")
             + f" (fingerprint {outcome['fingerprint']}, {outcome['tokens']} tokens)."),
            outcome)

    # ------------------------------------------------------------------ the main entry
    def context(self, request, *, principal=None, via=None, partition=None,
                session_id=None, fresh=False, focus=None, task_type=None,
                startup_fingerprint=None, explain=False, record=True,
                include_kernel=None, tools=True) -> Result:
        """Route one request and return one bounded context packet.

        Without `tools`, the packet for a model that cannot call the brain at all: it holds
        nothing from before and cannot continue a session, so nothing in the text asks for a
        tool, the procedure comes in full, and nothing is recorded."""
        if not str(request or "").strip():
            return error("get_task_context needs the request text.")
        st = self.state()
        caller = self.caller(principal, via, partition, st=st)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        session = str(session_id or "").strip()
        continuing = bool(session and Ledger.valid(session))
        if not continuing:
            session = Ledger.mint()
        delivered = self.ledger.delivered(session) if continuing and not fresh else {}
        previous = self.ledger.last_packet(session) if continuing else None
        route = st.router.route(str(request), chain, partitions, focus_override=focus,
                                task_type_override=task_type, previous=previous)
        packet = packets_mod.build(route, config=st.config, index=st.index,
                                   delivered=delivered, fresh=bool(fresh), session_id=session,
                                   partition=partition, explain=explain, tools=tools)
        kernel_text, kernel_fp = kernel_mod.render(st.config, st.index, st.scopes, chain,
                                                   partitions)
        kernel_held = tools and (("kernel", kernel_fp) in delivered or (
            str(startup_fingerprint or "").strip() == kernel_fp))
        if include_kernel is not None:
            kernel_held = not include_kernel
        parts = []
        if not kernel_held and tools:
            parts.append("# Startup context (kernel " + kernel_fp + ")\n\n" + kernel_text)
        elif not kernel_held:
            parts.append("# Startup context\n\n" + kernel_mod.render(
                st.config, st.index, st.scopes, chain, partitions, tools=False)[0])
        parts.append("# Task context\n\n" + packet.text)
        status = "continuing" if continuing else "new"
        if tools:
            parts.append(
                "## Continuity\n\n"
                f"session_id: {session} ({status}). When a later message asks for something "
                "new, call get_task_context again with this session_id; it sends only what is "
                "new. Pass it on every other call too, and fresh=true after a compaction.\n"
                f"kernel: {kernel_fp} ({'current' if kernel_held else 'included above'})\n")
        data = dict(packet.data)
        data.update({"kernel_fingerprint": kernel_fp, "kernel_included": not kernel_held,
                     "session_status": status, "vault_fingerprint": st.fingerprint[:12]})
        if record and tools:
            items = list(packet.items)
            if ("kernel", kernel_fp) not in delivered:
                # Held from now on either way: delivered in this packet, or proven by the
                # fingerprint the client presented. Later calls need not repeat either.
                items.append(("kernel", kernel_fp, kernel_fp,
                              0 if kernel_held else util.tokens(kernel_text)))
            self.ledger.touch(session, chain[-1], label=self.client,
                              engine=runtime_mod.STARTED_WITH)
            self.ledger.record(session, packet.id, str(request), route.mode, packet.text,
                               data, items)
        return Result("\n\n".join(parts), data)

    def preview(self, request, *, principal=None, focus=None, partition=None,
                tools=True) -> Result:
        """What an AI would be handed for this request, and why each piece is there, without
        recording a delivery: the packet as a conversation would get it (its kernel aside) and
        a plain account of the project, procedure, notes and file sections it chose. Without
        `tools`, the packet as a model that cannot call the brain needs it (one side of a
        comparison): nothing in it asks for a tool, and the procedure it would open comes in
        full (`skill_included` names it)."""
        result = self.context(request, principal=principal, focus=focus, partition=partition,
                              explain=True, record=False, include_kernel=False, tools=tools)
        if result.is_error:
            return result
        st = self.state()
        data = result.data
        trace = data.get("trace") or {}
        notes = []
        for row in trace.get("note_scores") or []:
            note = st.index.note(row.get("id"))
            if note is None or row.get("id") not in set(data.get("note_ids") or []):
                continue
            notes.append({"id": note.id, "title": note.title, "kind": note.kind,
                          "topic": note.route_key, "score": row.get("adj", row.get("score")),
                          "why": "house style for writing" if row.get("core") is not None
                          else "relevant to the request"})
        sections = [{"id": row["id"], "file": row["file"], "title": row["title"],
                     "label": row["label"], "score": row["score"],
                     "why": ("in the project it names" if row.get("project") else
                             "names the file" if row.get("named") else
                             "about what the request asks")}
                    for row in trace.get("section_scores") or []
                    if row["id"] in set(data.get("section_ids") or [])]
        focus_id = data.get("focus_id")
        found = st.index.focuses.get(focus_id) if focus_id else None
        text = result.text.split("## Continuity", 1)[0].rstrip() + "\n"
        return Result(text, {
            "request": str(request), "mode": data.get("mode"),
            "tokens": data.get("token_count"),
            "project": ({"id": found.id, "title": found.title} if found is not None else None),
            "procedure": data.get("skill_id"), "candidates": data.get("candidates") or [],
            "skill_included": data.get("skill_included"),
            "notes": notes, "sections": sections,
            "related": data.get("related_ids") or [], "log": trace.get("route_log") or []})

    # ------------------------------------------------------------------ follow-ups
    def skill(self, name, *, principal=None, partition=None, session_id=None) -> Result:
        caller = self.caller(principal, None, partition)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        st = self.state()
        wanted = str(name or "").strip().lstrip("/")
        skill = st.index.skills.get(wanted) or next(
            (s for s in st.index.skills.values()
             if wanted.lower() in [a.lower() for a in [s.name] + s.aliases]), None)
        if skill is None or not Scopes.admits(skill.scope, skill.partition, chain, partitions):
            return error(f"No skill named {wanted!r} is available to {' > '.join(chain)}.",
                         skill=wanted)
        lines = [f"# /{skill.name}", ""]
        if skill.load_topics or skill.load_references:
            lines.append("Loads: " + ", ".join(skill.load_topics + skill.load_references))
        if skill.depends_on:
            lines.append("Depends on: " + ", ".join(skill.depends_on))
        if skill.quality_gates:
            lines.append("Quality gates: " + ", ".join(skill.quality_gates))
        folder = os.path.dirname(skill.path)
        lines.append(f"Folder: vault/{folder} (scripts and assets are resolved from here)")
        lines += ["", skill.body.strip(), ""]
        text = "\n".join(lines)
        if session_id and Ledger.valid(session_id):
            self.ledger.touch(session_id, chain[-1])
            self.ledger.record_items(session_id, "followup",
                                     [("skill", skill.name, skill.body_hash, skill.tokens)])
        return Result(text, {"skill": skill.name, "path": skill.path, "tokens": skill.tokens,
                             "loads": skill.loads, "depends_on": skill.depends_on})

    def skill_versions(self, name, *, limit=30, with_text=False, principal=None,
                       partition=None) -> Result:
        """Every version of a skill's procedure, newest first, from git (history.py)."""
        from . import history
        caller = self.caller(principal, None, partition)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        wanted = str(name or "").strip().lstrip("/")
        skill = self.state().index.skills.get(wanted)
        if skill is None or not Scopes.admits(skill.scope, skill.partition, chain, partitions):
            return error(f"No skill named {wanted!r} is available to {' > '.join(chain)}.",
                         skill=wanted)
        rows = history.skill_versions(self, wanted, limit=limit, with_text=with_text) or []
        return Result("\n".join(f"- {r['ref']} {r['at']}: {r.get('message') or ''}"
                                for r in rows), {"skill": wanted, "versions": rows})

    def reference(self, path, *, session_id=None) -> Result:
        st = self.state()
        wanted = str(path or "").strip().replace("\\", "/")
        if not wanted.startswith("references/"):
            wanted = "references/" + wanted
        ref = st.index.references.get(wanted)
        if ref is None:
            return error(f"No reference document at {wanted}.", path=wanted)
        if session_id and Ledger.valid(session_id):
            self.ledger.record_items(session_id, "followup",
                                     [("reference", ref.path, ref.body_hash, ref.tokens)])
        return Result(ref.body, {"path": ref.path, "title": ref.title, "tokens": ref.tokens})

    def note(self, note_id, *, principal=None, partition=None, include_archived=False,
             session_id=None) -> Result:
        """One note by id or alias. With a session, the delivery is recorded, so later packets
        in that conversation do not send the same text again."""
        st = self.state()
        caller = self.caller(principal, None, partition, st=st)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        note = st.index.note(note_id, include_archived=include_archived)
        replaced = None
        if note is None:
            # A retired note that names its replacement (an old id, or an alias that still
            # points at it) leads to the note that says it now.
            old = st.index.note(note_id, include_archived=True)
            successor = (st.index.note(str(old.meta.get("superseded_by") or ""))
                         if old is not None else None)
            if successor is not None:
                note, replaced = successor, old.id
        if note is None or not Scopes.admits(note.scope, note.partition, chain, partitions):
            return error(f"No note {note_id!r} is visible to {' > '.join(chain)}.",
                         id=note_id)
        if session_id and Ledger.valid(session_id) and note.live:
            self.ledger.touch(session_id, chain[-1])
            self.ledger.record_items(session_id, "followup",
                                     [("note", note.id, note.body_hash, note.tokens)])
        header = f"# {note.id} ({note.route_key}, {note.scope}, {note.status}, {note.load})"
        if note.meta.get("title"):
            header = (f"# {note.title}\n`{note.id}` ({note.route_key}, {note.scope}, "
                      f"{note.status}, {note.load}, added {note.added or 'unknown'})")
        if replaced:
            header += f"\n`{replaced}` was retired; this note replaced it."
        stale = note.stale_reason(util.today_date(), st.config.review_days_for(note))
        if stale:
            header += f"\nStale ({stale}): verify before relying on it."
        if note.confidence:
            header += f"\nConfidence: {note.confidence}."
        return Result(header + "\n\n" + note.body.strip() + "\n",
                      {"id": note.id, "path": note.path, "meta": note.meta,
                       "body": note.body, "route_key": note.route_key, "title": note.title,
                       "summary": note.summary, "kind": note.kind, "added": note.added,
                       "verified": note.verified, "confidence": note.confidence,
                       "stale": stale})

    def search(self, query, *, principal=None, partition=None, limit=12,
               include_archived=False, session_id=None) -> Result:
        """Notes matching a query in the searcher's own words, best first.

        For an agent whose packet lacks something: it can describe what it needs the way it
        understands it ("avoid AI-sounding writing", "UTM parameters for links") and open a
        hit with get_note. With a session, notes it already holds are marked."""
        st = self.state()
        caller = self.caller(principal, None, partition, st=st)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        notes = st.router.admitted_notes(chain, partitions)
        ranked = st.router.score_notes(str(query or ""), notes)
        hits = [s for s in ranked if s.score > 0.05][:int(limit or 12)]
        held = (self.ledger.delivered(session_id)
                if session_id and Ledger.valid(session_id) else {})
        rows = [{"id": s.item.id, "score": s.score, "route_key": s.item.route_key,
                 "scope": s.item.scope, "load": s.item.load, "summary": s.item.summary,
                 "title": s.item.title, "added": s.item.added,
                 "standing": s.item.standing, "focus": st.config.is_focus(s.item),
                 "held": ("note", s.item.id) in held}
                for s in hits]
        if include_archived:
            archived = [n for n in st.index.archived.values()
                        if Scopes.admits(n.scope, n.partition, chain, partitions)]
            q = set(util.content_terms(query))
            rows += [{"id": n.id, "score": 0.0, "route_key": n.route_key, "scope": n.scope,
                      "load": n.load, "summary": n.index_line, "archived": True}
                     for n in archived if q & set(util.terms(n.body))][:5]
        lines = []
        for r in rows:
            marks = [m for m, on in (("in your startup context", r.get("standing")),
                                     ("already in this conversation", r.get("held")),
                                     ("a project's live state", r.get("focus")),
                                     ("archived", r.get("archived"))) if on]
            lines.append(f"- {r.get('title') or r['id']} (`{r['id']}`, {r['route_key']}, "
                         f"{r['score']:.2f})" + (f" [{'; '.join(marks)}]" if marks else "")
                         + f": {r['summary']}")
        # What the brain's files say about it, in parts (sections.py): the searcher reads the
        # whole file with get_reference when a part fits.
        files, per_file = [], {}
        for scored in st.router.score_sections(
                str(query or ""), st.router.admitted_sections(chain, partitions)):
            if len(files) >= 4:
                break
            # A search is asked for: a looser bar than a packet's. By meaning when the
            # embedding model is there, else by the words a section shares with the query.
            semantic = scored.detail.get("semantic")
            if semantic is not None:
                if semantic < 0.5:
                    break
            elif scored.score < 0.45 or scored.detail.get("coverage", 0.0) < 0.35:
                continue
            section = scored.item
            if per_file.get(section.path, 0) >= 2:
                continue
            per_file[section.path] = per_file.get(section.path, 0) + 1
            files.append({"kind": "section", "id": section.id, "path": section.path,
                          "title": st.index.file_title(section.path), "label": section.label,
                          "score": scored.score, "summary": util.excerpt(section.text, 160),
                          "held": ("section", section.id) in held})
        file_lines = [f"- {f['title']}: {f['label']} (`{f['path']}`, {f['score']:.2f})"
                      + (" [already in this conversation]" if f["held"] else "")
                      + f": {f['summary']}" for f in files]
        # Close: the best note would make it into a packet for this as a request, or a file
        # part passed the search's own bar. Otherwise the nearest notes are only nearest.
        close = bool(files) or bool(hits and hits[0].score >= st.router.policy.lean_floor)
        parts = []
        if lines and not close:
            parts.append(f"No close match for {query!r}: the nearest notes, none of them likely "
                         "about it:\n" + "\n".join(lines))
        elif lines:
            parts.append(f"Notes matching {query!r}, best first:\n" + "\n".join(lines)
                         + '\n\nOpen one with get_note(id="...").')
        if file_lines:
            parts.append("In the brain's files:\n" + "\n".join(file_lines)
                         + '\n\nRead a whole file with get_reference(path="...").')
        if parts:
            text = "\n\n".join(parts) + ("\n\nNothing fitting? Try other words: the brain's "
                                         "own terms, or plainer ones.")
        else:
            text = (f"No notes or files match {query!r}. Try other words before concluding "
                    "the brain has nothing on it.")
        return Result(text, {"hits": rows, "files": files, "query": query,
                             "close_match": close})

    def topics(self, *, principal=None) -> Result:
        caller = self.caller(principal)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        st = self.state()
        counts: dict[str, int] = {}
        for note in st.router.admitted_notes(chain, partitions):
            counts[note.route_key] = counts.get(note.route_key, 0) + 1
        rows = []
        config = st.config
        order = {area: i for i, area in enumerate(config.area_order())}
        keys = sorted(set(counts) | set(config.topics),
                      key=lambda k: (order.get(k.split("/")[0], 99), k))
        for key in keys:
            topic = config.topics.get(key)
            area = key.split("/")[0]
            description = topic.description if topic else ""
            if not description:
                focus = next((f for f in st.index.focuses.values()
                              if f.note.route_key == key), None)
                description = f"{focus.title}: {focus.current().get('current')}" if focus else ""
            rows.append({"key": key, "notes": counts.get(key, 0), "area": area,
                         "area_label": config.area_label(area), "description": description})
        return Result("\n".join(f"- {r['key']} ({r['notes']}): {r['description']}"
                                for r in rows), {"topics": rows,
                                                 "areas": [{"key": a,
                                                            "label": config.area_label(a)}
                                                           for a in config.area_order()]})

    def topic(self, route_key, *, principal=None, partition=None) -> Result:
        caller = self.caller(principal, None, partition)
        if isinstance(caller, Result):
            return caller
        chain, partitions = caller
        st = self.state()
        notes = sorted((n for n in st.router.admitted_notes(chain, partitions)
                        if n.route_key == route_key),
                       key=lambda n: (not st.config.is_focus(n), n.added, n.id))
        if not notes:
            return error(f"No visible notes in topic {route_key}.", route_key=route_key)
        text = "\n\n".join(f"### {n.title} (`{n.id}`, {n.scope}, {n.load})\n\n{n.body.strip()}"
                            for n in notes)
        return Result(text, {"route_key": route_key, "ids": [n.id for n in notes],
                             "notes": [{"id": n.id, "title": n.title, "summary": n.summary,
                                        "added": n.added, "kind": n.kind, "scope": n.scope,
                                        "load": n.load, "path": n.path} for n in notes]})

    # ------------------------------------------------------------------ Focus and governance
    def focus_list(self, **kwargs) -> Result:
        from . import focus
        return focus.list_focuses(self, **kwargs)

    def focus_get(self, name, **kwargs) -> Result:
        from . import focus
        return focus.get_focus(self, name, **kwargs)

    def project(self, name, *, principal=None, partition=None) -> Result:
        """One project (a Focus) in full: what it is for, where it stands, its progress
        updates newest first, its files with which copy each is, and the notes filed with
        it."""
        from . import focus as focus_mod
        from .uploads import _as_int
        found, refusal = focus_mod.resolve(self, name, principal, partition)
        if refusal is not None:
            return refusal
        st = self.state()
        cards = st.index.project_files(found)
        card_ids = {card.id for _path, card in cards}
        files = [{"path": path, "id": card.id, "title": st.index.file_title(path),
                  "summary": card.summary, "version": _as_int(card.meta.get("version")),
                  "file_status": card.meta.get("file_status"),
                  "dated": str(card.meta.get("dated") or "")[:10] or None,
                  "filename": card.meta.get("filename"),
                  "sections": len(st.index.file_sections(path))}
                 for path, card in cards]
        files.sort(key=lambda f: (str(f["dated"] or ""), f["path"]), reverse=True)
        notes = [n for n in st.index.notes.values()
                 if n.id != found.id and n.id not in card_ids
                 and (str(n.meta.get("project_id") or "") == found.id
                      or (st.config.uses_areas and n.route_key == found.note.route_key))]
        notes.sort(key=lambda n: (str(n.meta.get("revised") or n.added or ""), n.id),
                   reverse=True)
        state = found.current()
        return Result(found.title, {
            "id": found.id, "title": found.title, "summary": found.note.summary,
            "aliases": list(found.aliases), "status": state.get("status") or "active",
            "active": found.active, "state": state, "brief": found.note.body.strip(),
            "route_key": found.note.route_key,
            "updates": [dict(seq=u.seq, at=u.at, summary=u.summary, changes=u.changes,
                             evidence=u.evidence, actor=u.actor)
                        for u in reversed(found.updates)],
            "files": files,
            "notes": [{"id": n.id, "title": n.title, "summary": n.summary, "kind": n.kind,
                       "type": n.meta.get("type"), "added": n.added} for n in notes]})

    def focus_update(self, focus_name, summary, changes=None, **kwargs) -> Result:
        from . import focus
        return self._write(lambda: focus.record_update(self, focus_name, summary, changes,
                                                       **kwargs))

    def focus_create(self, name, summary, **kwargs) -> Result:
        from . import focus
        return self._write(lambda: focus.create_focus(self, name, summary, **kwargs))

    def propose(self, **kwargs) -> Result:
        from . import governance
        return self._write(lambda: governance.propose_note(self, **kwargs))

    def propose_skill(self, **kwargs) -> Result:
        """Propose a new skill or a change to one, with its files (staged until approved)."""
        from . import uploads
        return self._write(lambda: uploads.propose_skill(self, **kwargs))

    def add_file(self, **kwargs) -> Result:
        """File a document (reference) or asset with its card, or a new version of one; it
        applies at once or waits for review, as the capture policy says (uploads.py)."""
        from . import uploads
        return self._write(lambda: uploads.add_file(self, **kwargs))

    def sync(self, **kwargs) -> Result:
        """File what is new in the configured drop and skill folders."""
        from . import sync
        return self._write(lambda: sync.run(self, **kwargs))

    def remember(self, text, **kwargs) -> Result:
        from . import governance
        return self._write(lambda: governance.remember(self, text, **kwargs))

    def inbox(self, **kwargs) -> Result:
        from . import governance
        return governance.inbox(self, **kwargs)

    def approve(self, proposal_id, **kwargs) -> Result:
        from . import governance
        return self._write(lambda: governance.approve(self, proposal_id, **kwargs))

    def reject(self, proposal_id, reason="", **kwargs) -> Result:
        from . import governance
        return self._write(lambda: governance.reject(self, proposal_id, reason, **kwargs))

    def verify(self, note_id, **kwargs) -> Result:
        """The owner confirms a note is still true today (optionally with a confidence)."""
        from . import governance
        return self._write(lambda: governance.verify(self, note_id, **kwargs))

    def mark(self, note_id, state, **kwargs) -> Result:
        """The owner marks a note stale or disputed, with a reason; it stays, ranked lower."""
        from . import governance
        return self._write(lambda: governance.mark(self, note_id, state, **kwargs))

    def decide(self, decisions, **kwargs) -> Result:
        """The owner approves, rejects and archives in one batch, saved as one undo point."""
        from . import governance
        return self._write(lambda: governance.decide(self, decisions, **kwargs))

    def archive(self, note_id, reason="", **kwargs) -> Result:
        from . import governance
        return self._write(lambda: governance.archive(self, note_id, reason, **kwargs))

    def review(self, **kwargs) -> Result:
        """Every waiting proposal with what it would change: what it replaces, contradicts or
        repeats, in the Brain and among the other proposals."""
        from . import review
        return review.analyze(self, **kwargs)

    def checkpoints(self, limit=50) -> Result:
        from . import checkpoints
        rows = checkpoints.list_checkpoints(self, limit)
        return Result("\n".join(f"- {r['id']} {r['at']}: {r['label']}"
                                + (" (undone)" if r.get("undone_by") else "") for r in rows)
                      or "No undo points yet.", {"checkpoints": rows})

    def undo(self, checkpoint_id, **kwargs) -> Result:
        """Put back what one undo point changed (refused when something changed since)."""
        from . import checkpoints
        return self._write(lambda: checkpoints.undo(self, checkpoint_id, **kwargs))

    def attention(self, days: int = 7) -> Result:
        """What in the brain wants a person's eye besides the waiting proposals: proposals
        that may contradict a live note, live notes that may say the same thing, text that
        does not belong in a note, notes past their review, and how many conversations each
        note went to in the last `days`."""
        import datetime as dt

        from . import review
        st = self.state()
        notes = st.index.notes
        clashes = [
            {"proposal_id": row["id"], "title": row["title"], "entry_id": other["id"],
             "entry_title": other["title"], "why": other.get("contradiction") or ""}
            for row in review.analyze(self).data.get("proposals") or []
            for other in row.get("overlaps") or [] if other.get("may_contradict")]
        twins = [{"a": a, "a_title": notes[a].title, "b": b, "b_title": notes[b].title,
                  "score": score} for a, b, score in review.near_duplicates(st)]
        live = sorted(notes.values(), key=lambda n: n.id)
        flagged = [{"id": n.id, "title": n.title, "why": flag}
                   for n in live for flag in util.text_flags(n.body)]
        today = util.today_date()
        recheck = [{"id": n.id, "title": n.title, "why": why} for n in live
                   if (why := n.stale_reason(today, st.config.review_days_for(n)))]
        since = (util.now() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            usage = self.ledger.usage(since)
        except Exception:
            usage = {}
        went_in = review.went_in_disagreements(self)
        total = len(clashes) + len(twins) + len(flagged) + len(recheck) + len(went_in)
        return Result(f"{total} thing(s) want a look." if total else "Nothing wants a look.",
                      {"clashes": clashes, "twins": twins, "flagged": flagged,
                       "recheck": recheck, "went_in": went_in, "usage": usage, "days": days})

    def pending_checks(self, limit: int = 4) -> Result:
        """Pairs of notes a model should read side by side next (check 3 of the baseline
        check): waiting proposals first, then what went in on its own lately (review.py)."""
        from . import review
        batches = review.pending_checks(self, limit=limit)
        return Result(f"{sum(len(b['pairs']) for b in batches)} pair(s) to read.",
                      {"batches": batches})

    def record_checks(self, verdicts) -> Result:
        """Keep what a model read in pairs of notes: [{"key", "relation", "detail"}]."""
        from . import review
        rows = [v for v in verdicts or [] if isinstance(v, dict)
                and v.get("relation") in review.RELATIONS]
        kept = self.ledger.record_verdicts(rows)
        return Result(f"{kept} verdict(s) kept.", {"kept": kept})

    def apply_scheduled(self, **kwargs) -> Result:
        """Scheduled revisions whose time has come go in (governance.apply_scheduled)."""
        from . import governance
        return self._write(lambda: governance.apply_scheduled(self, **kwargs))

    def health(self) -> Result:
        from . import health
        return health.report(self)

    # ------------------------------------------------------------------ the supply chain
    # What the brain holds, where each entry came from, how it changed, where it went, and
    # where requests found nothing. Reads only, except restore, unarchive, update and the
    # use record (see history.py, inventory.py, governance.py and sessions.py).

    def inventory(self, *, include_archived=True) -> Result:
        """Every entry, skill and filed document, with its details, changes and use."""
        from . import inventory
        rows = inventory.rows(self, include_archived=include_archived)
        live = sum(1 for r in rows if r["type"] == "note" and r["live"])
        return Result(f"{live} live entries, {len(rows) - live} other items.", {"items": rows})

    def entry(self, note_id) -> Result:
        """One entry's inventory row (live or archived), or an error."""
        from . import inventory
        note = self.state().index.note(note_id, include_archived=True)
        if note is None:
            return error(f"No note {note_id!r}.", id=note_id)
        return Result(note.title, inventory.rows(self, notes=[note])[0])

    def versions(self, note_id, *, limit=50, with_text=False) -> Result:
        """Every version of an entry, newest first, each with the changes that made it."""
        from . import history
        rows = history.versions(self, note_id, limit=limit, with_text=with_text)
        if rows is None:
            return error(f"No note {note_id!r}.", id=note_id)
        return Result("\n".join(f"- {r['ref']} {r['at']}: {r.get('message') or r['title']}"
                                for r in rows), {"id": note_id, "versions": rows})

    def version(self, note_id, ref) -> Result:
        """One version of an entry, with its text and details."""
        from . import history
        row = history.version(self, note_id, ref)
        if row is None:
            return error(f"No version {ref!r} of {note_id!r}.", id=note_id, ref=ref)
        return Result(row["body"], row)

    def restore(self, note_id, ref, **kwargs) -> Result:
        """Put an earlier version of an entry back (the owner; an undo point inside decide)."""
        from . import governance
        return self._write(lambda: governance.restore(self, note_id, ref, **kwargs))

    def unarchive(self, note_id, **kwargs) -> Result:
        """Bring an archived or merged entry back (the owner)."""
        from . import governance
        return self._write(lambda: governance.unarchive(self, note_id, **kwargs))

    def update(self, note_id, fields, **kwargs) -> Result:
        """Change an entry's owner, review cadence, sensitivity or place (the owner)."""
        from . import governance
        return self._write(lambda: governance.update(self, note_id, fields, **kwargs))

    def policies(self) -> Result:
        """How this brain is governed (brain.json), defaults filled in."""
        from . import governance
        return Result("Policy.", governance.policies(self))

    def set_policies(self, changes, **kwargs) -> Result:
        """Change the policy (the owner): one undo point, recorded in the journal."""
        from . import governance
        return self._write(lambda: governance.set_policies(self, changes, **kwargs))

    def activity(self, *, note_id=None, since=None, until=None, actions=None, by=None,
                 limit=200) -> Result:
        """Governed events, newest first: proposals decided, edits, checks, restores,
        archives and undos, filtered by entry, time, action and who."""
        from . import history
        rows = history.events(self, note_id, since=since, until=until, actions=actions,
                              by=by, limit=limit)
        return Result(f"{len(rows)} event(s).", {"events": rows})

    def record_use(self, ref, entries, *, principal="workspace") -> Result:
        """Count entries handed to AI work outside a conversation (a workspace task run):
        `entries` is [{"id", "hash"?, "tokens"?}] or ids. Unknown ids are skipped."""
        st = self.state()
        items = []
        for entry in entries or []:
            wanted = entry if isinstance(entry, dict) else {"id": entry}
            note = st.index.note(wanted.get("id"))
            if note is None:
                continue
            items.append(("note", note.id, str(wanted.get("hash") or note.body_hash),
                          int(wanted.get("tokens") or note.tokens), "in an AI work packet"))
        if not items:
            return Result("Nothing to record.", {"recorded": 0})
        session = self.ledger.record_use(str(ref), items, principal=principal)
        return Result(f"Recorded {len(items)} entries for {ref}.",
                      {"recorded": len(items), "session_id": session})

    def use(self, item_id, *, days=90, kind="note") -> Result:
        """Where one entry (or skill, or filed document) went: daily counts, totals and the
        recent handouts still in the detail window."""
        if kind == "note":
            note = self.state().index.note(item_id, include_archived=True)
            if note is None:
                return error(f"No note {item_id!r}.", id=item_id)
            item_id = note.id
        data = self.ledger.item_usage(kind, item_id, days=days)
        totals = self.ledger.usage_table(kind).get((kind, item_id)) or {}
        data.update(id=item_id, kind=kind, totals=totals)
        return Result(f"{totals.get('total', 0)} use(s) of {item_id}.", data)

    def gaps(self, *, days=30) -> Result:
        """Requests the brain served poorly in the last `days` days (Ledger.gaps), with the
        titles of the entries they name."""
        import datetime as dt
        since = (util.now() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = self.ledger.gaps(since)
        st = self.state()
        for row in rows:
            note = st.index.note(row["entry"]) if row.get("entry") else None
            row["entry_title"] = note.title if note is not None else None
            row["entry_summary"] = note.summary if note is not None else None
            row["close"] = [{"id": n.id, "title": n.title}
                            for n in (st.index.note(i) for i in row.get("close") or [])
                            if n is not None]
        return Result(f"{len(rows)} gap(s).", {"gaps": rows, "days": days})

    def dismiss_gap(self, key) -> Result:
        """Hide one gap from later lists (an off-topic request, say)."""
        self.ledger.dismiss(str(key))
        return Result("Dismissed.", {"key": str(key)})

    def flow(self, *, days=7) -> Result:
        """The last `days` days in the supply chain: what came in, what was decided, what
        waits, what was handed out, and the health of what the brain holds."""
        import datetime as dt
        st = self.state()
        since = (util.now() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        decided: dict[str, int] = {}
        for record in self.vault.decisions():
            if str(record.get("at") or "") >= since:
                action = str(record.get("action") or "")
                decided[action] = decided.get(action, 0) + 1
        waiting = sorted(st.snapshot.proposals.values(), key=lambda p: p.created)
        came_in = sum(1 for p in waiting if p.created >= since) + sum(
            decided.get(a, 0) for a in ("approved", "auto-applied", "rejected"))
        try:
            delivery = self.ledger.flow(since)
            used = self.ledger.usage_table("note")
            first = self.ledger.first_day()
        except Exception:  # an unreadable ledger costs the delivery numbers only
            delivery, used, first = {}, {}, None
        today = util.today_date()
        live = list(st.index.notes.values())
        cutoff = (today - dt.timedelta(days=59)).isoformat()
        # Use is known only since the ledger began counting: "unused" means unused since then.
        recorded_since = first or today.isoformat()
        idle = [n.id for n in live
                if str((used.get(("note", n.id)) or {}).get("last") or "") < cutoff
                and (n.added or "") < cutoff]
        return Result(f"{came_in} came in, {len(waiting)} waiting.", {
            "days": days, "since": since, "came_in": came_in,
            "approved": decided.get("approved", 0) + decided.get("auto-applied", 0),
            "rejected": decided.get("rejected", 0), "decided": decided,
            "waiting": len(waiting),
            "oldest_waiting": waiting[0].created if waiting else None,
            "delivery": delivery,
            "usage_since": recorded_since,
            "stock": {
                "live": len(live),
                "due": sum(1 for n in live
                           if n.stale_reason(today, st.config.review_days_for(n))),
                "disputed": sum(1 for n in live if n.confidence == "disputed"),
                "unused_60_days": len(idle),
                "standing_tokens": sum(n.tokens for n in live if n.standing),
            }})

    def requests(self, *, limit=50, before=None, client=None, session=None) -> Result:
        """What each AI asked and what it got, newest first (activity.py)."""
        from . import activity
        return activity.requests(self, limit=limit, before=before, client=client,
                                 session=session)

    def record_output(self, path, *, title="", session_id=None) -> Result:
        """Note a file an AI saved for the person, with the conversation it was made in."""
        from . import activity
        return activity.record_output(self, path, title=title, session_id=session_id)

    def made_from(self, path) -> Result:
        """What a saved file was made from, when an AI recorded it (activity.py)."""
        from . import activity
        found = activity.made_from(self, path)
        return Result("Nothing was recorded for that file." if found is None else
                      f"Made in {found['app']}.", {"found": found})

    def work_given(self, run_id) -> Result:
        """What one run of the app's AI work was handed from the brain."""
        from . import activity
        return Result("Handed to the run.", {"pieces": activity.work_given(self, run_id)})

    def weekly(self, weeks=8) -> Result:
        """Conversations served in each of the last `weeks` weeks, oldest first."""
        try:
            rows = self.ledger.weekly(weeks)
        except Exception:  # an unreadable ledger costs the bars, not the page
            rows = []
        total = sum(r["conversations"] for r in rows)
        return Result(f"{total} conversation(s) in {len(rows)} week(s).", {"weeks": rows})

    def recap(self, since) -> Result:
        """What happened since an ISO moment: what went in on its own (with the undo point
        that takes each back), what people decided, what came in by source, the projects that
        moved, and the questions the brain could not answer (recap.py)."""
        from . import recap
        return recap.since(self, since)

    def builtin_skills(self) -> Result:
        """The skills every brain comes with, and whether this one has each (builtin.py)."""
        from . import builtin
        have = set(self.state().index.skills)
        rows = [{"name": s["name"], "category": s["category"], "description": s["description"],
                 "installed": s["name"] in have} for s in builtin.available()]
        missing = [r["name"] for r in rows if not r["installed"]]
        return Result(f"{len(rows) - len(missing)} of {len(rows)} built-in skills.",
                      {"skills": rows, "missing": missing})

    def add_builtin_skills(self, names=None, **kwargs) -> Result:
        """Add the built-in skills this brain is missing, as one undo point (builtin.py)."""
        from . import builtin
        return self._write(lambda: builtin.install(self, names=names, **kwargs))

    def goals(self) -> Result:
        """The questions about what this brain is for, and the owner's answers (goals.py)."""
        from . import goals
        found = goals.read(self)
        return Result(found["text"] or "No goals yet.", found)

    def set_goals(self, answers, **kwargs) -> Result:
        """The owner sets the brain's goals: the purpose (standing) and every answer, one undo
        point (goals.py)."""
        from . import goals
        return self._write(lambda: goals.write(self, answers, **kwargs))

    def move_in(self, sources, *, name="", principal=None) -> Result:
        """Read what an AI app already knows (a memory list, an instruction file, pasted text)
        into ideas checked against the brain. Writes nothing (movein.py)."""
        from . import movein
        return movein.analyze(self, sources, name=name, principal=principal)

    # ------------------------------------------------------------------ after writes
    def after_write(self, paths, message) -> dict:
        """Refresh derived files and record the change in git, per brain.json policy. Inside
        `deferring`, the change is only noted, for one refresh when the batch ends."""
        from . import gitops
        if self._deferred is not None:
            self._deferred.paths += [p for p in paths if p]
            self._deferred.messages.append(str(message))
            return {"kernel": None, "commit": None, "deferred": True}
        kernel_outcome = self.write_kernel().data
        commit = None
        if (self.state().config.data.get("git") or {}).get("auto_commit", True):
            # What an earlier failed commit left unsaved goes with this one: a retry.
            earlier = gitops.uncommitted(self.repo_root, self.governed_folders())
            commit = gitops.commit(self.repo_root, list(paths) + [
                os.path.join(self.repo_root, name) for name in kernel_outcome.get("written", [])]
                + [os.path.join(self.repo_root, p) for p in earlier], message)
            if commit and commit.get("failed"):
                reason = str(commit.get("reason") or "git failed")
                self._unsaved.append(reason)
                self.vault.append_decision({
                    "at": util.now_iso(), "action": "unsaved", "reason": reason[:500],
                    "message": str(message)[:300],
                    "paths": [os.path.relpath(p, self.repo_root).replace("\\", "/")
                              for p in paths if p][:50]})
        return {"kernel": kernel_outcome, "commit": commit}
