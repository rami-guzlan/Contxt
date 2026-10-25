"""The application: one Workspace, wired to the Brain, the connectors and every adapter."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

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
from .brain_testing import TestTheBrain
from .builtin_checks import BuiltinChecks
from .deps import error_response
from .difference import Differences
from .extractor import DocumentExtractor
from .heartbeat import Heartbeat
from .knowledge_agent import AgentWork
from .library import Library
from .mcp import tools as mcp_tools
from .mcp.protocol import McpHandler
from .models import Models
from .orchestration import Orchestration
from .outputs import Outputs
from .routes import (
    agent,
    agents,
    backups,
    brain,
    brain_mcp,
    bus,
    captures,
    compose,
    connections,
    goals,
    heartbeat,
    legacy,
    library,
    live,
    loop,
    mcp,
    notes,
    orchestrators,
    outputs,
    proof,
    release1,
    runners,
    skills,
    system,
    test_the_brain,
    work,
    workflows,
    workspace,
)
from .runners import Runners
from .settings import Settings
from .speech import Speech
from .templates import TemplateLibrary, find_templates_dir
from .triage import Triage, redacts
from .work_with_ai import WorkWithAI


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
    testing: TestTheBrain
    heartbeat: Heartbeat | None = None  # the scheduled read-only loop (heartbeat/)
    closed: bool = False
    # Where the AI apps on this computer keep their own instructions files (a test's
    # scratch folder in tests): Ask the Brain first writes there, with the person's yes.
    home: str = field(default_factory=lambda: os.path.expanduser("~"))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.heartbeat is not None and self.heartbeat.n8n_host is not None:
            self.heartbeat.n8n_host.close()  # Gnomon's own n8n stops with it
        self.testing.close()
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
    if adapter is not None:
        adapter.migrate_governance()
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
    differences = Differences(ws, runners)
    triage = Triage(models)

    def triager(model_id: str, text: str) -> list[int] | None:
        # A cloud model triages redacted text when the preset says so (decisions 7 and 13).
        try:
            policies: dict[str, Any] | None = ws.rt.brain.policies()
        except (OSError, ValueError, RuntimeError, KeyError):
            policies = None
        return triage.keep(model_id, text, redacting=redacts(model_id, policies))

    ws.distill.triager = triager
    return Runtime(
        settings=settings,
        ws=ws,
        brain=adapter,
        templates=templates,
        owner_token=token,
        runners=runners,
        speech=Speech(settings.speech_models),
        differences=differences,
        outputs=Outputs(ws, settings.exports_dir or os.path.join(settings.data_dir, "exports")),
        models=models,
        agent=AgentWork(ws, models),
        library=Library(ws, settings.data_dir),
        testing=TestTheBrain(
            settings,
            ws,
            builtin=BuiltinChecks(settings.data_dir, ws, adapter, differences),
        ),
        heartbeat=_heartbeat(ws, runners, settings),
    )


def _heartbeat(ws: Workspace, runners: Runners, settings: Settings) -> Heartbeat:
    """The heartbeat, with Gnomon's own n8n (in the data folder, when the owner hosts one) and
    the address n8n on this computer posts what it read to."""
    from .heartbeat.n8n_host import N8nHost

    beat = Heartbeat(ws, runners)
    beat.n8n_host = N8nHost(settings.data_dir)
    beat.inbox_url = local_url(settings)
    return beat


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    runtime = runtime or open_runtime(settings or Settings.from_env())
    mcp_tools.AGENT_WORK = runtime.agent  # knowledge_run starts work in the background
    mcp_tools.WORK_WITH_AI = WorkWithAI(runtime.ws, runtime.runners)  # work_ask
    orchestration = Orchestration(runtime.ws, runtime.runners)
    mcp_tools.orchestrator_tools.ORCHESTRATION = orchestration  # the orchestrators_ tools
    if runtime.heartbeat is None:
        runtime.heartbeat = Heartbeat(runtime.ws, runtime.runners)
    runtime.heartbeat.runners = runtime.runners  # the CLIs this app starts (a test's stand-in)
    mcp_tools.HEARTBEAT = runtime.heartbeat  # heartbeat_*

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
    app.state.orchestration = orchestration
    app.state.mcp = McpHandler(runtime.ws, runtime.templates, runtime.runners.contracts)

    @app.exception_handler(WorkspaceError)
    async def workspace_error(_request: Request, exc: WorkspaceError) -> JSONResponse:
        return error_response(exc)

    routers = (
        brain_mcp,
        system,
        notes,
        captures,
        agent,
        agents,
        brain,
        outputs,
        orchestrators,
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
        test_the_brain,
        goals,
        live,
        loop,
        mcp,
        release1,
        heartbeat,
    )
    for module in routers:
        app.include_router(module.router)
    app.include_router(web.router)
    web.mount_web(app, webapp.location(runtime.settings.web_dist))
    return app
