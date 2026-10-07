"""Connections: people and models, their revocable credentials, and copyable setups."""

from __future__ import annotations

import os
import sys
from typing import Any

from fastapi import APIRouter, Request, Response

from workspace_connectors.providers import (
    BRAIN_CLIENTS,
    BRAIN_SERVER_NAME,
    PROVIDERS,
    brain_setup,
    mcp_setup,
)
from workspace_core.domain.records import Actor, Credential

from ..deps import WS, Who
from ..schemas import ActorRenameIn, ConnectionIn, TokenIn

router = APIRouter(prefix="/api")


@router.get("/actors")
def actors(who: Who, ws: WS, include_disabled: bool = False) -> list[Actor]:
    return ws.actors.list(who, include_disabled=include_disabled)


@router.get("/providers")
def providers(who: Who) -> list[dict[str, Any]]:
    return [
        {"id": p.id, "label": p.label, "transport": p.transport, "schedule_hint": p.schedule_hint}
        for p in PROVIDERS.values()
    ]


@router.get("/brain/connect")
def connect_brain(request: Request, who: Who) -> dict[str, Any]:
    """How each AI app connects to this Brain: one command, or a block for its settings file.
    The Brain runs as a local command beside its folder, so there is no token to keep."""
    vault = request.app.state.settings.brain_vault
    if not vault:
        return {"ready": False, "server": BRAIN_SERVER_NAME, "clients": []}
    vault = os.path.abspath(vault)
    return {
        "ready": True,
        "server": BRAIN_SERVER_NAME,
        "vault": vault,
        "clients": [brain_setup(c, python=sys.executable, vault=vault) for c in BRAIN_CLIENTS],
    }


@router.post("/connections", status_code=201)
def connect(body: ConnectionIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Connect a model. The token appears in this response only; store it in the client."""
    connection = ws.actors.connect_model(
        who,
        name=body.name,
        provider=body.provider,
        description=body.description,
        projects=body.projects,
    )
    settings = request.app.state.settings
    return {
        "actor": connection.actor,
        "credential": connection.credential,
        "token": connection.token,
        "setup": mcp_setup(body.provider, url=settings.base_url, token=connection.token),
        "worker_prompt": request.app.state.templates.worker_prompt(
            connection.actor.name, ws.info().name
        ),
    }


@router.put("/actors/{actor_id}")
def rename_actor(actor_id: str, body: ActorRenameIn, who: Who, ws: WS) -> Actor:
    """A new display name (the owner's own name, during first-time setup)."""
    return ws.actors.rename(who, actor_id, body.name)


@router.get("/actors/{actor_id}/setup")
def setup(actor_id: str, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """The setup again, without a token (tokens are never shown twice)."""
    actor = ws.actors.get(who, actor_id)
    settings = request.app.state.settings
    return {
        "setup": mcp_setup(actor.provider or "other", url=settings.base_url),
        "worker_prompt": request.app.state.templates.worker_prompt(actor.name, ws.info().name),
    }


@router.get("/actors/{actor_id}/credentials")
def credentials(actor_id: str, who: Who, ws: WS) -> list[Credential]:
    return ws.actors.credentials(who, actor_id)


@router.post("/actors/{actor_id}/tokens", status_code=201)
def issue_token(actor_id: str, body: TokenIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    connection = ws.actors.issue_token(who, actor_id, label=body.label, projects=body.projects)
    settings = request.app.state.settings
    return {
        "credential": connection.credential,
        "token": connection.token,
        "setup": mcp_setup(
            connection.actor.provider or "other", url=settings.base_url, token=connection.token
        ),
    }


@router.delete("/credentials/{credential_id}", status_code=204)
def revoke(credential_id: str, who: Who, ws: WS) -> Response:
    ws.actors.revoke(who, credential_id)
    return Response(status_code=204)


@router.post("/actors/{actor_id}/disable")
def disable(actor_id: str, who: Who, ws: WS) -> Actor:
    return ws.actors.disable(who, actor_id)
