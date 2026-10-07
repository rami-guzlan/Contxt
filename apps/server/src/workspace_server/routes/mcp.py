"""The MCP endpoint: Streamable HTTP with JSON responses, bearer tokens, origin checks."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from workspace_core.errors import Unauthenticated

from ..deps import bearer

router = APIRouter()


def _allowed_origin(request: Request) -> bool:
    """Browsers send Origin; MCP clients do not. Refuse foreign pages (DNS rebinding)."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    settings = request.app.state.settings
    allowed = {settings.base_url.rstrip("/"), *settings.allowed_origins}
    return origin.rstrip("/") in allowed


@router.post("/mcp")
async def mcp(request: Request) -> Response:
    if not _allowed_origin(request):
        return JSONResponse({"error": "origin not allowed"}, status_code=403)
    try:
        who = await run_in_threadpool(request.app.state.ws.actors.authenticate, bearer(request))
    except Unauthenticated as exc:
        return JSONResponse(
            {"error": exc.to_dict()}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        message: Any = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )
    version = request.headers.get("mcp-protocol-version")
    reply = await run_in_threadpool(request.app.state.mcp.handle, message, who, version)
    if reply is None:
        return Response(status_code=202)
    return JSONResponse(reply)


@router.get("/mcp")
def mcp_stream() -> Response:
    # No server-initiated stream: every reply comes back on its POST.
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete("/mcp")
def mcp_end() -> Response:
    return Response(status_code=405, headers={"Allow": "POST"})
