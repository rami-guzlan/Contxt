"""Release 1 additions the redesigned app reads (docs/dev/plans/release1-plan.md): Taste, what
Auto learned from undos, the Brain map, and Scout."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import Field

from ..deps import WS, Who
from ..schemas import Body
from ..scout import Scout

router = APIRouter(prefix="/api")


class TasteIn(Body):
    text: str = Field(max_length=600)
    lens: str
    kind: str = "principle"
    strength: str = "usually"
    not_that: str = Field(default="", max_length=300)


class ScoutFolderIn(Body):
    path: str = Field(max_length=1000)
    project: str | None = None


class ScoutIn(Body):
    folders: list[ScoutFolderIn] | None = None
    formats: dict[str, bool] | None = None


@router.get("/brain/taste")
def taste(who: Who, ws: WS) -> dict[str, Any]:
    """The owner's taste, by lens: principles, this-not-that pairs, words to use or avoid."""
    who.require("brain.read")
    return ws.rt.brain.taste()


@router.post("/brain/taste", status_code=201)
def propose_taste(body: TasteIn, who: Who, ws: WS) -> dict[str, Any]:
    """Write one taste entry: it waits in Catch up, or goes in, as governance says."""
    who.require("brain.propose")
    return ws.rt.brain.propose_taste(
        body.text,
        lens=body.lens,
        kind=body.kind,
        strength=body.strength,
        not_that=body.not_that,
        capture_origin="app",
    )


@router.get("/brain/learned")
def learned(who: Who, ws: WS) -> list[dict[str, Any]]:
    """What Auto learned from the owner's undos: each makes one kind of change ask first."""
    who.require("brain.read")
    return ws.rt.brain.learned()


@router.delete("/brain/learned/{rule_id}")
def forget_learned(rule_id: str, who: Who, ws: WS) -> dict[str, Any]:
    who.require("brain.govern")
    return ws.rt.brain.forget_learned(rule_id)


@router.get("/brain/map")
def brain_map(who: Who, ws: WS, area: str | None = None, page: int = 1) -> dict[str, Any]:
    """The Brain map: what it holds that this person may see, paged (names are data)."""
    who.require("brain.read")
    return ws.rt.brain.brain_map(area=area, page=page)


def _scout(request: Request) -> Scout:
    return Scout(request.app.state.runtime.ws)


@router.get("/scout")
def scout(request: Request, who: Who) -> dict[str, Any]:
    """Scout: the folders, formats, last successful inspection and differences waiting."""
    return _scout(request).overview(who)


@router.put("/scout")
def configure_scout(body: ScoutIn, request: Request, who: Who) -> dict[str, Any]:
    return _scout(request).configure(
        who,
        folders=[f.model_dump() for f in body.folders] if body.folders is not None else None,
        formats=body.formats,
    )


@router.post("/scout/scan")
def scan(request: Request, who: Who) -> dict[str, Any]:
    """Scan now: what changed since the last successful scan, by content."""
    return _scout(request).scan(who)


@router.post("/scout/differences/{diff_id}/bring-in", status_code=201)
def bring_in(diff_id: str, request: Request, who: Who) -> dict[str, Any]:
    """Make a difference a capture, to distill and review as usual."""
    return _scout(request).bring_in(who, diff_id)


@router.post("/scout/differences/{diff_id}/dismiss")
def dismiss(diff_id: str, request: Request, who: Who) -> dict[str, Any]:
    return _scout(request).dismiss(who, diff_id)
