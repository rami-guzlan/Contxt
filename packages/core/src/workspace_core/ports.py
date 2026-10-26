"""What the core needs from outside, as protocols. Adapters implement them structurally.

The Brain is long-term, governed context (files and git, in `packages/brain`). The core never
imports it: the server wires an adapter in, and without one the workspace still works, with
no long-term context in packets and proposals refused with a clear reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from workspace_core.errors import Conflict, NotFound


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
    said_by: str | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class BrainHit:
    id: str
    title: str
    summary: str
    scope: str
    kind: str
    score: float = 0.0
    excerpt: str = ""


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
    # Why a change still waits for the owner in Auto ("must-hold", "private", ...).
    waits: list[str] = field(default_factory=list)


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
    objective: str = ""  # the output it is chasing; it opens every brief in the project
    goals: list[str] = field(default_factory=list)  # the goals it serves


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
    # In the Library, from its card: what kind of item it is (guide, reference, influence),
    # where it was fetched from (a page, or a repository and the files picked from it), when,
    # and how often it is fetched again (never, weekly, monthly).
    library: str | None = None
    source_url: str | None = None
    source_repo: str | None = None
    source_paths: tuple[str, ...] = ()
    fetched_at: str | None = None
    refresh: str | None = None
    # Where it came from, as its card says (`capture:recording`, `library`, `run:<id>`), or as
    # inferred for a file filed before cards kept it (`inferred`); None when nobody knows.
    origin: str | None = None
    origin_inferred: bool = False
    scope: str | None = None


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

    def search(
        self, query: str, limit: int = 10, *, include_archived: bool = False
    ) -> list[BrainHit]: ...

    def entry(self, entry_id: str, *, include_archived: bool = False) -> BrainEntry | None: ...

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
        # More front matter: who said it, the goal or project it serves, a must-hold's fields.
        extra: dict[str, Any] | None = None,
        # What AI work proposing it read (its run's inputs): the quotes in `evidence` must
        # come from there, as a chat's must come from what the person said.
        heard: list[str] | None = None,
        # The runs that made the outputs it cites (`work:<run>`): what only repeats the brief
        # one of them was handed cannot be promoted from its output (circular evidence).
        made_by: list[str] | None = None,
        # Who brought it to the door (`app`, `chat`, `folder`, `connector`): governance says
        # whether it goes in with undo or waits.
        capture_origin: str | None = None,
        # Why it is proposed, in plain words: what an Auto change records as its reason.
        reason: str | None = None,
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

    def undo(self, checkpoint_id: str, *, together: bool = False) -> dict[str, Any]:
        """Put back what an undo point changed: {"undone", "checkpoint"} (the undo's own).
        When later decisions changed the same entries it refuses and names them, unless
        `together`, which undoes them too, newest first."""
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
        files: list[dict[str, Any]] | None = None,
        depends_on: list[str] | None = None,
    ) -> BrainProposal:
        """A new skill, or a new version of one: it waits for review (`pending`), or is
        `duplicate` when a proposal for that skill already waits, or `refused`. `files` are
        the skill's own files ({"path", "content_base64"}), beside its SKILL.md."""
        ...

    def skill_versions(self, name: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        """Every version of a skill's procedure, newest first; None when there is no such
        skill."""
        ...

    def skill_freshness(self, name: str) -> dict[str, Any] | None:
        """When the skill was last edited, and what it loads (notes, documents) that changed
        since: {"last_edited", "changed": [{"key", "title", "at"}]}; None when there is no
        such skill."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Vectors for `texts` from the Brain's local model, to compare by meaning; None
        when no model is here (callers then compare by words)."""
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
        wait: bool = False,
        library: dict[str, Any] | None = None,
        replaces: str | None = None,
        came_from: str | None = None,
    ) -> BrainProposal:
        """File a document or asset (in a project, as a new version of one already there
        when its name says so, or of the one `replaces` names). The Brain's capture policy
        decides whether it is filed at once, with an undo point (`status` applied), or waits
        for review (pending); `wait` makes it wait whatever the policy says. `library` gives
        it its Library fields on its card; `came_from` says where it came from
        (`capture:recording`, `movein`, `run:<id>`), kept on its card as its origin."""
        ...

    def projects(self) -> list[BrainProject]:
        """Every project the Brain follows, active first, most recently moved first."""
        ...

    def create_project(
        self,
        *,
        name: str,
        summary: str,
        aliases: list[str],
        proposer: str,
        objective: str = "",
        goals: list[str] | None = None,
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

    def project_objective(self, project_id: str, objective: str, *, reason: str) -> None:
        """Change a project's objective (it reaches every brief in the project): a reason
        and an undo point, like the rest of its baseline."""
        ...

    def preview(
        self,
        request: str,
        *,
        project: str | None = None,
        tools: bool = True,
        include: dict[str, Any] | None = None,
        exclude: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """What an AI would be handed for this request, and why each piece is there,
        recording nothing: {"text", "mode", "tokens", "project", "procedure", "notes",
        "sections", "related", "skill_included"}. Without `tools`, as a model that cannot
        call the Brain needs it: nothing in the text asks for a tool, and the procedure it
        would open comes in full (`skill_included` names it)."""
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

    def prompts(self, *, archived: bool = False) -> list[dict[str, Any]]:
        """The prompts kept in the Library that the owner may see, newest first: {"id",
        "path", "title", "body" (the words exactly), "tags", "picks", "project",
        "project_title", "version", "added", "updated", "origin", "scope", "archived",
        "attachments"}."""
        ...

    def prompt(self, prompt_id: str) -> dict[str, Any] | None:
        """One prompt, live or set aside, with "versions" of its words, newest first."""
        ...

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

    def indexed(self, ids: list[str]) -> set[str]:
        """The entries among `ids` the Brain's search index holds now: a kept entry is not
        searchable until it does."""
        ...

    def receipt(self, packet_id: str) -> dict[str, Any] | None:
        """One request's evidence receipt, exactly as delivered, or None."""
        ...

    def requests_in(self, session_id: str) -> list[dict[str, Any]]:
        """The requests one conversation made, oldest first: an answer's receipts."""
        ...

    def taste(self) -> dict[str, Any]:
        """The owner's taste, by lens (brainkit taste.py)."""
        ...

    def propose_taste(self, text: str, **fields: Any) -> dict[str, Any]:
        """Propose one taste entry; it waits or applies as governance says."""
        ...

    def learned(self) -> list[dict[str, Any]]:
        """The "ask first" rules the owner's undos taught."""
        ...

    def forget_learned(self, rule_id: str) -> dict[str, Any]: ...

    def brain_map(
        self, *, area: str | None = None, page: int = 1, tier: str | None = None
    ) -> dict[str, Any]:
        """The whole Brain map, paged, or one tier whole (brainkit brainmap.py)."""
        ...

    def relevance(self, goal: str, texts: list[str]) -> list[float | None] | None:
        """Each text's meaning score against a goal, by the Brain's local meaning model (no
        call out); None when no meaning model is here."""
        ...

    def map_view(self) -> dict[str, Any]:
        """The map card: every tier, the short map as sent, what it cut, sealed projects."""
        ...

    def sections(self, item_id: str) -> dict[str, Any]:
        """Every section address in one note, lesson or file."""
        ...

    def open_address(self, address: str) -> dict[str, Any]:
        """One part by its address (note-id#heading, file#section, lore_id#story)."""
        ...

    def lore(self) -> list[dict[str, Any]]:
        """Every lesson, with its level and address."""
        ...

    def lesson(self, lesson_id: str) -> dict[str, Any]: ...

    def propose_lesson(self, **fields: Any) -> dict[str, Any]:
        """A lesson, proposed through governance like any other note."""
        ...

    def sessions_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Past conversations whose receipts match: id, date, app, what it was given."""
        ...

    def correct(
        self, packet_id: str, kind: str, *, item: str = "", note: str = ""
    ) -> dict[str, Any]:
        """A correction made from a receipt, of one kind; it only proposes (corrections.py):
        {"outcome": "challenge" | "recorded", "proposal_id"?}."""
        ...

    def brain_versions(self) -> list[dict[str, Any]]:
        """The Brain's versions, oldest first (git tags gnomon/v<N>)."""
        ...

    def bench_files(self) -> dict[str, str]:
        """The Test Bench's tests and suites as YAML text, by path (bench/<suite>/...)."""
        ...

    def commit_sheets(self, message: str) -> dict[str, Any]:
        """Commit the context sheets' database and snapshots (once per beat or day)."""
        ...

    def world_draft(self) -> dict[str, Any]:
        """{due, prompt, regions}: whether the world overview needs a draft, and the prompt."""
        ...

    def propose_world(self, text: str, regions: dict[str, Any]) -> dict[str, Any]:
        """A drafted world overview as a proposal that waits for the owner."""
        ...

    def bench_write(self, rel: str, text: str | None, *, message: str) -> dict[str, Any]:
        """Write one bench file (or remove it, with `text` None) and commit it."""
        ...

    def save_version(self, *, cause: str = "manual", note: str = "") -> dict[str, Any]:
        """Make a version of the Brain as it is: {"status", "version"}."""
        ...

    def version_diff(self, a: str, b: str) -> dict[str, Any]:
        """Entries added, changed and removed between two versions, and sheet cells."""
        ...

    def restore_version(self, version: str, *, ids: list[str] | None = None) -> dict[str, Any]:
        """Chosen entries as they were at a version, as a new version; refused when an entry
        changed since the last version."""
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

    def kernel(self, *, tools: bool = True) -> dict[str, Any]:
        """The startup context every conversation gets once: {"text", "tokens", "fingerprint",
        "budget", "layers" (each {"name", "scopes", "tokens", "budget"}), "over_budget"}.
        Without `tools`, as a model that cannot call the Brain needs it: nothing asks for a
        tool."""
        ...

    # ---- measuring: what context costs and how good briefs are

    def record_model_call(self, job: str, model: str, **figures: Any) -> None:
        """A background call the app made to a model (tokens_in, tokens_out, cache_read,
        cache_write, cost, ms, ref, measured), for the cost report. Never raises."""
        ...

    def report(
        self, *, days: int = 7, claude_code: bool = False, quality: bool = True
    ) -> dict[str, Any]:
        """The report card: cost by day and line, brief sizes by request type, eval results
        and the private eval set's status; `text` is it in words."""
        ...

    def replay(
        self, packet_ids: list[str], *, at: str | None = None, proposal: str | None = None
    ) -> dict[str, Any]:
        """Logged briefs rebuilt against the Brain now, at a git ref, or with a proposal
        applied in a copy, each with what entered, left or moved."""
        ...

    def eval_case(self, packet_id: str) -> dict[str, Any] | None:
        """A logged request's place in the private eval set, with its labels; None if absent."""
        ...

    def eval_label(self, packet_id: str, labels: dict[str, Any]) -> dict[str, Any]:
        """Label a logged request (needed, useful, noise, missing note ids, and `nothing`: it
        should get nothing) for the eval set."""
        ...

    def eval_status(self) -> dict[str, Any]:
        """How many requests the private eval set holds and how many are labeled."""
        ...

    def calibration_samples(self) -> list[dict[str, Any]]:
        """Texts the Brain really sends (the kernel, recent briefs), with their estimated
        token counts, to measure against the model's own tokenizer."""
        ...

    def set_calibration(self, pairs: list[tuple[int, int]], *, method: str) -> dict[str, Any]:
        """Store the factor from (estimated, measured) token counts of the same texts."""
        ...

    def agent_outline(self, *, brief: bool = False) -> dict[str, Any]:
        """The knowledge agent's map of what the owner may see, made by code: {"counts",
        "goals", "areas", "projects", "skills", "text"}; `brief` for a small model."""
        ...

    def agent_gather(self, action: str, *, limit: int = 10) -> dict[str, Any]:
        """What one knowledge agent action judges: {"action", "candidates": [{"ref", "kind",
        "ids", "title", "text"}], "found"}."""
        ...

    def agent_skill(self, name: str) -> str:
        """The procedure one knowledge agent action (or its conversation) follows."""
        ...

    def agent_skills(self) -> list[dict[str, Any]]:
        """The knowledge agent's procedures: [{"name", "description", "when_to_use",
        "triggers", "text", "own"}]."""
        ...

    # ---- Work: agents, roles kept in the Brain (agents/<name>/AGENT.md)

    def agents(self, *, archived: bool = False) -> list[dict[str, Any]]:
        """The agents the owner defined, each its role, pointers and operating prompt."""
        ...

    def agent(self, name: str) -> dict[str, Any] | None:
        """One agent: {"agent", "resolved" (each pointer as it is now, and what no longer
        resolves), "prompt" (its role as a model gets it)}; None when there is no such agent."""
        ...

    def save_agent(
        self, name: str, fields: dict[str, Any], prompt: str, *, label: str | None = None
    ) -> dict[str, Any]:
        """Create or change an agent as the owner: applied at once, one undo point. Raises
        ValidationFailed with the Brain's words when the role is not right."""
        ...

    def archive_agent(self, name: str) -> dict[str, Any]:
        """Hide an agent; its file stays, with an undo point."""
        ...

    def agent_versions(self, name: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        """Every saved version of an agent, newest first; None when there is no such agent."""
        ...

    def work_skill(self, name: str) -> str | None:
        """A procedure Work follows with a model (agent-builder, prompt-improver)."""
        ...

    def unsaved(self) -> list[str]:
        """Governed files whose changes are live but not saved to git (a commit failed)."""
        ...

    def models(self) -> dict[str, Any]:
        """The local model that matches by meaning: whether it is here or being fetched."""
        ...

    def download_models(self) -> dict[str, Any]:
        """Fetch the matching model in the background (the owner's call, never automatic)."""
        ...

    def skills_history(self, names: list[str]) -> dict[str, dict[str, Any]]:
        """Each skill's version hashes (newest first), last edit and what it loads that
        changed since, for the Skills page: {name: {"hashes", "last_edited", "changed"}}."""
        ...

    def holds_text(self, fingerprints: list[str]) -> set[str]:
        """Which of these text fingerprints (statements.fingerprint) a live note already
        says word for word: hash dedupe before any model reads them."""
        ...

    def local_models(self) -> dict[str, Any]:
        """This computer's local models (brain-logic plan 5.11.16): the machine and its setup,
        each role's model and pinned options, and whether the engine runs in full."""
        ...

    def act_local_models(
        self, action: str, name: str = "", on: bool | None = None
    ) -> dict[str, Any]:
        """check | default | download | remove | speed | claude_code; returns local_models()
        with a `notice` (a warning that does not refuse)."""
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

    def request(self, packet_id: str) -> dict[str, Any]:
        """One request in full: what `requests` says of it, the exact text it was handed
        (`text`), and the startup context when it went with it (`startup`: {"fingerprint",
        "text"}, the text None when it was not kept). NotFound past the retention window."""
        ...

    def goals(self) -> dict[str, Any]:
        """The questions about what the Brain is for, and the owner's answers: {"questions",
        "answers", "exists", "updated", "text"}."""
        ...

    def set_goals(self, answers: dict[str, str]) -> dict[str, Any]:
        """Set the Brain's goals as its owner, as one undo point."""
        ...

    def ladder(self, *, with_signals: bool = False) -> dict[str, Any]:
        """The goal ladder (brainkit/ladder.py): {"purpose", "yours", "agents", "has_goals",
        "check_ins_due", "starters", "signals"}; the signal library (each signal's value now,
        for the measure picker) only `with_signals`."""
        ...

    def goal(self, goal_id: str) -> dict[str, Any]:
        """One goal in full: its checks, journal, shared plan and `context` (what an AI
        receives). NotFound when there is no such goal."""
        ...

    def goal_cards(self) -> list[dict[str, Any]]:
        """Agent goals that slipped: one card per slip, until the goal recovers."""
        ...

    def act_goal(
        self, action: str, goal_id: str = "", fields: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """set | change | check_in | note | plan | starters | link | check
        (brainkit/ladder.py)."""
        ...

    # ---- State (BL 8) and tasks (goals plan 5)

    def state_act(self, action: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        """The owner's State actions (brainkit/state.py): sheets, templates, rows, history,
        waiting, promotions; create_sheet, add_column, add_row, write, touch, decide,
        remove_row. NotFound, Conflict or ValidationFailed on a refusal."""
        ...

    def update_state(
        self, updates: list[dict[str, Any]], *, evidence: str = "", session_id: str = ""
    ) -> dict[str, Any]:
        """An AI's cell updates through the app's runs: {"text", "results"}."""
        ...

    def get_state(self, *, sheet: str = "", row: str = "", query: str = "") -> dict[str, Any]:
        """State as an AI reads it: {"text", ...}."""
        ...

    def hand_off(self, **fields: Any) -> dict[str, Any]:
        """Take, save, pass on or finish a task, or add a goal note (brainkit/handoff.py):
        {"task", "card", "owner", "task_status"}. ValidationFailed with how to fix the
        call."""
        ...

    def tasks(self, **filters: Any) -> list[dict[str, Any]]:
        """Tasks from the Tasks sheet, filtered by owner, status, goal or project."""
        ...

    def task(self, task_id: str) -> dict[str, Any]:
        """One task with its card, its rendered card and its log. NotFound without one."""
        ...

    def outputs_for(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        """What the Brain recorded for these output files (by absolute path): the project,
        the State row, who made it, the conversation."""
        ...

    # ---- the updating loop (BL 9) and the local knowledge agent (BL 17)

    def agent_tool(self, name: str, args: Any) -> tuple[Any, list[str]]:
        """Run one of the knowledge agent's tools: (its result, the problems that refused
        it)."""
        ...

    def agent_menu(self) -> str:
        """The agent's tools, one line each, for its core prompt."""
        ...

    def sweep(self) -> dict[str, Any]:
        """File what is new in the watched folders (an ingestion step): {"text", ...}."""
        ...

    def changes_digest(self) -> str:
        """What changed lately, by area, in a line (the map carries it)."""
        ...

    def record_agent_run(
        self, run_id: str, action: str, ending: str, record: dict[str, Any]
    ) -> None:
        """Keep a job's run record (BL 17.8), credentials masked."""
        ...

    def record_episode(self, **fields: Any) -> None:
        """One agent suggestion and the person's decision (BL 17.6)."""
        ...

    def enrichment_pending(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Entries whose retrieval lines a model has yet to write: id, title, prompt and version
        (general-retrieval plan 3.1)."""
        ...

    def enrich_note(
        self, entry_id: str, answer: str, *, by: str, expected_version: str | None = None
    ) -> dict[str, Any]:
        """Write one model answer into its entry; `ok` false, with `text`, when unusable."""
        ...

    def set_asked_as(self, entry_id: str, lines: list[str]) -> dict[str, Any]:
        """The owner's own wording of how an entry is asked for."""
        ...

    def accept_triggers(self, entry_id: str) -> dict[str, Any]:
        """The owner's yes to the trigger words suggested for a must-hold."""
        ...

    def learn_from_use(self, days: int = 30) -> dict[str, Any]:
        """Teach each entry a conversation had to search for the words it was asked in
        (general-retrieval plan 3.5): learned, suggested (waiting for the owner), skipped."""
        ...

    def accept_asked_as(self, entry_id: str) -> dict[str, Any]:
        """The owner's yes to ways of asking learned from other people's conversations."""
        ...

    def loop_status(self) -> dict[str, Any]:
        """What the updating loop asks of the owner now (brainkit/loop.py)."""
        ...

    def correction(self, text: str, *, session_id: str = "", packet_id: str = "") -> dict[str, Any]:
        """The owner corrected an AI's output: its suspects and the "Still true?" card."""
        ...

    def close_correction(self, correction_id: int, status: str) -> None: ...

    def check_output(self, text: str, *, sent_back: str = "") -> list[dict[str, Any]]:
        """The must-hold violations in an output's text; `sent_back` names a draft sent
        back for them, so the measure counts it."""
        ...

    def agent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """The knowledge agent's runs, newest first, each with its steps."""
        ...

    def blast_radius(self, proposal_id: str) -> dict[str, Any]:
        """What a waiting proposal would change in recent briefs (the replay harness)."""
        ...

    def link_output(self, path: str, *, project: str | None = None, row: str | None = None) -> None:
        """The person says what an output is for."""
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

    # ---- the baseline check: what a model should read side by side, and scheduled changes

    def pending_checks(self, limit: int = 4) -> list[dict[str, Any]]:
        """Statements a model should read beside the notes they may disagree with, oldest
        first: [{"subject", "title", "text", "pairs": [{"key", "id", "title", "text"}]}]."""
        ...

    def record_checks(self, verdicts: list[dict[str, Any]]) -> int:
        """Keep a model's verdicts on pairs: [{"key", "relation", "detail"}]."""
        ...

    def apply_scheduled(self) -> dict[str, Any]:
        """Revisions the owner scheduled whose time has come go in: {"applied", "returned"}."""
        ...

    # ---- dissent: challenges, the weekly cross-check, the external challenger's targets

    def challenge(
        self, note_id: str, *, claim: str, evidence: str, source: str, proposer: str
    ) -> BrainProposal:
        """Challenge a note with a claim and its evidence: it waits for review."""
        ...

    def cross_check(self) -> list[dict[str, Any]]:
        """Beliefs something in the Brain says otherwise about, each with its evidence."""
        ...

    def challenge_targets(self, limit: int = 3) -> list[dict[str, Any]]:
        """The beliefs the external challenger tests this week, each as a claim only."""
        ...


class NoBrain:
    """The workspace without long-term context. Nothing breaks; nothing is remembered."""

    def status(self) -> dict[str, Any]:
        return {"available": False, "reason": "No Brain is configured for this workspace."}

    def context(self, request: str, *, session_id: str | None = None) -> BrainContext:
        return BrainContext(available=False, reason="No Brain is configured.")

    def search(
        self, query: str, limit: int = 10, *, include_archived: bool = False
    ) -> list[BrainHit]:
        return []

    def entry(self, entry_id: str, *, include_archived: bool = False) -> BrainEntry | None:
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

    def undo(self, checkpoint_id: str, *, together: bool = False) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def verify(self, entry_id: str, *, confidence: str | None = None) -> BrainEntry:
        raise Conflict("This workspace has no Brain.")

    def mark(self, entry_id: str, state: str, *, reason: str) -> BrainEntry:
        raise Conflict("This workspace has no Brain.")

    def catalog(self) -> BrainCatalog:
        return BrainCatalog()

    def attention(self) -> dict[str, Any]:
        return {
            "clashes": [],
            "twins": [],
            "flagged": [],
            "recheck": [],
            "went_in": [],
            "dated": [],
            "usage": {},
            "days": 7,
        }

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

    def skill_freshness(self, name: str) -> dict[str, Any] | None:
        return None

    def embed(self, texts: list[str]) -> list[list[float]] | None:
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

    def project_objective(self, project_id: str, objective: str, *, reason: str) -> None:
        raise Conflict("This workspace has no Brain to keep projects in.")

    def project_update(self, project_id: str, **_: Any) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to follow projects in.")

    def preview(
        self,
        request: str,
        *,
        project: str | None = None,
        tools: bool = True,
        include: dict[str, Any] | None = None,
        exclude: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "text": "",
            "mode": "none",
            "tokens": 0,
            "project": None,
            "procedure": None,
            "skill_included": None,
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

    def prompts(self, *, archived: bool = False) -> list[dict[str, Any]]:
        return []

    def prompt(self, prompt_id: str) -> dict[str, Any] | None:
        return None

    def activity(self, **_: Any) -> list[dict[str, Any]]:
        return []

    def use(self, entry_id: str, *, days: int = 90) -> dict[str, Any] | None:
        return None

    def gaps(self, *, days: int = 30) -> list[dict[str, Any]]:
        return []

    def indexed(self, ids: list[str]) -> set[str]:
        return set()

    def receipt(self, packet_id: str) -> dict[str, Any] | None:
        return None

    def requests_in(self, session_id: str) -> list[dict[str, Any]]:
        return []

    def taste(self) -> dict[str, Any]:
        return {"lenses": {"looks": [], "feels": [], "works": []}, "words": {}, "count": 0}

    def propose_taste(self, text: str, **fields: Any) -> dict[str, Any]:
        return {"status": "unavailable"}

    def learned(self) -> list[dict[str, Any]]:
        return []

    def forget_learned(self, rule_id: str) -> dict[str, Any]:
        return {"status": "missing"}

    def brain_map(
        self, *, area: str | None = None, page: int = 1, tier: str | None = None
    ) -> dict[str, Any]:
        return {"lines": [], "page": 1, "pages": 1, "levels": {}}

    def relevance(self, goal: str, texts: list[str]) -> list[float | None] | None:
        return None

    def map_view(self) -> dict[str, Any]:
        return {
            "areas": [],
            "projects": [],
            "sheets": [],
            "must_holds": [],
            "lore": [],
            "levels": {},
            "sealed": 0,
            "text": "",
            "cut": {},
            "tokens": 0,
            "limit": 250,
            "caps": {},
            "fingerprint": "",
        }

    def sections(self, item_id: str) -> dict[str, Any]:
        raise NotFound("This workspace has no Brain.")

    def open_address(self, address: str) -> dict[str, Any]:
        raise NotFound("This workspace has no Brain.")

    def lore(self) -> list[dict[str, Any]]:
        return []

    def lesson(self, lesson_id: str) -> dict[str, Any]:
        raise NotFound("This workspace has no Brain.")

    def propose_lesson(self, **fields: Any) -> dict[str, Any]:
        return {"status": "unavailable"}

    def sessions_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return []

    def correct(
        self, packet_id: str, kind: str, *, item: str = "", note: str = ""
    ) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def brain_versions(self) -> list[dict[str, Any]]:
        return []

    def bench_files(self) -> dict[str, str]:
        return {}

    def commit_sheets(self, message: str) -> dict[str, Any]:
        return {"committed": False, "reason": "no Brain"}

    def world_draft(self) -> dict[str, Any]:
        return {"due": False, "prompt": "", "regions": {}}

    def propose_world(self, text: str, regions: dict[str, Any]) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def bench_write(self, rel: str, text: str | None, *, message: str) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def save_version(self, *, cause: str = "manual", note: str = "") -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def version_diff(self, a: str, b: str) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def restore_version(self, version: str, *, ids: list[str] | None = None) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

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

    def kernel(self, *, tools: bool = True) -> dict[str, Any]:
        return {"text": "", "tokens": 0}

    def record_model_call(self, job: str, model: str, **figures: Any) -> None:
        return None

    def report(
        self, *, days: int = 7, claude_code: bool = False, quality: bool = True
    ) -> dict[str, Any]:
        return {"days": days, "spend": {"days": []}, "per_day_usd": 0.0, "text": ""}

    def replay(
        self, packet_ids: list[str], *, at: str | None = None, proposal: str | None = None
    ) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to replay.")

    def eval_case(self, packet_id: str) -> dict[str, Any] | None:
        return None

    def eval_label(self, packet_id: str, labels: dict[str, list[str]]) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to evaluate.")

    def eval_status(self) -> dict[str, Any]:
        return {"cases": 0, "labeled": 0, "held_out": 0, "by_type": {}}

    def calibration_samples(self) -> list[dict[str, Any]]:
        return []

    def set_calibration(self, pairs: list[tuple[int, int]], *, method: str) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to calibrate.")

    def agent_outline(self, *, brief: bool = False) -> dict[str, Any]:
        return {"counts": {}, "goals": "", "areas": [], "projects": [], "skills": [], "text": ""}

    def agent_gather(self, action: str, *, limit: int = 10) -> dict[str, Any]:
        return {"action": action, "candidates": [], "found": 0}

    def agent_skill(self, name: str) -> str:
        raise Conflict("This workspace has no Brain for an agent to keep.")

    def agent_skills(self) -> list[dict[str, Any]]:
        return []

    def agents(self, *, archived: bool = False) -> list[dict[str, Any]]:
        return []

    def agent(self, name: str) -> dict[str, Any] | None:
        return None

    def save_agent(
        self, name: str, fields: dict[str, Any], prompt: str, **_: Any
    ) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep agents in.")

    def archive_agent(self, name: str) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep agents in.")

    def agent_versions(self, name: str, *, with_text: bool = False) -> list[dict[str, Any]] | None:
        return None

    def work_skill(self, name: str) -> str | None:
        return None

    def unsaved(self) -> list[str]:
        return []

    def models(self) -> dict[str, Any]:
        return {"matching": {"enabled": False, "present": False, "downloading": False}}

    def download_models(self) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to download a model for.")

    def skills_history(self, names: list[str]) -> dict[str, dict[str, Any]]:
        return {}

    def holds_text(self, fingerprints: list[str]) -> set[str]:
        return set()

    def local_models(self) -> dict[str, Any]:
        return {"enabled": False}

    def act_local_models(
        self, action: str, name: str = "", on: bool | None = None
    ) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to run local models for.")

    def made_from(self, path: str) -> dict[str, Any] | None:
        return None

    def work_given(self, run_id: str) -> list[dict[str, Any]]:
        return []

    def requests(
        self, *, limit: int = 50, before: str | None = None, client: str | None = None
    ) -> dict[str, Any]:
        return {"requests": [], "brain_tokens": 0, "apps": []}

    def request(self, packet_id: str) -> dict[str, Any]:
        raise NotFound("This workspace has no Brain.")

    def goals(self) -> dict[str, Any]:
        return {"questions": [], "answers": {}, "exists": False, "updated": None, "text": ""}

    def set_goals(self, answers: dict[str, str]) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep goals in.")

    def ladder(self, *, with_signals: bool = False) -> dict[str, Any]:
        return {
            "purpose": {
                "id": "you-goals",
                "exists": False,
                "text": "",
                "signals": [],
                "rules": {},
            },
            "must_holds": [],
            "yours": [],
            "agents": [],
            "has_goals": False,
            "check_ins_due": 0,
            "starters": [],
            "signals": [],
        }

    def goal(self, goal_id: str) -> dict[str, Any]:
        raise NotFound("This workspace has no Brain.")

    def goal_cards(self) -> list[dict[str, Any]]:
        return []

    def act_goal(
        self, action: str, goal_id: str = "", fields: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep goals in.")

    def state_act(self, action: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        if action in ("sheets", "waiting", "promotions"):
            return {"sheets": [], "waiting": [], "suggestions": []}
        if action == "templates":
            return {"templates": []}
        raise Conflict("This workspace has no Brain to keep State in.")

    def update_state(
        self, updates: list[dict[str, Any]], *, evidence: str = "", session_id: str = ""
    ) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep State in.")

    def get_state(self, *, sheet: str = "", row: str = "", query: str = "") -> dict[str, Any]:
        return {"text": "No State sheets yet.", "sheets": []}

    def hand_off(self, **fields: Any) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep tasks in.")

    def tasks(self, **filters: Any) -> list[dict[str, Any]]:
        return []

    def task(self, task_id: str) -> dict[str, Any]:
        raise NotFound("This workspace has no Brain.")

    def outputs_for(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        return {}

    def agent_tool(self, name: str, args: Any) -> tuple[Any, list[str]]:
        return None, ["This workspace has no Brain."]

    def agent_menu(self) -> str:
        return ""

    def sweep(self) -> dict[str, Any]:
        return {"text": "This workspace has no Brain to file into."}

    def changes_digest(self) -> str:
        return ""

    def record_agent_run(
        self, run_id: str, action: str, ending: str, record: dict[str, Any]
    ) -> None:
        return None

    def record_episode(self, **fields: Any) -> None:
        return None

    def enrichment_pending(self, limit: int | None = None) -> list[dict[str, Any]]:
        return []

    def enrich_note(
        self, entry_id: str, answer: str, *, by: str, expected_version: str | None = None
    ) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def set_asked_as(self, entry_id: str, lines: list[str]) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def accept_triggers(self, entry_id: str) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def learn_from_use(self, days: int = 30) -> dict[str, Any]:
        return {"learned": [], "suggested": [], "skipped": 0}

    def accept_asked_as(self, entry_id: str) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain.")

    def loop_status(self) -> dict[str, Any]:
        return {
            "corrections": [],
            "bent_rules": [],
            "approval_health": {},
            "single_source": [],
            "review_due": False,
            "lessons": [],
            "hand_ups": [],
        }

    def correction(self, text: str, *, session_id: str = "", packet_id: str = "") -> dict[str, Any]:
        return {"suspects": [], "card": None}

    def close_correction(self, correction_id: int, status: str) -> None:
        return None

    def check_output(self, text: str, *, sent_back: str = "") -> list[dict[str, Any]]:
        return []

    def agent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return []

    def blast_radius(self, proposal_id: str) -> dict[str, Any]:
        return {"briefs": 0, "changed": 0, "rows": [], "seconds": 0.0}

    def link_output(self, path: str, *, project: str | None = None, row: str | None = None) -> None:
        return None

    def builtin_skills(self) -> dict[str, Any]:
        return {"skills": [], "missing": []}

    def add_builtin_skills(self, names: list[str] | None = None) -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to keep skills in.")

    def move_in(self, sources: list[dict[str, Any]], *, name: str = "") -> dict[str, Any]:
        raise Conflict("This workspace has no Brain to move into.")

    def pending_checks(self, limit: int = 4) -> list[dict[str, Any]]:
        return []

    def record_checks(self, verdicts: list[dict[str, Any]]) -> int:
        return 0

    def apply_scheduled(self) -> dict[str, Any]:
        return {"applied": [], "returned": []}

    def challenge(self, note_id: str, **_: Any) -> BrainProposal:
        raise Conflict("This workspace has no Brain to challenge.")

    def cross_check(self) -> list[dict[str, Any]]:
        return []

    def challenge_targets(self, limit: int = 3) -> list[dict[str, Any]]:
        return []


class TextExtractor(Protocol):
    """Turns an uploaded file into searchable text (its 'text shadow'), or None; and into
    Markdown that keeps its shape (headings, slides, pages, a transcript's turns), or None."""

    def extract(self, data: bytes, filename: str, mime: str | None) -> str | None: ...

    def markdown(self, data: bytes, filename: str) -> str | None: ...
