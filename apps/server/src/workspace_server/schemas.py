"""Request bodies. Responses are the core's records, serialized as they are."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def changes(self) -> dict[str, Any]:
        """Only the fields the client actually sent (PATCH semantics)."""
        data = self.model_dump(exclude_unset=True)
        data.pop("expected_version", None)
        return data


# ------------------------------------------------------------------------- the task bus


class ReasonIn(Body):
    reason: str = ""


class ClaimIn(Body):
    task_id: str
    lease_seconds: int | None = None


class RunEventIn(Body):
    type: str
    message: str = ""
    data: dict[str, Any] | None = None


class CompleteIn(Body):
    summary: str = ""
    outcome: str = "succeeded"


class RunIn(Body):
    task_id: str


# ------------------------------------------------------------------------- connections


class ConnectionIn(Body):
    name: str
    provider: str
    description: str | None = None
    projects: list[str] | None = None


class TokenIn(Body):
    label: str | None = None
    projects: list[str] | None = None


class ActorRenameIn(Body):
    name: str


# ------------------------------------------------------------------------- the Brain


class ProposalIn(Body):
    title: str
    statement: str
    summary: str | None = None
    origin: str | None = None  # where it came from: doc:<note id>@r<version>, say
    kind: str = "fact"
    scope: str | None = None
    evidence: str = ""
    sources: list[str] | None = None
    replaces: list[str] | None = None
    contradicts: list[str] | None = None
    topic: str | None = None


class DecisionItem(Body):
    # approve | reject | unschedule (a proposal); archive | edit | restore | unarchive |
    # update | verify | mark (an entry)
    action: str
    proposal_id: str | None = None
    entry_id: str | None = None  # the entry the entry actions act on
    reason: str = ""  # approve: required, in a few words, when it revises a baseline
    replaces: list[str] | None = None  # approve: entries it replaces, archived as it lands
    topic: str | None = None  # approve: file it under another area/topic
    title: str | None = None  # approve or edit: a better title
    summary: str | None = None  # approve or edit: its one-line summary
    body: str | None = None  # approve: file these words instead; edit: the entry's new text
    ref: str | None = None  # restore: the version to put back ("current", or a commit)
    # update: details to set; an empty value clears one (owner, review_days, review_by,
    # classification, area, topic, and a project's aliases, comma separated)
    fields: dict[str, str | None] | None = None
    minor: bool | None = None  # edit: a typo or cleanup, not new knowledge
    state: str | None = None  # mark: stale | disputed (with a reason)
    confidence: str | None = None  # verify: confirmed | inferred | disputed | unknown


class DecisionsIn(Body):
    decisions: list[DecisionItem] = Field(min_length=1, max_length=200)
    label: str | None = None
    # What the batch came from, as the page shows it: {"catch_up": <item>}, and how many
    # seconds the card was shown before the decision (`seconds`).
    source: dict[str, str | int | float] | None = None


class PoliciesIn(Body):
    """How the Brain is governed; only the settings sent change."""

    review_days: dict[str, int | None] | None = None  # by area or kind
    default_owner: str | None = None
    auto_apply_own_scope: bool | None = None
    auto_apply_scopes: list[str] | None = None
    max_proposals_per_session: int | None = None
    retention_days: int | None = None
    # What the owner's own captures do, by type and origin: {"file": {"chat": "wait"}}.
    capture: dict[str, dict[str, str]] | None = None
    preset: str | None = None  # personal, careful or regulated: a fresh start
    revision_delay: bool | None = None  # a day to think before a rule or must-hold changes
    model_checks: bool | None = None  # your own AI reads possible disagreements
    cross_check: bool | None = None  # the weekly cross-check of your beliefs
    challenger: bool | None = None  # the external challenger (off until turned on)
    redact_cloud: bool | None = None  # sensitive spans redacted for cloud models (decision 13)


class CatchUpItemIn(Body):
    """One item in the catch-up: proposal:<id>, recheck:<id>, twin:<a>|<b>, tidy:<id>,
    offer:<type>:<origin> or unused."""

    key: str
    days: int | None = Field(default=None, ge=1, le=3650)


class GoalsIn(Body):
    """The owner's answers about what the Brain is for, by question id."""

    answers: dict[str, str]


class BuiltinSkillsIn(Body):
    names: list[str] | None = None  # none: every one the Brain is missing


class MoveInSource(Body):
    kind: str = "paste"  # chatgpt, claude, cursor, instructions or paste
    text: str = Field(max_length=200_000)
    label: str = ""


