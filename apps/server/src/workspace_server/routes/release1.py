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
def brain_map(
    who: Who, ws: WS, area: str | None = None, page: int = 1, tier: str | None = None
) -> dict[str, Any]:
    """The Brain map: what it holds that this person may see, paged (names are data); with
    `tier`, that tier whole."""
    who.require("brain.read")
    return ws.rt.brain.brain_map(area=area, page=page, tier=tier)


@router.get("/brain/map/view")
def brain_map_view(who: Who, ws: WS) -> dict[str, Any]:
    """The map card: every tier whole, the short map exactly as a packet sends it, which
    tiers it cut, and how many sealed projects it leaves out (only the owner sees that)."""
    who.require("brain.read")
    return ws.rt.brain.map_view()


@router.get("/brain/world")
def brain_world(who: Who, ws: WS, since: str | None = None) -> dict[str, Any]:
    """The Brain as a world, for the World page (v4 backend plan, 13.5): the overview, the
    regions, the entries by level, how they relate, what moved since `since`, the lessons
    and the apps that read the Brain."""
    who.require("brain.read")
    return ws.rt.brain.world_view(since=since or None)


@router.post("/brain/world/visit")
def brain_world_visit(who: Who, ws: WS) -> dict[str, Any]:
    """The owner opened the World page: "since my last visit" counts from now on."""
    who.require("brain.read")
    return ws.rt.brain.mark_world_visit()


@router.get("/brain/sections/{item_id:path}")
def sections(item_id: str, who: Who, ws: WS) -> dict[str, Any]:
    """Every section address in one note, lesson or file, to copy."""
    who.require("brain.read")
    return ws.rt.brain.sections(item_id)


@router.get("/brain/open")
def open_address(address: str, who: Who, ws: WS) -> dict[str, Any]:
    """One part by its address (note-id#heading, file#section, lore_id#story)."""
    who.require("brain.read")
    return ws.rt.brain.open_address(address)


class LessonIn(Body):
    title: str = Field(max_length=120)
    story: str = Field(max_length=2000)
    pattern: str = Field(max_length=600)
    words: list[str] = Field(default_factory=list, max_length=20)
    evidence: str = Field(default="", max_length=2000)


@router.get("/brain/lore")
def lore(who: Who, ws: WS) -> list[dict[str, Any]]:
    """The Lore shelf: every lesson with its level and address."""
    who.require("brain.read")
    return ws.rt.brain.lore()


@router.get("/brain/lore/{lesson_id}")
def lesson(lesson_id: str, who: Who, ws: WS) -> dict[str, Any]:
    who.require("brain.read")
    return ws.rt.brain.lesson(lesson_id)


@router.post("/brain/lore", status_code=201)
def propose_lesson(body: LessonIn, who: Who, ws: WS) -> dict[str, Any]:
    """Propose a lesson: it waits in Catch up (Keep, Edit first, Skip) like any other."""
    who.require("brain.propose")
    return ws.rt.brain.propose_lesson(
        title=body.title,
        story=body.story,
        pattern=body.pattern,
        words=body.words,
        evidence=body.evidence,
        capture_origin="app",
    )


@router.get("/brain/sessions/search")
def sessions_search(q: str, who: Who, ws: WS, limit: int = 10) -> list[dict[str, Any]]:
    """Past conversations whose receipts match: session id, date, app, what it was given."""
    who.require("brain.read")
    return ws.rt.brain.sessions_search(q, limit=limit)


def _scout(request: Request) -> Scout:
    return Scout(request.app.state.runtime.ws)


@router.get("/scout")
def scout(request: Request, who: Who) -> dict[str, Any]:
    """Scout: the folders, formats, last successful inspection and differences waiting."""
    return _scout(request).overview(who)


@router.put("/scout")
def configure_scout(body: ScoutIn, request: Request, who: Who) -> dict[str, Any]:
    done = _scout(request).configure(
        who,
        folders=[f.model_dump() for f in body.folders] if body.folders is not None else None,
        formats=body.formats,
    )
    beat = request.app.state.runtime.heartbeat
    if beat is not None:
        beat.scout_changed(who)  # the heartbeat's Scout row says so at once
    return done


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
