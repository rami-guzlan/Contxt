"""What the core needs from outside, as protocols. Adapters implement them structurally.

The Brain is long-term, governed context (files and git, in `packages/brain`). The core never
imports it: the server wires an adapter in, and without one the workspace still works, with
no long-term context in packets and proposals refused with a clear reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from workspace_core.errors import Conflict


@dataclass(frozen=True)
class BrainContext:
    """What the Brain contributes to one task packet."""

    available: bool
    text: str = ""
    entry_ids: list[str] = field(default_factory=list)
    reason: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    # Each entry the packet carries, with the version it carries ({"id", "hash", "tokens"}):
    # what an output built from this packet was built on.
    entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class BrainEntry:
    id: str
    title: str
    text: str
    scope: str
    kind: str
    status: str
    revision: str | None = None
    summary: str = ""
    confidence: str | None = None
    verified: str | None = None
    stale: bool = False
    source: str | None = None
    path: str | None = None
    stale_reason: str | None = None


@dataclass(frozen=True)
class BrainHit:
    id: str
    title: str
    summary: str
    scope: str
    kind: str
    score: float = 0.0


@dataclass(frozen=True)
class BrainDocument:
    """A procedure (skill) or a long reference document held by the Brain."""

    kind: str  # skill | reference
    name: str
    text: str
    loads: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BrainProposal:
    status: str  # pending | applied | duplicate | refused
    message: str
    proposal_id: str | None = None
    entry_id: str | None = None
    # A file filed at once: where it is, which version, what it replaced, how many parts
    # the Brain can quote, its project, and the undo point that takes it back out.
    path: str | None = None
    version: int | None = None
    replaced: str | None = None
    sections: int = 0
    project: str | None = None
    checkpoint_id: str | None = None


@dataclass(frozen=True)
class BrainProject:
    """A piece of work the Brain follows across conversations (a Focus): what it is, where
    it stands, the names people call it, and how many files it holds."""

    id: str
    title: str
    summary: str = ""
    status: str = "active"
    active: bool = True
    current: str = ""
    next: str = ""
    blockers: str = ""
    updated: str | None = None
    aliases: list[str] = field(default_factory=list)
    files: int = 0
    updates: int = 0
    topic: str = ""  # where its notes are filed: "projects/<slug>"


@dataclass(frozen=True)
class BrainEntrySummary:
    """One entry as the catalog lists it: enough to browse, filter and open it."""

    id: str
    title: str
    summary: str
    area: str
    topic: str  # the route key, "area/topic"
    kind: str
    scope: str
    partition: str | None = None  # sealed to one client or campaign
    added: str | None = None
    verified: str | None = None
    confidence: str | None = None
    stale_reason: str | None = None
    standing: bool = False  # delivered with every task, not only when relevant
    file: str | None = None  # the filed reference or asset this entry points at


@dataclass(frozen=True)
class BrainTopic:
    key: str
    label: str
    description: str = ""
    entries: int = 0


@dataclass(frozen=True)
class BrainArea:
    key: str
    label: str
    description: str = ""
    topics: list[BrainTopic] = field(default_factory=list)


@dataclass(frozen=True)
class BrainCatalog:
    """Everything the Brain holds, organized the way its owner files it."""

    areas: list[BrainArea] = field(default_factory=list)
    entries: list[BrainEntrySummary] = field(default_factory=list)


@dataclass(frozen=True)
class BrainFile:
    """A file the Brain holds: a reference document, an asset, or one of a skill's files."""

    path: str  # inside the Brain: references/..., assets/..., skills/...
    kind: str  # reference | asset | skill
    title: str
    size: int
    mime: str
    updated: str | None = None
    description: str = ""
    entry_id: str | None = None  # the entry that routes models to it
    original: str | None = None  # a reference's original file, when the Brain kept it
    # Which copy it is and where it belongs, from its card: a work file (a proposal, a
    # brief) in a project, or a guide kept whole; and how many parts the Brain can quote.
    project: str | None = None
    project_title: str | None = None
    version: int | None = None
    file_status: str | None = None
    dated: str | None = None
    sections: int = 0
    work: bool = False


@dataclass(frozen=True)
class BrainSkill:
    name: str
    category: str
    description: str
    when_to_use: str = ""
    path: str = ""  # its folder
    files: list[BrainFile] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)  # what a person says to ask for it
    artifacts: list[str] = field(default_factory=list)  # what it makes: post, pdf, pptx
    loads: list[str] = field(default_factory=list)  # the topics and documents it reads
    depends_on: list[str] = field(default_factory=list)  # skills whose files it uses
    scope: str = ""
    invocation: str = ""  # "explicit": used only when called by name


@dataclass(frozen=True)
class BrainFiles:
    references: list[BrainFile] = field(default_factory=list)
    assets: list[BrainFile] = field(default_factory=list)
    skills: list[BrainSkill] = field(default_factory=list)


