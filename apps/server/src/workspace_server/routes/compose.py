"""Compose over REST: a request and what goes with it (skills in order, an agent, notes,
documents, a project), assembled exactly as a model would get it, with its size in tokens;
improved by the chosen model (in the background; poll /api/brain/agent/jobs/{id}); run here as a
task like any skill run; and saved as a prompt with versions (/api/prompts), private to the app."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from brainkit import util as brain_util
from workspace_core.domain.records import Task
from workspace_core.services.prompts import SavedPrompt

from ..deps import WS, Who
from ..mcp.render import packet as render_packet
from ..schemas import ComposeImproveIn, ComposeIn, ComposeRunIn, PromptIn, PromptPatch
from .agents import work

router = APIRouter()


@router.post("/api/compose/assemble")
def assemble(body: ComposeIn, who: Who, ws: WS) -> dict[str, Any]:
    """The whole prompt a model gets for this request and these picks (the instructions, each
    pinned note as it is now, the Brain's brief), its size in tokens and by part, and the short
    request for any AI connected to the Brain. Nothing runs and nothing is recorded."""
    spec = body.spec()
    packet = ws.compose.packet(who, **spec)
    about = packet.pop("about")
    prompt = render_packet(packet)
    parts = [{"label": "Instructions", "tokens": brain_util.tokens(packet["instructions"]["text"])}]
    for item in packet["inputs"]:
        parts.append({"label": f"Note: {item['title']}", "tokens": brain_util.tokens(item["text"])})
    brief = packet["brain"]["text"] or ""
    parts.append({"label": "The Brain's brief", "tokens": brain_util.tokens(brief)})
    short = ws.compose.short(who, **spec)
    return {
        "title": packet["task"]["title"],
        "prompt": prompt,
        "tokens": brain_util.tokens(prompt),
        "exact": bool(brain_util.tokenizer_status()["exact"]),
        "parts": parts,
        "brief": {
            "available": packet["brain"]["available"],
            "entries": len(packet["brain"]["entry_ids"]),
            "note": packet["brain"]["note"],
        },
        "short": short,
        "short_tokens": brain_util.tokens(short),
        "skills": list(about.get("names") or []),
        "agent": about.get("agent"),
        "makes_files": bool(about.get("files")),
    }


@router.post("/api/compose/improve", status_code=201)
def improve(body: ComposeImproveIn, request: Request, who: Who, ws: WS) -> dict[str, Any]:
    """Have the chosen model rewrite the request with what was picked, in the background.
    Nothing changes until the owner takes the new words."""
    spec = body.spec()
    return (
        work(request)
        .start_work(
            who,
            "prompt-improve",
            lambda: ws.compose.improver_prompt(who, **spec),
            ws.compose.read_improved,
            model=body.model,
            message=body.request[:200],
        )
        .to_dict()
    )


@router.post("/api/compose/run", status_code=201)
def run(body: ComposeRunIn, who: Who, ws: WS) -> Task:
    """Run it here: a task on the same queue as every skill and agent run (from a saved prompt,
    `prompt_id` counts it as a use)."""
    return ws.compose.run(who, prompt_id=body.prompt_id, **body.spec())


# ------------------------------------------------------------------------- saved prompts


@router.get("/api/prompts")
def prompts(who: Who, ws: WS, q: str = "", archived: bool = False) -> list[SavedPrompt]:
    """Saved prompts, the most used first; `q` finds them by their words."""
    return ws.prompts.list(who, archived=archived, query=q)


@router.post("/api/prompts", status_code=201)
def save(body: PromptIn, who: Who, ws: WS) -> SavedPrompt:
    return ws.prompts.create(who, title=body.title, body=body.body, picks=body.picks.model_dump())


@router.get("/api/prompts/{prompt_id}")
def prompt(prompt_id: str, who: Who, ws: WS) -> SavedPrompt:
    """One saved prompt, with its versions and how often it ran."""
    return ws.prompts.get(who, prompt_id)


@router.put("/api/prompts/{prompt_id}")
def change(prompt_id: str, body: PromptPatch, who: Who, ws: WS) -> SavedPrompt:
    """New words are a new version; new picks replace the old."""
    return ws.prompts.update(
        who,
        prompt_id,
        title=body.title,
        body=body.body,
        picks=body.picks.model_dump() if body.picks is not None else None,
        expected_version=body.expected_version,
    )


@router.delete("/api/prompts/{prompt_id}")
def archive(prompt_id: str, who: Who, ws: WS) -> SavedPrompt:
    """Set it aside; nothing is deleted."""
    return ws.prompts.archive(who, prompt_id)


@router.post("/api/prompts/{prompt_id}/restore")
def restore(prompt_id: str, who: Who, ws: WS) -> SavedPrompt:
    return ws.prompts.archive(who, prompt_id, archived=False)
