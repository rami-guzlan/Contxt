"""Workflows over REST and MCP, on the sample Brain: built, run, decided at a check, taken away
as a file and brought back; started by another AI only when the owner allows it; moved along by
the server's worker (due runs, a step started here, upkeep run and reported); and a connector
step's run, which alone loads the owner's own MCP servers and may call only its named tools."""

import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

from workspace_server.app import create_app
from workspace_server.flows import SERVER_LINE, WorkflowWorker
from workspace_server.runners import Runners

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_cli.py")
POSTS = """---
name: weekly-posts
description: Draft the week's LinkedIn posts from the content calendar.
artifacts:
  - post
---
# /weekly-posts

1. Draft one post per day.
"""
STEP = {"kind": "skill", "skill": "weekly-posts", "ask": "Three posts about async reviews."}


def fake_resolve(spec):
    return [sys.executable, FAKE] if spec.id == "claude" else None


@pytest.fixture
def client(runtime):
    runtime.runners = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=fake_resolve
    )
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def posts_skill(brain_vault):
    folder = os.path.join(brain_vault, "skills", "social", "weekly-posts")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(POSTS)


def finish_step(model, task_id, text):
    claim = model.tool("claim_task", task_id=task_id)["structuredContent"]
    run_id = claim["run"]["id"]
    model.tool("save_skill_result", run_id=run_id, title="Posts", text=text)
    model.tool("complete_task", run_id=run_id, summary="Done.")
    return claim


def test_a_workflow_is_built_run_and_decided_at_its_check(owner, model, runtime):
    made = owner.ok(
        owner.post(
            "/api/workflows",
            json={
                "name": "Weekly posts",
                "schedule": {"kind": "weekly", "days": ["mon"], "time": "09:00"},
                "steps": [
                    STEP,
                    {"kind": "check", "ask": "Read them first."},
                    {"kind": "prompt", "text": "One blurb from the posts."},
                ],
            },
        ),
        201,
    )
    assert made["when"] == "Every Monday at 09:00 (America/New_York)" and made["next_due_at"]
    assert (
        owner.post("/api/workflows", json={"name": "Bad", "steps": [{"kind": "nope"}]}).status_code
        == 422
    )
    assert [t["id"] for t in owner.ok(owner.get("/api/workflows/templates"))][0] == "weekly-upkeep"
    run = owner.ok(owner.post(f"/api/workflows/{made['id']}/run", json={}), 201)
    assert run["status"] == "running" and run["steps"][0]["status"] == "running"
    assert owner.post(f"/api/workflows/{made['id']}/run", json={}).status_code == 409
    finish_step(model, run["steps"][0]["task_id"], "Post one.")
    runtime.ws.workflows.advance(runtime.ws.owner())
    (waiting,) = owner.ok(owner.get("/api/workflows/waiting"))
    assert waiting["id"] == run["id"] and waiting["waiting"]["result"]["excerpt"] == "Post one."
    went = owner.ok(
        owner.post(
            f"/api/workflows/runs/{run['id']}/decide", json={"go": True, "edit": "Post one, short."}
        )
    )
    assert went["status"] == "running" and went["step"] == 2
    third = model.tool("claim_task", task_id=went["steps"][2]["task_id"])["structuredContent"]
    assert any(i.get("text") == "Post one, short." for i in third["packet"]["inputs"])
    stopped = owner.ok(owner.post(f"/api/workflows/runs/{run['id']}/stop"))
    assert stopped["status"] == "stopped"
    listed = owner.ok(owner.get(f"/api/workflows/{made['id']}/runs"))
    assert [r["id"] for r in listed] == [run["id"]]
    assert owner.ok(owner.get("/api/workflows"))[0]["last_run"]["status"] == "stopped"


def test_a_workflow_goes_out_as_a_file_and_comes_back_switched_off(owner):
    made = owner.ok(
        owner.post("/api/workflows", json={"name": "Weekly posts: Q4", "steps": [STEP]}), 201
    )
    out = owner.get(f"/api/workflows/{made['id']}/export")
    assert 'filename="Weekly posts Q4.json"' in out.headers["content-disposition"]
    data = json.loads(out.text)
    assert data["contxt"] == "workflow" and data["steps"][0]["skill"] == "weekly-posts"
    back = owner.ok(owner.post("/api/workflows/import", json=data), 201)
    assert back["id"] != made["id"] and back["enabled"] is False and back["steps"] == made["steps"]
    assert owner.post("/api/workflows/import", json={"name": "x"}).status_code == 422
    owner.ok(owner.delete(f"/api/workflows/{back['id']}"))
    assert [w["id"] for w in owner.ok(owner.get("/api/workflows"))] == [made["id"]]