class MoveInIn(Body):
    sources: list[MoveInSource] = Field(min_length=1, max_length=8)
    ids: list[str] | None = None  # the ideas to keep; none: every one worth keeping


class DifferenceIn(Body):
    request: str = Field(min_length=1, max_length=2000)
    project: str | None = None


class FollowupIn(Body):
    question: str = Field(min_length=1, max_length=400)
    answer: str = Field(min_length=1, max_length=6000)


class AppConnectIn(Body):
    confirm: bool = False  # the person said yes: this changes the app's own settings


class OutputFolderIn(Body):
    path: str = Field(min_length=1, max_length=500)


class OutputMoveIn(Body):
    source: str = Field(min_length=1, max_length=500)
    target: str = Field(min_length=1, max_length=500)


class MergeIn(Body):
    keep_id: str
    other_id: str
    assignee_id: str | None = None  # none: waits for a model, or for a run from this computer


class BrainProjectIn(Body):
    """A project for the Brain to follow: its name, what it is for, other names for it."""

    name: str = Field(max_length=200)
    summary: str = Field(max_length=1000)
    aliases: list[str] = Field(default_factory=list, max_length=24)
    objective: str = Field(default="", max_length=1000)
    goals: list[str] = Field(default_factory=list, max_length=12)


class ProjectUpdateIn(Body):
    """Progress on a project: one line on what happened, and what changed in where it stands
    (status, current, next, blockers, decisions, completed)."""

    summary: str = Field(max_length=300)
    state: dict[str, str] = Field(default_factory=dict)


class GapIn(Body):
    key: str


class BrainDecisionIn(Body):
    approve: bool
    reason: str = ""


class VerifyIn(Body):
    confidence: str | None = None


class MarkIn(Body):
    state: str
    reason: str


class RequestLabelsIn(Body):
    """The owner's labels for one logged request, for the private eval set: notes it needed,
    notes that helped, notes that were noise, and notes it should have had."""

    needed: list[str] = Field(default_factory=list, max_length=40)
    useful: list[str] = Field(default_factory=list, max_length=40)
    noise: list[str] = Field(default_factory=list, max_length=40)
    missing: list[str] = Field(default_factory=list, max_length=40)
    nothing: bool = False  # it should get nothing from the Brain


class LocalModelsIn(Body):
    """One change to this computer's local models (Settings, On this computer)."""

    action: Literal["check", "default", "download", "remove", "speed", "claude_code"]
    name: str = Field(default="", max_length=100)
    on: bool | None = None


class ReplayIn(Body):
    packets: list[str] = Field(default_factory=list, max_length=50)
    at: str | None = None
    proposal: str | None = None


class DistillRequestIn(Body):
    """Pull what matters out of these notes and captures, or documents filed in the Brain."""

    item_ids: list[str] = Field(default_factory=list, max_length=20)
    paths: list[str] = Field(default_factory=list, max_length=20)  # documents in the Brain
    assignee_id: str | None = None
    guidance: str = Field(default="", max_length=2000)
    wait: bool = True  # with no model to take it yet, keep it for the first one that connects


class RememberIn(Body):
    """Pull what matters out of one note (the note is in the address)."""

    assignee_id: str | None = None
    guidance: str = Field(default="", max_length=2000)
    wait: bool = True


class DistillSettingsIn(Body):
    assignee_id: str | None = None  # the model that does the AI work the app starts
    triage: str | None = None  # the model that triages first (claude, local:..., ollama:...)


class ReconcileIn(Body):
    proposal_id: str
    entry_id: str
    current: str  # "proposal" or "entry": the piece that stands as it is
    guidance: str = ""
    assignee_id: str | None = None  # none: waits for a model, or for a run from this computer


# ------------------------------------------------------------------------- notes


class SummarizeIn(Body):
    guidance: str = Field(default="", max_length=2000)


class ConfirmIn(Body):
    confirmed: bool = False


class ExcludeIn(Body):
    reason: str = Field(default="", max_length=200)


class CaptureSettingsIn(Body):
    summarize: bool


# ------------------------------------------------------------------------- skills


class SkillRunIn(Body):
    ask: str = Field(min_length=1, max_length=4000)
    capture_id: str | None = None
    project: str | None = None
    files: list[str] = Field(default_factory=list, max_length=5)


class SkillsRunIn(SkillRunIn):
    """A run from the Skills page: the skills to follow, in order (none: the one that fits)."""

    names: list[str] = Field(default_factory=list, max_length=6)


class SkillImproveIn(Body):
    ask: str = Field(min_length=1, max_length=4000)
    capture_id: str | None = None  # an example brought in or written (an edited result, say)
    example: str | None = None  # an artifact a run of this skill made


