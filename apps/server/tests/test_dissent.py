"""Dissent, end to end on the sample Brain: a model challenges an entry and the owner settles
it; the external challenger stays off until turned on, then runs once a week, blind, with the
web as its only extra tool."""

import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

from workspace_server.app import create_app
from workspace_server.challenger import ChallengerWorker
from workspace_server.runners import Runners

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_cli.py")
CLAIM = "Web design projects now run ten to twelve weeks from kickoff to launch."


def fake_resolve(spec):
    return [sys.executable, FAKE] if spec.id == "claude" else None


@pytest.fixture
def client(runtime):
    runtime.runners = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=fake_resolve
    )
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


def finish(owner, run_id, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = owner.ok(owner.get(f"/api/runners/runs/{run_id}"))
        if run["status"] not in ("starting", "running"):
            return run
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish")


def test_a_model_challenges_an_entry_and_the_owner_settles_it(owner, model, runtime):
    reply = model.tool(
        "propose_challenge",
        note_id="facts-services-002",
        claim=CLAIM,
        evidence="The 2026 project tracker shows eleven weeks on average.",
        source="Project tracker, October 2026",
    )
    assert not reply["isError"], reply
    proposal = reply["structuredContent"]["proposal"]
    assert proposal["status"] == "pending"
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    card = next(c for c in plan["judgment"] if c["proposal_id"] == proposal["proposal_id"])
    assert card["type"] == "challenge" and card["with"]["id"] == "facts-services-002"
    assert card["recommend"]["action"] in card["actions"]
    owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={"decisions": [{"action": "approve", "proposal_id": proposal["proposal_id"]}]},
        )
    )
    note = runtime.ws.rt.brain.brain.state().index.note("facts-services-002")
    assert note.confidence == "disputed" and note.meta["other_view"] == CLAIM


def test_the_challenger_runs_only_when_on_once_a_week_blind_with_the_web(owner, model, runtime):
    worker = ChallengerWorker(runtime.ws, runtime.runners)
    assert not worker.run_once()  # off until the owner turns it on
    owner.ok(owner.put("/api/brain/policies", json={"challenger": True}))
    assert worker.run_once()
    (task,) = [
        t
        for t in runtime.ws.tasks.list(runtime.ws.owner(), include_archived=True)
        if t.template == "challenge"
    ]
    assert "Claim under test (id `" in task.instructions
    assert task.output_contract["tool"] == "propose_challenge"
    (run,) = list(runtime.runners.runs.values())
    done = finish(owner, run.id)
    seen = next(e for e in done["events"] if e["kind"] == "text" and e["text"].startswith("debug "))
    argv = __import__("json").loads(seen["text"][len("debug ") :])["argv"]
    assert argv[argv.index("--tools") + 1] == "WebSearch,WebFetch"
    assert "WebSearch" in argv and "Bash" not in argv and "Write" not in argv
    assert not worker.run_once()  # once a week
    claimed = model.tool("claim_task", task_id=task.id)
    assert not claimed["isError"], claimed
    packet = claimed["structuredContent"]["packet"]
    assert packet["brain"]["available"] is False  # blind: no brief presents the claims as true
    assert "Claim under test" in packet["instructions"]["text"]
