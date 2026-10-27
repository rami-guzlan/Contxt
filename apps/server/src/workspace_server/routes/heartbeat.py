"""The heartbeat (the auto default, section 4): its status, beats, regions and settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import Field

from workspace_core.errors import PermissionDenied, ValidationFailed

from ..deps import Who
from ..heartbeat import Heartbeat
from ..heartbeat.n8n import SECRET_HEADER
from ..schemas import Body

router = APIRouter(prefix="/api/heartbeat")


class ConnectorChoiceIn(Body):
    id: str = Field(max_length=240)
    enabled: bool | None = None
    feeds: list[str] | None = None
    cadence_minutes: int | None = None
    ask: str | None = Field(default=None, max_length=1000)


class SettingsIn(Body):
    cadence: int | None = None
    quiet_hours: str | None = None
    paused: bool | None = None
    cli: str | None = None
    connectors: list[ConnectorChoiceIn] | None = None


class ConnectorIn(Body):
    enabled: bool | None = None
    feeds: list[str] | None = None
    cadence_minutes: int | None = None
    ask: str | None = Field(default=None, max_length=1000)


class OnboardIn(Body):
    clis: list[str] | None = None
    ask: str | None = Field(default=None, max_length=1000)
    pasted: str | None = Field(default=None, max_length=60000)


def _heartbeat(request: Request) -> Heartbeat:
    found: Heartbeat = request.app.state.runtime.heartbeat
    return found


@router.get("/status")
def status(request: Request, who: Who) -> dict[str, Any]:
    """Cadence, quiet hours, the last and next beat, paused or not, the connectors."""
    return _heartbeat(request).status(who)


@router.post("/beat")
def beat(request: Request, who: Who, wait: bool = False) -> dict[str, Any]:
    """Beat now: in the background (its id comes back; the status shows what it reads), or,
    with `wait`, once it is done."""
    return _heartbeat(request).beat(who, "now", wait=wait)


@router.get("/beats")
def beats(request: Request, who: Who, since: str | None = None, limit: int = 20) -> list[Any]:
    return _heartbeat(request).beats(who, since=since, limit=limit)


@router.get("/beats/{beat_id}")
def get_beat(beat_id: str, request: Request, who: Who) -> dict[str, Any]:
    return _heartbeat(request).get_beat(who, beat_id)


@router.get("/regions")
def regions(request: Request, who: Who) -> list[Any]:
    """Live status per Brain region: headline, lines with their source, projects."""
    return _heartbeat(request).regions(who)


@router.post("/lines/{line_id}/undo")
def undo(line_id: str, request: Request, who: Who) -> dict[str, Any]:
    """Undo one line's write; the next beat does not write it again."""
    return _heartbeat(request).undo(who, line_id)


@router.put("/settings")
def configure(body: SettingsIn, request: Request, who: Who) -> dict[str, Any]:
    return _heartbeat(request).configure(
        who,
        cadence=body.cadence,
        quiet=body.quiet_hours,
        paused=body.paused,
        cli=body.cli,
        connectors=[c.model_dump(exclude_unset=True) for c in body.connectors]
        if body.connectors is not None
        else None,
    )


@router.post("/connectors/rescan")
def rescan(request: Request, who: Who) -> dict[str, Any]:
    """Find connectors in my CLIs."""
    return _heartbeat(request).rescan(who)


@router.post("/connectors/{connector_id:path}/test")
def test_connector(connector_id: str, request: Request, who: Who) -> dict[str, Any]:
    """The setup check for one connector: found, signed in, read-only and one sample read.
    Nothing it reads is kept."""
    return _heartbeat(request).test_read(who, connector_id)


@router.put("/connectors/{connector_id}")
def set_connector(
    connector_id: str, body: ConnectorIn, request: Request, who: Who
) -> dict[str, Any]:
    return _heartbeat(request).set_connector(
        who,
        connector_id,
        enabled=body.enabled,
        feeds=body.feeds,
        cadence_minutes=body.cadence_minutes,
        ask=body.ask,
    )


@router.post("/onboard")
def onboard(body: OnboardIn, request: Request, who: Who, wait: bool = False) -> dict[str, Any]:
    """The onboarding beat: each CLI reads what it keeps on me (its memory, my chats, what it
    remembers from its other apps) into context packets, in the background."""
    return _heartbeat(request).onboard(
        who, clis=body.clis, ask=body.ask, pasted=body.pasted, wait=wait
    )


# ------------------------------------------------------------------ reads through n8n

# Addresses an n8n on this computer posts from; anything else is refused.
LOCAL = frozenset({"127.0.0.1", "::1", "localhost"})
# What a reverse proxy adds to a request it passes on. A proxy on this computer (Caddy, Tailscale
# Serve) connects from 127.0.0.1 for whoever sent the request, so a post with one is not local.
FORWARDED = ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip")


def _from_this_computer(request: Request) -> bool:
    """Posted straight from this computer (as n8n here does), not passed on by a proxy."""
    host = request.client.host if request.client else ""
    return host in LOCAL and not any(name in request.headers for name in FORWARDED)


class N8nReadIn(Body):
    name: str = Field(max_length=200)
    workflow: dict[str, Any]
    feeds: list[str] | None = None
    connector_id: str | None = Field(default=None, max_length=240)