class SkillDraftIn(Body):
    ask: str = Field(min_length=1, max_length=4000)
    capture_id: str | None = None


class SkillEditIn(Body):
    body: str = Field(min_length=1, max_length=60000)
    description: str | None = Field(default=None, max_length=2000)
    when_to_use: str | None = Field(default=None, max_length=2000)
    triggers: list[str] | None = Field(default=None, max_length=12)
    reason: str = Field(default="", max_length=600)


class NoteIn(Body):
    title: str = ""
    body: str = ""


class NoteSaveIn(Body):
    title: str | None = None
    body: str | None = None
    expected_version: int | None = None


class NoteNameIn(Body):
    label: str


class NoteRestoreIn(Body):
    revision: int


class NoteToBrainIn(Body):
    project: str | None = None  # the Brain project to file it in
    status: str | None = None  # draft, sent, final


# ------------------------------------------------------------------------- the workspace


class OnboardingIn(Body):
    completed: bool | None = None
    dismissed: bool | None = None
    tour_seen: bool | None = None
    step: str | None = None


class WorkspacePatch(Body):
    name: str | None = None
    timezone: str | None = None


# ------------------------------------------------------------------------- the knowledge agent


class AgentSettingsIn(Body):
    model: str | None = Field(default=None, max_length=140)
    suggestions: bool | None = None


class AgentActionIn(Body):
    model: str | None = Field(default=None, max_length=140)


class AgentEnrichIn(Body):
    model: str | None = Field(default=None, max_length=140)
    limit: int | None = Field(default=None, ge=1, le=5000)


class AskedAsIn(Body):
    lines: list[str] = Field(default_factory=list, max_length=10)


class AgentTurn(Body):
    role: str = Field(pattern="^(user|agent)$")
    text: str = Field(max_length=8000)


class AgentChatIn(Body):
    message: str = Field(min_length=1, max_length=4000)
    history: list[AgentTurn] = Field(default_factory=list, max_length=40)
    model: str | None = Field(default=None, max_length=140)


class AgentDismissIn(Body):
    key: str = Field(min_length=1, max_length=300)
    days: int = Field(default=3, ge=1, le=30)


class AgentAnswerIn(Body):
    key: str = Field(min_length=1, max_length=300)
    do: str = Field(pattern="^(verify|retire|dispute|answer|done|dismiss)$")
    text: str | None = Field(default=None, max_length=2000)


class AgentKeepIn(Body):
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=1, max_length=2000)
    kind: str = Field(default="fact", pattern="^(fact|rule|decision|preference)$")
    said: str = Field(default="", max_length=4000)


# ------------------------------------------------------------------------- the Library

LIBRARY_KIND = "^(guide|reference|influence)$"
LIBRARY_REFRESH = "^(never|weekly|monthly)$"


class LibraryWriteIn(Body):
    """A guide (or any item) written in the Library itself, in Markdown."""

    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)
    kind: str = Field(default="guide", pattern=LIBRARY_KIND)
    project: str | None = Field(default=None, max_length=200)


class LibraryUrlIn(Body):
    """A web page to fetch and keep."""

    url: str = Field(min_length=9, max_length=2000)
    kind: str = Field(default="influence", pattern=LIBRARY_KIND)
    title: str = Field(default="", max_length=200)
    refresh: str = Field(default="never", pattern=LIBRARY_REFRESH)
    project: str | None = Field(default=None, max_length=200)


class LibraryRepoIn(Body):
    """A GitHub repository to keep as a snapshot: its README, its tree and the files picked."""

    url: str = Field(min_length=20, max_length=500)
    paths: list[str] = Field(default_factory=list, max_length=20)
    kind: str = Field(default="influence", pattern=LIBRARY_KIND)
    title: str = Field(default="", max_length=200)
    refresh: str = Field(default="never", pattern=LIBRARY_REFRESH)
    project: str | None = Field(default=None, max_length=200)


class LibraryItemIn(Body):
    """Change what kind of item it is, how often it is fetched again, or where it came from
    (capture:recording, library, upload, ...)."""

    path: str = Field(min_length=1, max_length=500)
    kind: str | None = Field(default=None, pattern="^(guide|reference|influence|asset)$")
    refresh: str | None = Field(default=None, pattern=LIBRARY_REFRESH)
    origin: str | None = Field(default=None, max_length=160)


class LibraryRefreshIn(Body):
    path: str = Field(min_length=1, max_length=500)


# ------------------------------------------------------------------------- agents


