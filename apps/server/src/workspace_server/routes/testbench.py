"""The Test Bench's three panels (Release 1 plan, 15.3): an estimate first, then a run."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..deps import Who
from ..schemas import BenchRunIn

router = APIRouter(prefix="/api/bench")


def _args(body: BenchRunIn) -> dict[str, Any]:
    return {
        "project": body.project or None,
        "modes": body.modes or None,
        "include": body.include or None,
        "exclude": body.exclude or None,
        "runner": body.runner or "claude",
        "model": body.model or None,
    }


@router.post("/estimate")
def estimate(body: BenchRunIn, request: Request, who: Who) -> dict[str, Any]:
    """What a run would send to the provider, panel by panel, before Run is pressed."""
    return request.app.state.runtime.bench.estimate(who, body.request, **_args(body))


@router.post("/runs", status_code=202)
def start_run(body: BenchRunIn, request: Request, who: Who) -> dict[str, Any]:
    """Answer the request with no brain, the full brain and the custom packet, by the same
    runner and model, without tools. It runs in the background: poll the run."""
    found = request.app.state.runtime.bench.start(who, body.request, **_args(body))
    return found.to_dict()


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request, who: Who) -> dict[str, Any]:
    return request.app.state.runtime.bench.get(who, run_id).to_dict()