@router.post("/n8n", status_code=201)
def add_n8n(body: N8nReadIn, request: Request, who: Who) -> dict[str, Any]:
    """A connector read by an n8n workflow: checked read-only by code, off until turned on.
    The secret its workflow posts with comes back this once."""
    return _heartbeat(request).add_n8n(
        who,
        name=body.name,
        workflow=body.workflow,
        feeds=body.feeds,
        connector_id=body.connector_id,
    )


@router.post("/inbox/{connector_id}")
async def inbox(connector_id: str, request: Request) -> dict[str, Any]:
    """Where an n8n workflow on this computer posts what it read, with its connector's secret
    (not the owner's sign-in: n8n posts here, and only from this computer)."""
    if not _from_this_computer(request):
        raise PermissionDenied("Only an n8n on this computer may post here.")
    try:
        body = await request.json()
    except ValueError as exc:
        raise ValidationFailed("Post the items as JSON.") from exc
    secret = request.headers.get(SECRET_HEADER, "")
    return _heartbeat(request).receive(connector_id, secret, body)


class N8nHostIn(Body):
    action: str = Field(pattern="^(install|start|stop)$")


@router.get("/n8n/host")
def n8n_host(request: Request, who: Who) -> dict[str, Any]:
    """Gnomon's own n8n: installed, installing, running, where."""
    return _heartbeat(request).n8n_status(who)


@router.post("/n8n/host")
def n8n_host_act(body: N8nHostIn, request: Request, who: Who) -> dict[str, Any]:
    """Host n8n here: install it (once, in the background), start it or stop it."""
    return _heartbeat(request).n8n_act(who, body.action)


@router.post("/n8n/suggest")
def suggest_n8n(request: Request, who: Who) -> dict[str, Any]:
    """Search every connected CLI for connectors, then suggest an n8n workflow for each app
    Gnomon has one for (off until signed in to in n8n and turned on)."""
    return _heartbeat(request).suggest_n8n(who)


@router.post("/n8n/errors")
async def n8n_errors(request: Request) -> dict[str, Any]:
    """Where Gnomon's error-report workflow in its n8n says one of its workflows failed (with
    that workflow's own secret, from this computer only)."""
    if not _from_this_computer(request):
        raise PermissionDenied("Only an n8n on this computer may post here.")
    try:
        body = await request.json()
    except ValueError as exc:
        raise ValidationFailed("Post the report as JSON.") from exc
    return _heartbeat(request).n8n_failed(request.headers.get(SECRET_HEADER, ""), body)


class FixIn(Body):
    keep: bool


@router.post("/n8n/{connector_id}/fix")
def suggest_fix(connector_id: str, request: Request, who: Who) -> dict[str, Any]:
    """The knowledge agent suggests a fix for a failed n8n read (kept only with your yes)."""
    return _heartbeat(request).suggest_fix(who, connector_id)


@router.put("/n8n/{connector_id}/fix")
def decide_fix(connector_id: str, body: FixIn, request: Request, who: Who) -> dict[str, Any]:
    """Keep the suggested fix, or skip it."""
    return _heartbeat(request).decide_fix(who, connector_id, body.keep)


# ------------------------------------------------------------------ learning: the buffer


class LearningIn(Body):
    goal: str | None = Field(default=None, max_length=600)
    filters: list[dict[str, Any]] | None = None
    buffer_days: int | None = None
    learn: str | None = None  # nightly (default) or per_beat
    distill_at: str | None = None  # HH:MM, local time
    # Apply during the day: {"connectors": [...], "sheets": [...]} distilled in the beat.
    live: dict[str, list[str]] | None = None


@router.get("/learning")
def learning_settings(request: Request, who: Who) -> dict[str, Any]:
    """The goal, the negative filters and how long the buffer is kept."""
    return _heartbeat(request).learning_settings(who)


@router.put("/learning")
def configure_learning(body: LearningIn, request: Request, who: Who) -> dict[str, Any]:
    """The goal, the negative filters and how long the buffer is kept."""
    return _heartbeat(request).configure_learning(
        who,
        goal=body.goal,
        filters=body.filters,
        buffer_days=body.buffer_days,
        learn=body.learn,
        distill_at=body.distill_at,
        live=body.live,
    )


@router.post("/distill")
def distill_now(request: Request, who: Who, wait: bool = False) -> dict[str, Any]:
    """Distill now: learn from what the buffer holds, without waiting for tonight."""
    return _heartbeat(request).beat(who, "distill", wait=wait)


@router.get("/staged")
def staged(request: Request, who: Who, status: str | None = None) -> list[Any]:
    """Heartbeat › Today: what the buffer holds for the distill."""
    return _heartbeat(request).staged(who, status=status)


@router.post("/staged/{staged_id}/forget")
def forget_staged(staged_id: str, request: Request, who: Who) -> dict[str, Any]:
    return _heartbeat(request).forget_staged(who, staged_id)


@router.post("/staged/{staged_id}/bring-back")
def bring_back(staged_id: str, request: Request, who: Who) -> dict[str, Any]:
    return _heartbeat(request).bring_back(who, staged_id)


@router.get("/still-waiting")
def still_waiting(request: Request, who: Who) -> dict[str, Any]:
    """What the distill sent to Catch up over 14 days ago and still waits for you."""
    return _heartbeat(request).still_waiting(who)