class AgentForm(Body):
    """An agent's role, written like a job description: the Brain checks what each field means."""

    role: str = Field(default="", max_length=300)
    responsibilities: list[str] = Field(default_factory=list, max_length=20)
    goals: list[str] = Field(default_factory=list, max_length=20)
    projects: list[str] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=20)
    library: list[str] = Field(default_factory=list, max_length=20)
    context: list[str] = Field(default_factory=list, max_length=20)
    meetings_days: int = Field(default=0, ge=0, le=90)
    boundaries: list[str] = Field(default_factory=list, max_length=20)
    output: str = Field(default="outputs", pattern="^(outputs|workspace|proposals)$")
    output_shape: str = Field(default="", max_length=500)
    runner: str = Field(default="claude", max_length=90)
    review: bool = True


class AgentSaveIn(AgentForm):
    name: str = Field(min_length=1, max_length=64)
    prompt: str = Field(default="", max_length=30_000)


class AgentPromptIn(AgentForm):
    """Ask the chosen model to write the operating prompt from the form (saved or not)."""

    name: str = Field(default="", max_length=64)
    model: str | None = Field(default=None, max_length=140)


class AgentAskIn(Body):
    ask: str = Field(min_length=1, max_length=4000)
    project: str | None = Field(default=None, max_length=200)


# ------------------------------------------------------------------------- the Workspace


class WorkspaceDocIn(Body):
    template: str = Field(default="blank", pattern="^(blank|outline|plan|decision|progress)$")
    title: str = Field(default="", max_length=300)
    projects: list[str] = Field(default_factory=list, max_length=10)


class WorkspaceLinkIn(Body):
    url: str = Field(min_length=8, max_length=2000)
    title: str = Field(default="", max_length=300)
    projects: list[str] = Field(default_factory=list, max_length=10)


class WorkspaceProjectsIn(Body):
    projects: list[str] = Field(default_factory=list, max_length=10)


class WorkspaceDraftIn(Body):
    skill: str | None = Field(default=None, max_length=80)
    agent: str | None = Field(default=None, max_length=64)
    ask: str = Field(default="", max_length=2000)


class WorkspaceContinueIn(Body):
    where: str = Field(default="", max_length=300)


class WorkspaceUseIn(Body):
    task_id: str = Field(min_length=1, max_length=80)
    how: str = Field(pattern="^(version|append|new)$")


# ------------------------------------------------------------------------- Compose


class ComposePicks(Body):
    """What goes with a request: skills in order, one agent, notes, documents, a project."""

    skills: list[str] = Field(default_factory=list, max_length=6)
    agent: str | None = Field(default=None, max_length=64)
    docs: list[str] = Field(default_factory=list, max_length=5)
    library: list[str] = Field(default_factory=list, max_length=5)
    project: str | None = Field(default=None, max_length=200)


class ComposeIn(ComposePicks):
    request: str = Field(min_length=1, max_length=20000)

    def spec(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "skills": self.skills,
            "agent": self.agent,
            "docs": self.docs,
            "library": self.library,
            "project": self.project,
        }


class ComposeRunIn(ComposeIn):
    prompt_id: str | None = Field(default=None, max_length=80)


class ComposeImproveIn(ComposeIn):
    model: str | None = Field(default=None, max_length=140)


class PromptIn(Body):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    picks: ComposePicks = Field(default_factory=ComposePicks)
    tags: list[str] = Field(default_factory=list, max_length=12)


class PromptPatch(Body):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    picks: ComposePicks | None = None
    tags: list[str] | None = Field(default=None, max_length=12)
    expected_version: int | None = None


# ------------------------------------------------------------------------- Workflows


