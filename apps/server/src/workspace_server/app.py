"""The application: one Workspace, wired to the Brain, the connectors and every adapter."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from workspace_connectors.destinations import FolderDestination
from workspace_core import __version__
from workspace_core.clock import Clock
from workspace_core.errors import WorkspaceError
from workspace_core.ports import NoBrain
from workspace_core.workspace import Workspace

from . import web, webapp
from .brain_adapter import BrainKitAdapter
from .deps import error_response
from .difference import Differences
from .extractor import DocumentExtractor
from .knowledge_agent import AgentWork
from .library import Library
from .mcp.protocol import McpHandler
from .models import Models
from .outputs import Outputs
from .routes import (
    agent,
    agents,
    backups,
    brain,
    bus,
    captures,
    compose,
    connections,
    legacy,
    library,
    mcp,
    notes,
    outputs,
    proof,
    runners,
    skills,
    system,
    work,
    workflows,
    workspace,
)
from .runners import Runners
from .settings import Settings
from .speech import Speech
from .templates import TemplateLibrary, find_templates_dir


@dataclass
class Runtime:
    settings: Settings
    ws: Workspace
    brain: BrainKitAdapter | None
    templates: TemplateLibrary
    owner_token: str
    runners: Runners
    speech: Speech
    differences: Differences
    outputs: Outputs
    models: Models
    agent: AgentWork
    library: Library
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.runners.close()
        self.ws.close()
        if self.brain is not None:
            self.brain.close()


def local_url(settings: Settings) -> str:
    """Where a CLI on this machine reaches the server: loopback unless bound elsewhere."""
    host = settings.host
    if host in ("", "0.0.0.0", "::", "localhost"):
        host = "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{settings.port}"


def open_runtime(settings: Settings, *, clock: Clock | None = None) -> Runtime:
    """Open the workspace the settings describe; migrations run, the owner token registers."""
    os.makedirs(settings.data_dir, exist_ok=True)
    adapter = (
        BrainKitAdapter(settings.brain_vault, embeddings=settings.brain_embeddings)
        if settings.brain_vault
        else None
    )
    ws = Workspace.open(
        settings.data_dir,
        database_url=settings.database_url,
        clock=clock,
        brain=adapter or NoBrain(),
        extractor=DocumentExtractor(),
        name=settings.name,
        timezone=settings.timezone,
        lease_seconds=settings.lease_seconds,
    )
    ws.add_destination(
        FolderDestination(settings.exports_dir or os.path.join(settings.data_dir, "exports"))
    )
    token = settings.resolved_owner_token()
    ws.actors.register_token(ws.owner_id, token, "Owner token")
    templates = TemplateLibrary(find_templates_dir())
    runners = Runners(
        ws,
        templates,
        base_url=local_url(settings),
        outputs=settings.exports_dir or os.path.join(settings.data_dir, "exports"),
    )
    models = Models(runners)
    return Runtime(
        settings=settings,
        ws=ws,
        brain=adapter,
        templates=templates,
        owner_token=token,
        runners=runners,
        speech=Speech(settings.speech_models),
        differences=Differences(ws, runners),
        outputs=Outputs(ws, settings.exports_dir or os.path.join(settings.data_dir, "exports")),
        models=models,
        agent=AgentWork(ws, models),
        library=Library(ws, settings.data_dir),
    )


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    runtime = runtime or open_runtime(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        runtime.close()

    app = FastAPI(
        title="Brain",
        version=__version__,
        lifespan=lifespan,
        description="REST API for the web UI. The app's own AI work reaches models through "
        "the MCP endpoint at /mcp, with their own bearer token.",
    )
    app.state.runtime = runtime
    app.state.settings = runtime.settings
    app.state.ws = runtime.ws
    app.state.brain = runtime.brain
    app.state.templates = runtime.templates
    app.state.runners = runtime.runners
    app.state.mcp = McpHandler(runtime.ws, runtime.templates, runtime.runners.contracts)

    @app.exception_handler(WorkspaceError)
    async def workspace_error(_request: Request, exc: WorkspaceError) -> JSONResponse:
        return error_response(exc)

    routers = (
        system,
        notes,
        captures,
        agent,
        agents,
        brain,
        outputs,
        proof,
        skills,
        bus,
        connections,
        runners,
        legacy,
        library,
        backups,
        workspace,
        compose,
        workflows,
        work,
        mcp,
    )
    for module in routers:
        app.include_router(module.router)
    app.include_router(web.router)
    web.mount_web(app, webapp.location(runtime.settings.web_dist))
    return app
