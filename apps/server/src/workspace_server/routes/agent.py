"""The knowledge agent over REST: its suggestions, its actions and conversation (run in the
background through the model the owner chose), its questions, and its settings."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Request

from ..deps import WS, Who
from ..knowledge_agent import AgentWork
from ..models import Models, provider_card
from ..schemas import (
    AgentActionIn,
    AgentAnswerIn,
    AgentChatIn,
    AgentDismissIn,
    AgentEnrichIn,
    AgentKeepIn,
    AgentSettingsIn,
)

router = APIRouter(prefix="/api/brain/agent")


def work(request: Request) -> AgentWork:
    found: AgentWork = request.app.state.runtime.agent
    return found


def models(request: Request) -> Models:
    found: Models = request.app.state.runtime.models
    return found


@router.get("")
def overview(request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """The agent's page: the model chosen and the ones here, the actions, its questions and
    its last runs."""
    out = ws.agent.overview(who)
    out["models"] = [m.to_dict() for m in models(request).list()]
    if ws.agent.chosen_model() is None:
        out["model"] = models(request).default()  # a local model when one is here
    here = {m.id: m for m in models(request).list()}
    wanted = str(out["model"])
    current = here.get(wanted)
    if current is None and wanted.split(":", 1)[0] in here:  # a CLI with a model named
        base = here[wanted.split(":", 1)[0]]
        current = replace(base, id=wanted, label=f"{base.label}, {wanted.split(':', 1)[1]}")
    if current is not None:
        out["provider"] = provider_card(current)  # what it runs on, and where data goes
    out["working"] = [
        j.to_dict()
        for j in work(request).recent(who)
        if j.status in ("waiting", "running") and j.kind in ("action", "chat")
    ]
    return out


@router.put("/settings")
def configure(body: AgentSettingsIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Choose the model the agent works through, and whether its suggestions show."""
    if body.model is not None:
        models(request).choose(body.model)  # it must be one that can answer here
    return ws.agent.configure(who, model=body.model, suggestions=body.suggestions)


@router.get("/suggestions")
def suggestions(who: Who, ws: WS) -> list[dict[str, Any]]:
    """What the agent would bring up now, made by code from the Brain as it is."""
    return ws.agent.suggestions(who)


@router.post("/suggestions/dismiss", status_code=204)
def dismiss(body: AgentDismissIn, who: Who, ws: WS) -> None:
    """Set a suggestion aside for a few days."""
    ws.agent.dismiss(who, body.key, days=body.days)


@router.get("/map")
def outline(who: Who, ws: WS) -> dict[str, Any]:
    """The map of the Brain every model the agent asks is given, made by code."""
    who.require("brain.read")
    found = ws.rt.brain.agent_outline()
    return {"counts": found.get("counts") or {}, "text": found.get("text") or ""}


@router.get("/skills")
def procedures(who: Who, ws: WS) -> list[dict[str, Any]]:
    """The procedures the agent follows, one per action and one for the conversation."""
    who.require("brain.read")
    return ws.rt.brain.agent_skills()


@router.post("/actions/{action}", status_code=201)
def run_action(action: str, body: AgentActionIn, request: Request, who: Who) -> dict[str, Any]:
    """Run one upkeep action through the chosen model, in the background."""
    return work(request).start_action(who, action, model=body.model).to_dict()


@router.get("/enrich")
def enrich_waiting(who: Who, ws: WS) -> dict[str, Any]:
    """How many entries wait for a model to write how they are asked for."""
    who.require("brain.read")
    return {"waiting": len(ws.rt.brain.enrichment_pending())}


@router.post("/enrich", status_code=201)
def enrich(body: AgentEnrichIn, request: Request, who: Who) -> dict[str, Any]:
    """Write how each waiting entry is asked for, through the chosen model, in the
    background; poll /api/brain/agent/jobs/{id}."""
    return work(request).start_enrich(who, model=body.model, limit=body.limit).to_dict()


@router.post("/chat", status_code=201)
def chat(body: AgentChatIn, request: Request, who: Who) -> dict[str, Any]:
    """One turn of the conversation, in the background."""
    history = [t.model_dump() for t in body.history]
    return work(request).start_chat(who, body.message, history, model=body.model).to_dict()


@router.get("/jobs")
def jobs(request: Request, who: Who) -> list[dict[str, Any]]:
    """The agent's work since the app started, newest first."""
    return [j.to_dict() for j in work(request).recent(who)]


@router.get("/jobs/{job_id}")
def job(job_id: str, request: Request, who: Who) -> dict[str, Any]:
    return work(request).get(who, job_id).to_dict()


@router.post("/questions/answer")
def answer(body: AgentAnswerIn, who: Who, ws: WS) -> dict[str, Any]:
    """Act on one of the agent's questions: still true, retire it, mark it disputed, answer
    it in words, done, or set it aside."""
    return ws.agent.answer(who, body.key, body.do, text=body.text)


@router.post("/notes", status_code=201)
def keep(body: AgentKeepIn, who: Who, ws: WS) -> dict[str, Any]:
    """Keep a note the agent suggested in the conversation: it waits in Catch up."""
    return ws.agent.keep_note(who, title=body.title, text=body.text, kind=body.kind, said=body.said)
