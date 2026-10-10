"""Settings > Test the Brain over REST: the owner runs the tests and reads their results.

Every route is the owner's alone. The page reads results, and writes nothing but starting and
cancelling a run (and which Lab folder it reads, stored on this machine); it never writes
approvals, gates or labels.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..brain_testing import TestTheBrain
from ..deps import Who

router = APIRouter(prefix="/api/test-the-brain")


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(min_length=1, max_length=64)
    suite: str | None = Field(default=None, max_length=64)
    confirm: bool = False
    request: str | None = Field(default=None, max_length=2000)


class WatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: str | None = Field(default=None, max_length=2000)
    run: str | None = Field(default=None, max_length=120)
    case: str | None = Field(default=None, max_length=120)


class LabIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder: str = Field(min_length=1, max_length=1000)


def owner_only(request: Request, who: Who) -> TestTheBrain:
    """The service, for the owner only (administering the workspace stays with people). It is
    a dependency, so a refusal comes before the request body is even read."""
    who.require("workspace.admin")
    found: TestTheBrain = request.app.state.runtime.testing
    return found


Testing = Annotated[TestTheBrain, Depends(owner_only)]


@router.get("")
def state(testing: Testing) -> dict[str, Any]:
    return testing.state()


@router.post("/lab")
def connect(body: LabIn, testing: Testing) -> dict[str, Any]:
    return testing.connect(body.folder)


@router.delete("/lab")
def disconnect(testing: Testing) -> dict[str, Any]:
    return testing.disconnect()


@router.get("/runs")
def runs(testing: Testing, kind: str | None = None) -> dict[str, Any]:
    return {"runs": testing.runs(kind)}


@router.get("/runs/{run}")
def run(run: str, testing: Testing) -> dict[str, Any]:
    return testing.run(run)


@router.get("/runs/{run}/cases")
def cases(
    run: str,
    testing: Testing,
    kind: str | None = None,
    suite: str | None = None,
    result: str | None = Query(default=None, pattern="^(pass|fail)$"),
    gate: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    passed = None if result is None else result == "pass"
    return testing.cases(
        run, kind=kind, suite=suite, passed=passed, gate=gate, offset=offset, limit=limit
    )


@router.get("/runs/{run}/cases/{case_id}")
def case(run: str, case_id: str, testing: Testing) -> dict[str, Any]:
    return testing.case(run, case_id)


@router.get("/overview")
def overview(testing: Testing) -> dict[str, Any]:
    return testing.overview()


@router.get("/gates")
def gates(testing: Testing) -> dict[str, Any]:
    return testing.gates()


@router.get("/compare")
def compare(a: str, b: str, testing: Testing) -> dict[str, Any]:
    return testing.compare(a, b)


@router.get("/live")
def live(testing: Testing, after: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return testing.live(after)


@router.post("/runs", status_code=202)
def start(body: StartIn, testing: Testing) -> dict[str, Any]:
    return testing.start(body.kind, body.suite, body.confirm, body.request)


@router.post("/watch")
def watch(body: WatchIn, testing: Testing) -> dict[str, Any]:
    """Read only: routes the request on this app's Brain and records nothing."""
    return testing.watch(request=body.request, run=body.run, case=body.case)


@router.post("/runs/{run}/cancel")
def cancel(run: str, testing: Testing) -> dict[str, Any]:
    return testing.cancel(run)
