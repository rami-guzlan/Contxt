"""The Brain's own MCP tools, served by the running app at /brain/mcp (Streamable HTTP, JSON
replies): an AI app on this computer connects by URL with its own token (Settings, Your AI
apps), instead of starting the Brain itself. The same tools and answers as the Brain's stdio
server (`brainkit mcp`), on the one Brain the app holds."""

from __future__ import annotations

import io
import json
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from workspace_core.errors import Unauthenticated

from ..deps import bearer
from .mcp import _allowed_origin

router = APIRouter()


def _one(adapter: Any, message: Any) -> dict[str, Any] | None:
    """One JSON-RPC message through the Brain's MCP server; None for a notification."""
    from brainkit.mcp_server import Server

    out = io.StringIO()
    server = Server(brain=adapter.brain, out=out)
    with adapter._lock:  # one Brain, written to by the app and its AI apps in turn
        server.handle(message if isinstance(message, dict) else {})
    lines = out.getvalue().strip().splitlines()
    found: dict[str, Any] | None = json.loads(lines[-1]) if lines else None
    return found


def _answer(adapter: Any, message: Any) -> Any:
    if isinstance(message, list):
        replies = [r for r in (_one(adapter, m) for m in message) if r is not None]
        return replies or None
    return _one(adapter, message)


@router.post("/brain/mcp")
async def brain_mcp(request: Request) -> Response:
    if not _allowed_origin(request):
        return JSONResponse({"error": "origin not allowed"}, status_code=403)
    try:
        await run_in_threadpool(request.app.state.ws.actors.authenticate, bearer(request))
    except Unauthenticated as exc:
        return JSONResponse(
            {"error": exc.to_dict()}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
        )
    adapter = request.app.state.brain
    if adapter is None:
        return JSONResponse({"error": "this app has no Brain to serve"}, status_code=503)
    try:
        message: Any = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )
    reply = await run_in_threadpool(_answer, adapter, message)
    if reply is None:
        return Response(status_code=202)
    return JSONResponse(reply)


@router.get("/brain/mcp")
def brain_mcp_stream() -> Response:
    # No server-initiated stream: every reply comes back on its POST.
    return Response(status_code=405, headers={"Allow": "POST"})
