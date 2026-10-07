"""The error vocabulary every adapter maps: REST to status codes, MCP to tool errors."""

from __future__ import annotations

from typing import Any


class WorkspaceError(Exception):
    """A refusal the caller can act on. `code` is stable; the message is for people."""

    code = "error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


class ValidationFailed(WorkspaceError):
    code = "invalid"


class NotFound(WorkspaceError):
    code = "not_found"


class Unauthenticated(WorkspaceError):
    code = "unauthenticated"


class PermissionDenied(WorkspaceError):
    code = "forbidden"


class Conflict(WorkspaceError):
    """The request is valid but the current state does not allow it."""

    code = "conflict"


class InvalidTransition(Conflict):
    code = "invalid_transition"


class VersionConflict(Conflict):
    """The record changed since the caller read it (optimistic concurrency)."""

    code = "version_conflict"


class LeaseLost(Conflict):
    """The run's claim expired or was released; its work can no longer be written."""

    code = "lease_lost"


class IdempotencyMismatch(Conflict):
    """The idempotency key was already used for a different request."""

    code = "idempotency_mismatch"