class WorkflowIn(Body):
    """A workflow from the builder: its steps (checked in full by the workflow service), when it
    runs, where it runs and where what it makes goes."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    project: str | None = Field(default=None, max_length=200)
    schedule: dict[str, Any] = Field(default_factory=lambda: {"kind": "manual"})
    ai: bool = False
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=12)
    runner: str = Field(default="claude", pattern="^(claude|any)$")
    output: dict[str, Any] = Field(default_factory=lambda: {"kind": "outputs"})
    enabled: bool = True
    expected_version: int | None = None

    def fields(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "project": self.project,
            "schedule": self.schedule,
            "ai": self.ai,
            "steps": self.steps,
            "runner": self.runner,
            "output": self.output,
            "enabled": self.enabled,
        }


class WorkflowRunIn(Body):
    request: str = Field(default="", max_length=4000)


class WorkflowDecideIn(Body):
    go: bool
    edit: str | None = Field(default=None, max_length=400000)
    note: str = Field(default="", max_length=500)


# ------------------------------------------------------------------------- Skills, upgraded


class SkillGitIn(Body):
    """A skill in a GitHub repository: its address (a repository, or a folder in one)."""

    url: str = Field(min_length=19, max_length=500)
    path: str = Field(default="", max_length=300)


class SkillPushIn(Body):
    """Where in Claude Code the copy goes: the person's own skills, or a project's."""

    project_dir: str | None = Field(default=None, max_length=1000)


class SuggestionDismissIn(Body):
    key: str = Field(min_length=1, max_length=80)


# ------------------------------------------------------------------------- goals (G1)


class ProjectObjectiveIn(Body):
    objective: str = Field(max_length=1000)
    reason: str = Field(min_length=1, max_length=500)


class GoalIn(Body):
    """A goal from the coach's draft or the form; `board` fills the plan template's notes,
    `first_steps` become suggestions, `project` links a project to it."""

    title: str = Field(min_length=1, max_length=160)
    why: str = Field(default="", max_length=600)
    level: Literal["yours", "agent"] = "yours"
    kept_by: str | None = Field(default=None, max_length=120)
    measure: dict[str, Any] | None = None
    due: str | None = Field(default=None, max_length=10)
    cadence: Literal["daily", "weekly", "monthly"] = "weekly"
    serves: list[str] | None = Field(default=None, max_length=10)
    template: Literal["plan", "launch", "grow", "blank"] = "plan"
    board: dict[str, str] | None = None
    first_steps: list[str] = Field(default_factory=list, max_length=3)
    project: str | None = Field(default=None, max_length=200)


class GoalChangeIn(Body):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    why: str | None = Field(default=None, max_length=600)
    measure: dict[str, Any] | None = None
    due: str | None = Field(default=None, max_length=10)
    cadence: Literal["daily", "weekly", "monthly"] | None = None
    status: Literal["active", "paused", "met", "missed", "dropped", "retired"] | None = None
    serves: list[str] | None = Field(default=None, max_length=10)
    reason: str = Field(default="", max_length=500)


class GoalCheckInIn(Body):
    call: Literal["on_track", "at_risk", "off_track"]
    value: float | None = None
    line: str = Field(default="", max_length=300)


class GoalBoardIn(Body):
    layout: dict[str, Any]
    expected_version: int | None = None


class GoalSuggestionIn(Body):
    accept: bool


class GoalDecisionIn(Body):
    text: str = Field(min_length=1, max_length=1000)


class GoalLinkIn(Body):
    project: str = Field(min_length=1, max_length=200)
    linked: bool = True


class GoalCoachTurn(Body):
    role: Literal["you", "coach"]
    text: str = Field(min_length=1, max_length=4000)


class GoalCoachIn(Body):
    messages: list[GoalCoachTurn] = Field(min_length=1, max_length=8)
    model: str | None = Field(default=None, max_length=140)


class GoalSettingsIn(Body):
    weekly_review: bool


# ------------------------------------------------------------------- State and tasks (step 6)


class LiveActIn(Body):
    action: Literal[
        "create_sheet", "add_column", "add_row", "write", "touch", "decide", "remove_row"
    ]
    fields: dict[str, Any] = Field(default_factory=dict)


class CorrectionIn(Body):
    text: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=80)
    packet_id: str | None = Field(default=None, max_length=80)


class CorrectionAnswerIn(Body):
    status: Literal["still_true", "fixed", "dismissed"]


class LessonIn(Body):
    key: str = Field(min_length=1, max_length=300)


class CheckOutputIn(Body):
    text: str = Field(min_length=1, max_length=200_000)


class HandOffIn(Body):
    task: str | None = Field(default=None, max_length=20)
    new_task: dict[str, Any] | None = None
    goal: str | None = Field(default=None, max_length=200)
    to: str | None = Field(default=None, max_length=120)
    claim: bool | None = None
    status: Literal["working", "blocked", "waiting_for_you", "done", "dropped"] | None = None
    done_so_far: str | None = Field(default=None, max_length=2000)
    next_step: str | None = Field(default=None, max_length=1000)
    done_when: str | None = Field(default=None, max_length=1000)
    decisions: str | None = Field(default=None, max_length=2000)
    open_questions: str | None = Field(default=None, max_length=2000)
    load: str | None = Field(default=None, max_length=1000)
    evidence: list[str] | None = Field(default=None, max_length=20)
    goal_note: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)


class OutputLinkIn(Body):
    path: str = Field(min_length=1, max_length=1000)
    project: str | None = Field(default=None, max_length=200)
    row: str | None = Field(default=None, max_length=300)
