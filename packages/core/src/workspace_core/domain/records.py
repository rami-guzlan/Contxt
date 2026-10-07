"""The records services return. Plain, immutable, and serializable with `to_dict`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any, Self


class Record:
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        return cls(**{f.name: row.get(f.name) for f in fields(cls)})  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[call-overload]


@dataclass(frozen=True)
class WorkspaceInfo(Record):
    id: str
    name: str
    timezone: str
    settings: dict[str, Any]
    created_at: str
    updated_at: str
    version: int


@dataclass(frozen=True)
class Actor(Record):
    id: str
    kind: str
    name: str
    provider: str | None
    description: str | None
    last_seen_at: str | None
    disabled_at: str | None
    created_at: str
    updated_at: str
    version: int


@dataclass(frozen=True)
class Credential(Record):
    id: str
    actor_id: str
    token_hint: str
    label: str | None
    actions: list[str]
    projects: list[str] | None
    created_by: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


@dataclass(frozen=True)
class Project(Record):
    id: str
    title: str
    summary: str
    status: str
    brain_ref: str | None
    provenance: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str
    version: int
    archived_at: str | None


@dataclass(frozen=True)
class Task(Record):
    id: str
    project_id: str | None
    title: str
    purpose: str
    instructions: str
    prompt_version: int
    assignee_id: str | None
    schedule: dict[str, Any]
    timezone: str
    next_due_at: str | None
    output_contract: dict[str, Any]
    review_policy: str
    brain_request: str | None
    status: str
    attempts: int
    depends_on: str | None
    template: str | None
    current_run_id: str | None
    revision: int
    provenance: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str
    version: int
    archived_at: str | None


@dataclass(frozen=True)
class Pin(Record):
    id: str
    task_id: str
    ref_type: str
    ref_id: str
    pinned_version: int | None
    note: str | None
    created_by: str
    created_at: str


@dataclass(frozen=True)
class Run(Record):
    id: str
    task_id: str
    attempt: int
    occurrence: str
    status: str
    actor_id: str
    task_revision: int
    claimed_at: str
    lease_expires_at: str
    started_at: str | None
    finished_at: str | None
    packet: dict[str, Any]
    outcome: dict[str, Any]
    version: int


@dataclass(frozen=True)
class ContextItem(Record):
    id: str
    scope_kind: str
    scope_id: str | None
    kind: str
    title: str
    body: str
    url: str | None
    object_key: str | None
    filename: str | None
    mime: str | None
    size: int | None
    content_hash: str | None
    text_shadow: str | None
    shadow_status: str
    idea_state: str | None
    memory_state: str | None
    labels: list[str]
    source_label: str | None
    revision: int
    last_referenced_at: str | None
    provenance: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str
    version: int
    archived_at: str | None

    @property
    def scope(self) -> str:
        return self.scope_kind if self.scope_id is None else f"{self.scope_kind}:{self.scope_id}"


@dataclass(frozen=True)
class Artifact(Record):
    id: str
    goal_id: str | None
    project_id: str | None
    task_id: str | None
    run_id: str | None
    type: str
    title: str
    status: str
    current_version: int
    created_by: str
    created_at: str
    updated_at: str
    version: int
    archived_at: str | None


@dataclass(frozen=True)
class ArtifactVersion(Record):
    id: str
    artifact_id: str
    number: int
    object_key: str
    filename: str
    mime: str
    size: int
    content_hash: str
    preview_text: str | None
    run_id: str | None
    task_revision: int | None
    prompt_version: int | None
    inputs: list[dict[str, Any]]
    context_used: list[dict[str, Any]]
    note: str | None
    created_by: str
    created_at: str


@dataclass(frozen=True)
class Approval(Record):
    id: str
    subject_type: str
    subject_id: str
    subject_version: int | None
    project_id: str | None
    task_id: str | None
    run_id: str | None
    status: str
    reason: str
    requested_by: str
    requested_at: str
    decided_by: str | None
    decided_at: str | None
    decision_note: str | None
    version: int


@dataclass(frozen=True)
class Event(Record):
    seq: int
    id: str
    at: str
    actor_id: str
    type: str
    subject_type: str
    subject_id: str
    project_id: str | None
    reason: str | None
    data: dict[str, Any]
    noise: bool


@dataclass(frozen=True)
class ExportRecord(Record):
    id: str
    artifact_id: str
    artifact_version: int
    destination: str
    status: str
    result: dict[str, Any]
    created_by: str
    created_at: str