@dataclass(frozen=True)
class BrainFileContent:
    filename: str
    mime: str
    data: bytes


class BrainPort(Protocol):
    def status(self) -> dict[str, Any]: ...

    def context(self, request: str, *, session_id: str | None = None) -> BrainContext: ...

    def search(self, query: str, limit: int = 10) -> list[BrainHit]: ...

    def entry(self, entry_id: str) -> BrainEntry | None: ...

    def skill(self, name: str) -> BrainDocument | None: ...

    def reference(self, path: str) -> BrainDocument | None: ...

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
        revises: str | None = None,  # a new text for this existing entry, not a new entry
        summary: str | None = None,  # one line saying what it holds; derived when missing
        origin: str | None = None,  # where it came from: `doc:<id>@r<n>`, `work:<run>`, `you:`
    ) -> BrainProposal: ...

    def proposals(self) -> list[dict[str, Any]]: ...

    def review(self) -> list[dict[str, Any]]:
        """Each waiting proposal's analysis (by `id`): the entries it replaces, contradicts or
        nearly repeats, other proposals saying the same, and what would make approving it
        go wrong."""
        ...

    def decide_many(
        self,
        decisions: list[dict[str, Any]],
        *,
        label: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Approve, reject and archive as one undo point: {"results", "checkpoint"}. Each
        decision is {"action", "proposal_id" or "entry_id", "reason", "replaces", "topic",
        "title"}."""
        ...

    def checkpoints(self, limit: int = 50) -> list[dict[str, Any]]: ...

    def undo(self, checkpoint_id: str) -> dict[str, Any]:
        """Put back what an undo point changed: {"undone", "checkpoint"} (the undo's own)."""
        ...

    def verify(self, entry_id: str, *, confidence: str | None = None) -> BrainEntry: ...

    def mark(self, entry_id: str, state: str, *, reason: str) -> BrainEntry: ...

    def catalog(self) -> BrainCatalog: ...

    def attention(self) -> dict[str, Any]:
        """What wants a person's eye besides the waiting proposals: clashes, twins, misplaced
        text, notes to re-check, and how many conversations each note went to this week."""
        ...

    def files(self) -> BrainFiles: ...

    def file_content(self, path: str, *, original: bool = False) -> BrainFileContent | None: ...

    def history(self, entry_id: str) -> list[dict[str, Any]]: ...

    def propose_skill(
        self,
        *,
        proposer: str,
        sources: list[str],
        body: str,
        target: str | None = None,  # the skill this is a new version of; else a new skill
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
        """A new skill, or a new version of one: it waits for review (`pending`), or is
        `duplicate` when a proposal for that skill already waits, or `refused`."""
        ...

    def skill_versions(self, name: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        """Every version of a skill's procedure, newest first; None when there is no such
        skill."""
        ...

    def skill_folder(self, name: str) -> str | None:
        """Where a skill's files are on this computer, for a run that works with them; None
        when there is no such skill (or it is not on this computer)."""
        ...

    def skill_source(self, name: str) -> str | None:
        """A skill's procedure exactly as its file holds it (without the frontmatter): what an
        edit to it applies to. None when there is no such skill."""
        ...

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
        """File a document or asset (in a project, as a new version of one already there
        when its name says so). The Brain's capture policy decides whether it is filed at
        once, with an undo point (`status` applied), or waits for review (pending)."""
        ...

    def projects(self) -> list[BrainProject]:
        """Every project the Brain follows, active first, most recently moved first."""
        ...

    def create_project(
        self, *, name: str, summary: str, aliases: list[str], proposer: str
    ) -> BrainProject: ...

    def project(self, project_id: str) -> dict[str, Any] | None:
        """One project in full: what it is for (`brief`), where it stands (`state`), its
        progress `updates` newest first, its `files` and the `notes` filed with it; None when
        there is no such project."""
        ...

    def project_update(
        self, project_id: str, *, summary: str, changes: dict[str, str], evidence: str = ""
    ) -> dict[str, Any]:
        """Record progress on a project: one append-only update, never a rewrite."""
        ...

    def preview(self, request: str, *, project: str | None = None) -> dict[str, Any]:
        """What an AI would be handed for this request, and why each piece is there,
        recording nothing: {"text", "mode", "tokens", "project", "procedure", "notes",
        "sections", "related"}."""
        ...

    # ---- the supply chain: what the Brain holds, where it came from, where it went

    def record_use(self, ref: str, entries: list[dict[str, Any]]) -> None:
        """Count entries handed to AI work (a task run, `ref`) as used."""
        ...

    def inventory(self) -> list[dict[str, Any]]:
        """Every entry (live and archived), skill and filed document, with its owner, origin,
        confidence, review cadence, sensitivity, changes and use."""
        ...

    def entry_details(self, entry_id: str) -> dict[str, Any] | None:
        """One entry's inventory row."""
        ...

    def versions(self, entry_id: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        """Every version of an entry, newest first, each with the changes that made it."""
        ...

    def version(self, entry_id: str, ref: str) -> dict[str, Any] | None: ...

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
        """Governed events, newest first: decisions, edits, checks, restores, undos."""
        ...

    def use(self, entry_id: str, *, days: int = 90) -> dict[str, Any] | None:
        """Where an entry went: daily counts, totals, and the recent handouts."""
        ...

    def gaps(self, *, days: int = 30) -> list[dict[str, Any]]:
        """Requests the Brain served poorly: nothing matched, or routing missed an entry."""
        ...

    def dismiss_gap(self, key: str) -> None: ...

    def flow(self, *, days: int = 7) -> dict[str, Any]:
        """The supply chain over `days`: came in, decided, waiting, handed out, stock health."""
        ...

    def policies(self) -> dict[str, Any]:
        """How the Brain is governed: review cadences, what applies without review, the
        proposal limit per conversation, how long delivery detail is kept, default owner."""
        ...

    def set_policies(self, changes: dict[str, Any]) -> dict[str, Any]: ...

    # ---- keeping up: what happened, what the Brain is for, what it comes with

    def propose_many(self, items: list[dict[str, Any]], *, proposer: str) -> list[BrainProposal]:
        """Many proposals as one change; each item takes `propose`'s keyword arguments (and
        `extra`, details the Brain keeps on the proposal)."""
        ...

    def recap(self, since: str) -> dict[str, Any]:
        """What happened since an ISO moment: what went in on its own (each with the undo point
        that takes it back), what people decided, what came in by source, the projects that
        moved, and how many requests the Brain could not answer."""
        ...

    def weekly(self, weeks: int = 8) -> list[dict[str, Any]]:
        """Conversations the Brain served in each of the last `weeks` weeks, oldest first:
        [{"start", "end", "conversations", "packets"}]."""
        ...

    def kernel(self) -> dict[str, Any]:
        """The startup context every conversation gets once: {"text", "tokens"}."""
        ...

    def made_from(self, path: str) -> dict[str, Any] | None:
        """What a file an AI saved for the person was made from, when it said so: the
        conversation's requests and what each got; None when nothing was recorded."""
        ...

    def work_given(self, run_id: str) -> list[dict[str, Any]]:
        """What one run of the app's AI work was handed from the Brain."""
        ...

    def requests(
        self, *, limit: int = 50, before: str | None = None, client: str | None = None
    ) -> dict[str, Any]:
        """What each AI asked and what it got, newest first: {"requests", "brain_tokens",
        "apps"}; each request with its app, what it got and why, what it opened after, and
        what its conversation saved or suggested."""
        ...

    def goals(self) -> dict[str, Any]:
        """The questions about what the Brain is for, and the owner's answers: {"questions",
        "answers", "exists", "updated", "text"}."""
        ...

    def set_goals(self, answers: dict[str, str]) -> dict[str, Any]:
        """Set the Brain's goals as its owner, as one undo point."""
        ...

    def builtin_skills(self) -> dict[str, Any]:
        """The skills every Brain comes with: {"skills": [{"name", "installed", ...}],
        "missing"}."""
        ...

    def add_builtin_skills(self, names: list[str] | None = None) -> dict[str, Any]:
        """Add the built-in skills the Brain is missing, as one undo point."""
        ...

    def move_in(self, sources: list[dict[str, Any]], *, name: str = "") -> dict[str, Any]:
        """Read what an AI app already knows (memories, instruction files, pasted text) into
        ideas checked against the Brain: {"sources", "ideas", "stages", "examples"}. Writes
        nothing."""
        ...


class NoBrain:
    """The workspace without long-term context. Nothing breaks; nothing is remembered."""

    def status(self) -> dict[str, Any]:
        return {"available": False, "reason": "No Brain is configured for this workspace."}

    def context(self, request: str, *, session_id: str | None = None) -> BrainContext:
        return BrainContext(available=False, reason="No Brain is configured.")

    def search(self, query: str, limit: int = 10) -> list[BrainHit]:
        return []

    def entry(self, entry_id: str) -> BrainEntry | None:
        return None

    def skill(self, name: str) -> BrainDocument | None:
        return None

    def reference(self, path: str) -> BrainDocument | None:
        return None

    def propose(self, **_: Any) -> BrainProposal:
        raise Conflict("This workspace has no Brain to propose long-term context to.")

    def proposals(self) -> list[dict[str, Any]]:
        return []

    def review(self) -> list[dict[str, Any]]:
        return []

    def decide_many(self, decisions: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def checkpoints(self, limit: int = 50) -> list[dict[str, Any]]:
        return []

    def undo(self, checkpoint_id: str) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def verify(self, entry_id: str, *, confidence: str | None = None) -> BrainEntry:
        raise Conflict("This workspace has no Brain.")

    def mark(self, entry_id: str, state: str, *, reason: str) -> BrainEntry:
        raise Conflict("This workspace has no Brain.")

    def catalog(self) -> BrainCatalog:
        return BrainCatalog()

    def attention(self) -> dict[str, Any]:
        return {"clashes": [], "twins": [], "flagged": [], "recheck": [], "usage": {}, "days": 7}

    def files(self) -> BrainFiles:
        return BrainFiles()

    def file_content(self, path: str, *, original: bool = False) -> BrainFileContent | None:
        return None

    def history(self, entry_id: str) -> list[dict[str, Any]]:
        return []

    def propose_skill(self, **_: Any) -> BrainProposal:
        raise Conflict("This workspace has no Brain to keep skills in.")

    def skill_versions(self, name: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        return None

    def skill_folder(self, name: str) -> str | None:
        return None

    def skill_source(self, name: str) -> str | None:
        return None

    def add_file(self, **_: Any) -> BrainProposal:
        raise Conflict("This workspace has no Brain to file documents in.")

    def projects(self) -> list[BrainProject]:
        return []

    def create_project(self, **_: Any) -> BrainProject:
        raise Conflict("This workspace has no Brain to follow projects in.")

    def project(self, project_id: str) -> dict[str, Any] | None:
        return None

    def project_update(self, project_id: str, **_: Any) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to follow projects in.")

    def preview(self, request: str, *, project: str | None = None) -> dict[str, Any]:
        return {
            "text": "",
            "mode": "none",
            "tokens": 0,
            "project": None,
            "procedure": None,
            "notes": [],
            "sections": [],
            "related": [],
            "reason": "No Brain is configured for this workspace.",
        }

    def record_use(self, ref: str, entries: list[dict[str, Any]]) -> None:
        return None

    def inventory(self) -> list[dict[str, Any]]:
        return []

    def entry_details(self, entry_id: str) -> dict[str, Any] | None:
        return None

    def versions(self, entry_id: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        return None

    def version(self, entry_id: str, ref: str) -> dict[str, Any] | None:
        return None

    def activity(self, **_: Any) -> list[dict[str, Any]]:
        return []

    def use(self, entry_id: str, *, days: int = 90) -> dict[str, Any] | None:
        return None

    def gaps(self, *, days: int = 30) -> list[dict[str, Any]]:
        return []

    def dismiss_gap(self, key: str) -> None:
        return None

    def flow(self, *, days: int = 7) -> dict[str, Any]:
        return {"days": days, "came_in": 0, "approved": 0, "rejected": 0, "waiting": 0}

    def policies(self) -> dict[str, Any]:
        return {}

    def set_policies(self, changes: dict[str, Any]) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def propose_many(self, items: list[dict[str, Any]], *, proposer: str) -> list[BrainProposal]:
        raise Conflict("This workspace has no Brain to propose long-term context to.")

    def recap(self, since: str) -> dict[str, Any]:
        return {
            "since": since,
            "went_in": [],
            "went_in_total": 0,
            "decided": {},
            "came_in": {"total": 0, "by_source": {}, "waiting": 0},
            "projects": [],
            "gaps": 0,
        }

    def weekly(self, weeks: int = 8) -> list[dict[str, Any]]:
        return []

    def kernel(self) -> dict[str, Any]:
        return {"text": "", "tokens": 0}

    def made_from(self, path: str) -> dict[str, Any] | None:
        return None

    def work_given(self, run_id: str) -> list[dict[str, Any]]:
        return []

    def requests(
        self, *, limit: int = 50, before: str | None = None, client: str | None = None
    ) -> dict[str, Any]:
        return {"requests": [], "brain_tokens": 0, "apps": []}

    def goals(self) -> dict[str, Any]:
        return {"questions": [], "answers": {}, "exists": False, "updated": None, "text": ""}

    def set_goals(self, answers: dict[str, str]) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep goals in.")

    def builtin_skills(self) -> dict[str, Any]:
        return {"skills": [], "missing": []}

    def add_builtin_skills(self, names: list[str] | None = None) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep skills in.")

    def move_in(self, sources: list[dict[str, Any]], *, name: str = "") -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to move into.")


class TextExtractor(Protocol):
    """Turns an uploaded file into searchable text (its 'text shadow'), or None; and into
    Markdown that keeps its shape (headings, slides, pages, a transcript's turns), or None."""

    def extract(self, data: bytes, filename: str, mime: str | None) -> str | None: ...

    def markdown(self, data: bytes, filename: str) -> str | None: ...
