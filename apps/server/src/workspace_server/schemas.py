"""Request bodies. Responses are the core's records, serialized as they are."""

from __future__ import annotations

from typing import Any

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
    # approve | reject (a proposal); archive | edit | restore | unarchive | update | verify |
    # mark (an entry)
    action: str
    proposal_id: str | None = None
    entry_id: str | None = None  # the entry the entry actions act on
    reason: str = ""
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
    source: dict[str, str] | None = None  # what the batch came from, as the page shows it


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


class ReconcileIn(Body):
    proposal_id: str
    entry_id: str
    current: str  # "proposal" or "entry": the piece that stands as it is
    guidance: str = ""
    assignee_id: str | None = None  # none: waits for a model, or for a run from this computer


# ------------------------------------------------------------------------- notes


class SummarizeIn(Body):
    guidance: str = Field(default="", max_length=2000)


class CaptureSettingsIn(Body):
    summarize: bool


# ------------------------------------------------------------------------- skills


class SkillRunIn(Body):
    ask: str = Field(min_length=1, max_length=4000)
    capture_id: str | None = None
    project: str | None = None
    files: list[str] = Field(default_factory=list, max_length=5)


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
