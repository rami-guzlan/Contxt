"""Scoped authority: what an authenticated principal may do, and where.

A credential carries a grant: a set of actions and, optionally, the projects it is limited to.
The acting identity always comes from the credential, so a client cannot change who it is or
reach another model's queue by changing a parameter.

Human release gates (spec section 18) are never grantable to a model: approving, exporting,
changing durable Brain context and administering the workspace stay with people.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from workspace_core.errors import PermissionDenied

ACTIONS = frozenset(
    {
        "workspace.admin",
        "events.read",
        "goals.read",
        "goals.write",
        "projects.read",
        "projects.write",
        "tasks.read",
        "tasks.write",
        "tasks.claim",
        "runs.write",
        "context.read",
        "context.write",
        "work.write",
        "artifacts.read",
        "artifacts.create",
        "artifacts.review",
        "artifacts.export",
        "approvals.request",
        "approvals.decide",
        "brain.read",
        "brain.propose",
        "brain.govern",
    }
)

HUMAN_ONLY = frozenset(
    {"workspace.admin", "artifacts.review", "artifacts.export", "approvals.decide", "brain.govern"}
)

# A connected model reads its context, works its own queue, and proposes; it never decides.
MODEL_DEFAULTS = frozenset(
    {
        "projects.read",
        "tasks.read",
        "tasks.claim",
        "runs.write",
        "context.read",  # what its work pins; a person's notes reach it only that way
        "artifacts.read",
        "artifacts.create",
        "approvals.request",
        "brain.read",
        "brain.propose",
        "events.read",
    }
)

KINDS = ("human", "model", "system")


@dataclass(frozen=True)
class Grant:
    actions: frozenset[str]
    projects: frozenset[str] | None = None  # None: every project

    @classmethod
    def of(cls, actions: Iterable[str], projects: Iterable[str] | None, *, kind: str) -> Grant:
        wanted = set(actions)
        expanded = set(ACTIONS) if "*" in wanted else wanted & ACTIONS
        if kind != "human":
            expanded -= HUMAN_ONLY
        return cls(frozenset(expanded), None if projects is None else frozenset(projects))


@dataclass(frozen=True)
class Principal:
    """Who is acting, as established by authentication."""

    actor_id: str
    kind: str
    name: str
    grant: Grant
    credential_id: str | None = None

    @property
    def is_human(self) -> bool:
        return self.kind == "human"

    def can(self, action: str, project_id: str | None = None) -> bool:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        if action not in self.grant.actions:
            return False
        return (
            project_id is None or self.grant.projects is None or project_id in self.grant.projects
        )

    def require(self, action: str, project_id: str | None = None) -> None:
        if self.can(action, project_id):
            return
        where = f" in project {project_id}" if project_id else ""
        raise PermissionDenied(
            f"{self.name} ({self.kind}) may not {action}{where}.",
            action=action,
            project_id=project_id,
        )

    def sees_project(self, project_id: str | None) -> bool:
        return (
            project_id is None or self.grant.projects is None or (project_id in self.grant.projects)
        )