def test_other_ais_start_only_workflows_opened_to_them(owner, model):
    made = owner.ok(
        owner.post("/api/workflows", json={"name": "Weekly posts", "steps": [STEP]}), 201
    )
    listed = model.tool("list_workflows")
    assert "No workflow is open to other AIs" in listed["content"][0]["text"]
    refused = model.tool("run_workflow", name="Weekly posts")
    assert refused.get("isError")
    owner.ok(
        owner.put(
            f"/api/workflows/{made['id']}",
            json={"name": "Weekly posts", "steps": [STEP], "ai": True},
        )
    )
    assert "Weekly posts (1 steps)" in model.tool("list_workflows")["content"][0]["text"]
    started = model.tool("run_workflow", name="weekly posts", request="Focus on Friday reviews.")
    run = started["structuredContent"]["run"]
    assert run["trigger"] == "ai" and run["note"] == "Started by Claude Code."
    assert model.tool("run_workflow", name="Weekly posts").get("isError")  # one at a time


class StubRunners:
    """Claude Code here, as the worker sees it: whether one is going, and what it starts."""

    def __init__(self):
        self.runs = {}
        self.started = []

    def statuses(self, who):
        class Status:
            id = "claude"
            installed = True
            signed_in = True

        return [Status()]

    def start(self, who, runner_id, task_id):
        self.started.append((runner_id, task_id))


class StubAgent:
    """The knowledge agent's jobs, as the worker sees them."""

    def __init__(self):
        self.jobs = {}

    def start_action(self, who, action):
        class Job:
            pass

        job = Job()
        job.id, job.status, job.result, job.error = f"ajob_{len(self.jobs)}", "running", {}, None
        self.jobs[job.id] = job
        return job


def test_the_worker_starts_steps_here_and_runs_upkeep(runtime, owner):
    ws = runtime.ws
    made = owner.ok(
        owner.post(
            "/api/workflows",
            json={
                "name": "Upkeep then posts",
                "steps": [{"kind": "upkeep", "action": "tidy-repeats"}, STEP],
            },
        ),
        201,
    )
    run = owner.ok(owner.post(f"/api/workflows/{made['id']}/run", json={}), 201)
    runners, agent = StubRunners(), StubAgent()
    worker = WorkflowWorker(ws, runners, agent)
    assert worker.tick()["upkeep"] == 1
    (job,) = agent.jobs.values()
    assert ws.workflows.run_of(ws.owner(), run["id"]).steps[0]["job_id"] == job.id
    job.status, job.result = "done", {"summary": "No repeats found."}
    worker.tick()
    moved = ws.workflows.run_of(ws.owner(), run["id"])
    assert moved.step == 1 and moved.steps[0]["result"] == {"text": "No repeats found."}
    worker.tick()
    assert runners.started == [("claude", moved.steps[1]["task_id"])]
    runners.runs["busy"] = type("Run", (), {"status": "running"})()
    assert worker.tick()["ran"] == 0  # one run at a time on this computer


def test_connector_lines_are_read_from_claude_mcp_list():
    line = SERVER_LINE.match("hubspot: https://mcp.hubspot.com/mcp (HTTP) - ✓ Connected")
    assert line and (line["name"], line["state"]) == ("hubspot", "✓ Connected")
    assert SERVER_LINE.match("Checking MCP server health...") is None


def report(run):
    for event in run["events"]:
        if event["kind"] == "text" and event["text"].startswith("debug "):
            return json.loads(event["text"][len("debug ") :])
    raise AssertionError("no report from the CLI")


def test_a_connector_steps_run_loads_the_owners_servers_with_only_its_tools(owner, model):
    tools = ["mcp__hubspot__search_crm_objects", "mcp__hubspot__get_crm_objects"]
    made = owner.ok(
        owner.post(
            "/api/workflows",
            json={
                "name": "Deals",
                "steps": [{"kind": "connector", "ask": "This week's new deals.", "tools": tools}],
            },
        ),
        201,
    )
    run = owner.ok(owner.post(f"/api/workflows/{made['id']}/run", json={}), 201)
    started = owner.ok(
        owner.post("/api/runners/claude/runs", json={"task_id": run["steps"][0]["task_id"]}), 201
    )
    deadline, seen = time.monotonic() + 30, None
    while seen is None and time.monotonic() < deadline:
        try:
            seen = report(owner.ok(owner.get(f"/api/runners/runs/{started['id']}")))
        except AssertionError:
            time.sleep(0.2)
    assert seen is not None
    argv = seen["argv"]
    assert "--strict-mcp-config" not in argv and "--restricted" in argv
    allowed = argv[argv.index("--allowedTools") + 1 : argv.index("--no-session-persistence")]
    assert allowed == ["mcp__contxt-app", *tools]
    assert argv[argv.index("--tools") + 1] == ""  # still no built-in tools
