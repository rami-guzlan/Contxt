"""The Test Bench (Release 1 plan, 15.3 to 15.5): an estimate first, then a run; tests and
suites; scores and the summary."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..deps import Who
from ..schemas import BenchRunIn, BenchScoreIn, BenchSuiteIn, BenchSuiteRunIn, BenchTestIn

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


# ---------------------------------------------------------------- tests and suites (15.4)


@router.get("/suites")
def list_suites(request: Request, who: Who) -> dict[str, Any]:
    """Every suite with its tests, from the Brain's bench folder."""
    return {"suites": request.app.state.runtime.suites.suites(who)}


@router.put("/suites/{suite}")
def save_suite(suite: str, body: BenchSuiteIn, request: Request, who: Who) -> dict[str, Any]:
    return request.app.state.runtime.suites.save_suite(who, suite, body.model_dump())


@router.delete("/suites/{suite}")
def delete_suite(suite: str, request: Request, who: Who) -> dict[str, Any]:
    request.app.state.runtime.suites.delete_suite(who, suite)
    return {"deleted": suite}


@router.post("/suites/{suite}/tests", status_code=201)
def add_test(suite: str, body: BenchTestIn, request: Request, who: Who) -> dict[str, Any]:
    """Save a bench request as a test, committed in the Brain's folder."""
    return request.app.state.runtime.suites.save_test(who, suite, body.model_dump())


@router.put("/suites/{suite}/tests/{test}")
def edit_test(
    suite: str, test: str, body: BenchTestIn, request: Request, who: Who
) -> dict[str, Any]:
    return request.app.state.runtime.suites.save_test(who, suite, body.model_dump(), test)


@router.post("/suites/{suite}/tests/{test}/duplicate", status_code=201)
def duplicate_test(suite: str, test: str, request: Request, who: Who) -> dict[str, Any]:
    return request.app.state.runtime.suites.duplicate_test(who, suite, test)


@router.delete("/suites/{suite}/tests/{test}")
def delete_test(suite: str, test: str, request: Request, who: Who) -> dict[str, Any]:
    request.app.state.runtime.suites.delete_test(who, suite, test)
    return {"deleted": test}


@router.post("/suites/{suite}/run", status_code=202)
def run_suite(suite: str, body: BenchSuiteRunIn, request: Request, who: Who) -> dict[str, Any]:
    """Answer every test of the suite and grade each answer, in the background."""
    found = request.app.state.runtime.suites.run_suite(
        who,
        suite,
        modes=body.modes or None,
        runner=body.runner or None,
        model=body.model or None,
        grader=body.grader or None,
    )
    return {"id": found.id, "suite": found.suite, "status": found.status, "tests": found.tests}


@router.get("/suite-runs/{run_id}")
def suite_run(run_id: str, request: Request, who: Who) -> dict[str, Any]:
    return request.app.state.runtime.suites.suite_run(who, run_id)


@router.post("/results/{result_id}/score")
def score(result_id: str, body: BenchScoreIn, request: Request, who: Who) -> dict[str, Any]:
    """A person's score of one answer; it overrides the grader's."""
    return request.app.state.runtime.suites.score(who, result_id, body.model_dump())


@router.get("/summary")
def summary(request: Request, who: Who) -> dict[str, Any]:
    """Win rate by mode, each suite's average by Brain version, and the section signal."""
    return request.app.state.runtime.suites.summary(who)
