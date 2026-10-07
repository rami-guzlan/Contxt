"""Request plumbing: who is calling, and how refusals become HTTP responses."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from workspace_core.domain.policy import Principal
from workspace_core.errors import (
    Conflict,
    NotFound,
    PermissionDenied,
    Unauthenticated,
    ValidationFailed,
    WorkspaceError,
)
from workspace_core.workspace import Workspace

COOKIE = "workspace_token"  # the name every workspace used before each had its own


def cookie_name(ws: Workspace) -> str:
    """This workspace's own session cookie. A browser keeps cookies by host, not by port, so
    two workspaces on one computer (say on :8787 and :8788) would sign each other out if they
    shared a name."""
    return f"{COOKIE}_{ws.rt.workspace_id.lower()}"


CSRF_HEADER = "x-workspace-csrf"
STATUS = {
    ValidationFailed: 422,
    NotFound: 404,
    Unauthenticated: 401,
    PermissionDenied: 403,
    Conflict: 409,
}


def status_for(error: WorkspaceError) -> int:
    for kind, status in STATUS.items():
        if isinstance(error, kind):
            return status
    return 400


def error_response(error: WorkspaceError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if isinstance(error, Unauthenticated) else None
    return JSONResponse({"error": error.to_dict()}, status_code=status_for(error), headers=headers)


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def get_workspace(request: Request) -> Workspace:
    workspace: Workspace = request.app.state.ws
    return workspace


def get_principal(request: Request) -> Principal:
    """From the Authorization header; the browser UI uses an HttpOnly cookie instead.

    A cookie is sent by the browser automatically, so a state-changing request that relies on
    it must also carry the custom header only our own page sets (a CSRF guard).
    """
    ws = get_workspace(request)
    token = bearer(request)
    if token:
        return ws.actors.authenticate(token)
    # Its own cookie, or the shared one a session from before still carries.
    cookie = request.cookies.get(cookie_name(ws)) or request.cookies.get(COOKIE)
    if not cookie:
        raise Unauthenticated("Sign in with the link `contxt serve` printed, or your owner token.")
    principal = ws.actors.authenticate(cookie)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        raise PermissionDenied("Missing the X-Workspace-CSRF header.")
    return principal


Who = Annotated[Principal, Depends(get_principal)]
WS = Annotated[Workspace, Depends(get_workspace)]
