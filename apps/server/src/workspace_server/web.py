"""The browser side: sign-in with the owner token, and the built web app."""

from __future__ import annotations

import mimetypes
import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel, Field

from workspace_core.errors import Unauthenticated

from .deps import COOKIE, cookie_name

# The canvas editor's fonts; Windows' registry may not know these types.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")

router = APIRouter()

NO_UI = """<!doctype html><meta charset="utf-8"><title>Contxt</title>
<body style="font-family:system-ui;margin:3rem;max-width:40rem;line-height:1.5">
<h1>Contxt is running</h1>
<p>The web app is not here yet. Get this version's build with
<code>uv run contxt web --download</code>, or build it yourself with Node.js 20+:
<code>npm install</code>, then <code>npm run build</code>. Then reload this page.</p>
<p>API documentation: <a href="/docs">/docs</a>.</p></body>"""


@router.get("/auth/login")
def login(token: str, request: Request) -> Response:
    """Exchange the owner's token (from `contxt serve`) for an HttpOnly session cookie."""
    try:
        request.app.state.ws.actors.authenticate(token)
    except Unauthenticated:
        return HTMLResponse("<p>That token is not valid.</p>", status_code=401)
    response = RedirectResponse("/", status_code=303)
    secure = request.url.scheme == "https"
    response.set_cookie(
        cookie_name(request.app.state.ws),
        token,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=60 * 60 * 24 * 30,
    )
    return response


class LoginIn(BaseModel):
    token: str = Field(min_length=1, max_length=400)


@router.post("/auth/login", status_code=204)
def login_posted(body: LoginIn, request: Request) -> Response:
    """The same exchange as GET /auth/login, for the sign-in page: the key travels in the
    body, never in the address bar or the browser's history, and a wrong key is a JSON 401
    the page can explain."""
    try:
        request.app.state.ws.actors.authenticate(body.token)
    except Unauthenticated:
        return JSONResponse(
            {"error": {"code": "unauthenticated", "message": "That sign-in key is not valid."}},
            status_code=401,
        )
    response = Response(status_code=204)
    response.set_cookie(
        cookie_name(request.app.state.ws),
        body.token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.post("/auth/logout")
def logout(request: Request) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(cookie_name(request.app.state.ws))
    response.delete_cookie(COOKIE)
    return response


def mount_web(app: FastAPI, dist: str | None) -> None:
    """Serve the built single-page app; unknown non-API paths fall back to index.html."""
    root = os.path.abspath(dist) if dist else None
    index = os.path.join(root, "index.html") if root else None

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith(("api/", "mcp", "auth/")):
            return Response(status_code=404)
        if not root or not index or not os.path.isfile(index):
            return HTMLResponse(NO_UI)
        candidate = os.path.abspath(os.path.join(root, path))
        if path and candidate.startswith(root + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
