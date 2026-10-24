"""The heartbeat (the auto default, section 4): its status, beats, regions and settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import Field

from ..deps import Who
from ..heartbeat import Heartbeat
from ..schemas import Body

router = APIRouter(prefix="/api/heartbeat")


class ConnectorChoiceIn(Body):
    id: str = Field(max_length=240)
    enabled: bool | None = None
    feeds: list[str] | None = None
    cadence_minutes: int | None = None


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
    )
