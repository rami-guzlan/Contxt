"""Running a task now with a CLI on this machine: status, sign-in, isolation and clean-up."""

import json
import os
import sys
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from workspace_server import runners as runners_module
from workspace_server.app import create_app
from workspace_server.runners import Runners

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_cli.py")


def mcp(client, token, method, params=None):
    """An MCP call with the given bearer token (a run's own credential, say)."""
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={"Authorization": f"Bearer {token}", "MCP-Protocol-Version": "2025-06-18"},
    )


def fake_resolve(spec):
    return [sys.executable, FAKE] if spec.id == "claude" else None


@pytest.fixture
def client(runtime):
    runtime.runners = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=fake_resolve
    )
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


@pytest.fixture
def ready_task(model, make_task):
    """A ready task for the Claude Code model, with nothing it depends on."""
    return make_task(model.actor_id, title="Draft launch notes")


def finish(owner, run_id, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = owner.ok(owner.get(f"/api/runners/runs/{run_id}"))
        if run["status"] not in ("starting", "running"):
            return run
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish")


def report(run):
    """What the fake CLI saw: its arguments, folder, prompt and MCP configuration."""
    for event in run["events"]:
        if event["kind"] == "text" and event["text"].startswith("debug "):
            return json.loads(event["text"][len("debug ") :])
    raise AssertionError("no report from the CLI")


def wait_for_report(owner, run_id, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            return report(owner.ok(owner.get(f"/api/runners/runs/{run_id}")))
        except AssertionError:
            time.sleep(0.2)
    raise AssertionError("the CLI never reported")


def test_each_cli_says_whether_it_is_installed_and_signed_in(owner, model):
    claude, codex = owner.ok(owner.get("/api/runners"))
    assert (claude["id"], claude["installed"], claude["signed_in"]) == ("claude", True, True)
    assert claude["version"] == "9.9.9 (Claude Code)" and claude["actor_id"] == model.actor_id
    assert (codex["installed"], codex["one_click"]) == (False, False)
    assert codex["install"] == "npm install -g @openai/codex" and codex["sign_in"] == "codex login"


def test_a_signed_out_cli_says_how_to_sign_in(owner, ready_task, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_SIGNED_IN", "0")
    (claude, _codex) = owner.ok(owner.get("/api/runners", params={"refresh": "true"}))
    assert claude["signed_in"] is False and "claude auth login" in claude["detail"]
    refused = owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]})
    assert refused.status_code == 409 and "claude auth login" in refused.text


def test_signing_in_opens_a_terminal_and_never_sees_the_login(owner, runtime, monkeypatch):
    opened = []
    monkeypatch.setattr(runners_module, "terminal_command", lambda argv, title: ["term", *argv])
    runtime.runners.popen = lambda argv, **kw: opened.append(argv)
    result = owner.ok(owner.post("/api/runners/claude/sign-in"))
    assert result == {"opened": True, "command": "claude auth login"}
    assert opened[0][-2:] == ["auth", "login"]


def test_a_run_streams_its_work_and_leaves_nothing_behind(owner, model, ready_task):
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    assert run["status"] == "running" and run["actor_id"] == model.actor_id
    done = finish(owner, run["id"])
    assert done["status"] == "succeeded" and done["summary"] == "Done: two proposals."
    kinds = [e["kind"] for e in done["events"]]
    for kind in ("status", "text", "tool", "tool_result", "result", "done"):
        assert kind in kinds
    assert next(e for e in done["events"] if e["kind"] == "tool")["name"] == "claim_task"

    seen = report(done)
    argv = seen["argv"]
    for flag in ("--restricted", "--strict-mcp-config", "--no-session-persistence", "-p"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == ""  # no built-in tools: the workspace's only
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert argv[argv.index("--allowedTools") + 1] == "mcp__contxt-app"
    assert ready_task["id"] in seen["prompt"] and "Test workspace" in seen["prompt"]
    assert not os.path.exists(seen["cwd"])  # its folder, with the configuration, is gone
    server = seen["config"]["mcpServers"]["contxt-app"]
    assert (server["type"], server["url"]) == ("http", "http://127.0.0.1:8787/mcp")

    # the run's credential works for nothing once the run is over
    token = server["headers"]["Authorization"].removeprefix("Bearer ")
    assert mcp(owner.client, token, "tools/list").status_code == 401
    credentials = owner.ok(owner.get(f"/api/actors/{model.actor_id}/credentials"))
    assert all(
        c["revoked_at"] for c in credentials if "Run from the workspace" in (c["label"] or "")
    )


def test_a_run_stopped_midway_leaves_a_blocker_on_the_task(owner, ready_task, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "hang")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    seen = wait_for_report(owner, run["id"])
    token = seen["config"]["mcpServers"]["contxt-app"]["headers"]["Authorization"][len("Bearer ") :]
    claimed = mcp(
        owner.client,
        token,
        "tools/call",
        {"name": "claim_task", "arguments": {"task_id": ready_task["id"]}},
    )
    assert not claimed.json()["result"]["isError"], claimed.text
    owner.ok(owner.post(f"/api/runners/runs/{run['id']}/cancel"))
    done = finish(owner, run["id"])
    assert done["status"] == "cancelled"
    task = owner.ok(owner.get(f"/api/tasks/{ready_task['id']}"))
    assert task["status"] == "blocked"
    runs = owner.ok(owner.get(f"/api/tasks/{ready_task['id']}/runs"))
    assert "a person stopped it" in runs[0]["outcome"]["blocked"]


def test_a_cli_that_fails_says_why(owner, ready_task, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "fail")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    done = finish(owner, run["id"])
    assert done["status"] == "failed" and done["exit_code"] == 3
    assert any(e["kind"] == "stderr" and "boom" in e["text"] for e in done["events"])
    assert done["events"][-1]["kind"] == "done" and done["events"][-1]["ok"] is False


def test_one_answer_is_asked_for_with_no_tools_and_says_so(client, runtime):
    # Claude Code's own instructions describe tools: not told it has none, it writes out
    # calls it cannot make (a Bash call, get_skill) instead of the answer.
    seen = json.loads(runtime.runners.ask(runtime.ws.owner(), "Draft the update"))
    argv = seen["argv"]
    assert argv[argv.index("--append-system-prompt") + 1] == runners_module.NO_TOOLS
    assert "no tools" in runners_module.NO_TOOLS
    assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv
    assert argv[argv.index("--output-format") + 1] == "json" and "--restricted" in argv
    assert seen["config"] == {"mcpServers": {}} and seen["prompt"] == "Draft the update"
    assert not os.path.exists(seen["cwd"])  # its empty folder is gone


def test_what_claude_code_used_is_counted_in_the_cost_report(owner, model, ready_task, runtime):
    runtime.runners.ask(runtime.ws.owner(), "Is this note still true?", job="check")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    finish(owner, run["id"])
    found = owner.ok(owner.get("/api/brain/report?days=1&quality=false"))
    today = found["spend"]["days"][-1]
    jobs = {j["job"]: j for j in today["jobs"]}
    assert jobs["check"]["calls"] == 1 and jobs["run"]["calls"] == 1
    assert jobs["run"]["model"] == "claude-opus-5-5"
    # Claude Code's own cost is kept as it reported it.
    assert abs(today["lines"]["jobs"]["usd"] - 2 * 0.0123) < 1e-6
    assert "jobs" in found["text"]


def test_calibration_measures_the_brain_text_with_claudes_counts(owner, runtime, capsys):
    from workspace_server import cli

    owner.ok(owner.get("/api/brain/status"))
    runtime.ws.rt.brain.brain.context("What is the studio's voice?")
    assert cli._tokens(runtime, "calibrate") == 0
    out = capsys.readouterr().out
    assert "kernel: estimated" in out and "Claude tokens" in out
    factor = owner.ok(owner.get("/api/brain/report?days=1&quality=false"))["spend"]["factor"]
    # The fake CLI counts a character as a quarter token, as the estimate does.
    assert factor["measured"] and 0.9 <= factor["factor"] <= 1.1
    assert factor["method"] == "claude code"


def test_any_shape_of_output_is_read_without_error():
    """Claude Code says some things as plain text, and a tool's result can hold an image it
    looked at (a preview it rendered): each reads, nothing raises."""
    plain = {"type": "user", "message": {"content": "A plain reminder."}}
    assert runners_module.describe(json.dumps(plain)) == []
    looked = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "content": [
                        {"type": "image", "source": {}},
                        "a part",
                        {"type": "text", "text": "OK"},
                    ],
                },
                "a stray string",
            ]
        },
    }
    (event,) = runners_module.describe(json.dumps(looked))
    assert event == {"kind": "tool_result", "ok": True, "text": "[an image] a part OK"}
    said = {"type": "assistant", "message": {"content": "Just text."}}
    assert runners_module.describe(json.dumps(said)) == [{"kind": "text", "text": "Just text."}]
    assert runners_module.describe(json.dumps({"type": "assistant", "message": "odd"})) == []
    assert runners_module.describe(
        json.dumps({"type": "system", "subtype": "init", "mcp_servers": ["x"]})
    )


def test_a_run_whose_watch_breaks_still_ends_and_revokes_its_credential(
    owner, model, ready_task, monkeypatch
):
    def broken(self, run, token, ended):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(Runners, "_settle", broken)
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    done = finish(owner, run["id"])
    assert done["status"] == "succeeded" and done["finished_at"]
    assert any(
        e["kind"] == "error" and "the database went away" in e["text"] for e in done["events"]
    )
    assert done["events"][-1]["kind"] == "done"
    token = report(done)["config"]["mcpServers"]["contxt-app"]["headers"]["Authorization"]
    assert mcp(owner.client, token.removeprefix("Bearer "), "tools/list").status_code == 401


def test_credentials_left_by_a_stopped_server_are_revoked(runtime, model, clock):
    ws = runtime.ws
    owner = ws.owner()
    left = ws.actors.issue_token(owner, model.actor_id, label="Run from the workspace (lrun_old)")
    kept = ws.actors.issue_token(owner, model.actor_id, label="Claude Desktop")
    runners = Runners(ws, runtime.templates, base_url="http://127.0.0.1:8787", timeout=600)
    assert runners.sweep() == 0  # it may still be running: within its time limit
    clock.advance(timedelta(seconds=600 + 301))
    fresh = ws.actors.issue_token(owner, model.actor_id, label="Run from the workspace (lrun_new)")
    assert runners.sweep() == 1
    states = {c.id: c.revoked_at for c in ws.actors.credentials(owner, model.actor_id)}
    assert states[left.credential.id] and not states[kept.credential.id]
    assert not states[fresh.credential.id]


def test_only_the_owner_runs_things_here(model, ready_task):
    assert model.get("/api/runners").status_code == 403
    started = model.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]})
    assert started.status_code == 403


def test_another_models_task_stays_theirs(owner, make_task):
    codex = owner.ok(
        owner.post("/api/connections", json={"name": "Codex", "provider": "codex"}), 201
    )
    task = make_task(codex["actor"]["id"], title="Tidy the backlog")
    refused = owner.post("/api/runners/claude/runs", json={"task_id": task["id"]})
    assert refused.status_code == 409 and "assigned to Codex" in refused.text


def test_a_request_waiting_for_a_model_goes_to_this_computers(owner, note):
    waiting = owner.ok(owner.post(f"/api/notes/{note['id']}/remember", json={}), 201)
    assert waiting["status"] == "draft" and waiting["assignee_id"] is None
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": waiting["id"]}), 201)
    finish(owner, run["id"])
    task = owner.ok(owner.get(f"/api/tasks/{waiting['id']}"))
    actor = next(a for a in owner.ok(owner.get("/api/actors")) if a["id"] == task["assignee_id"])
    assert actor["name"] == "Claude Code (this computer)" and actor["provider"] == "claude-code"
    credentials = owner.ok(owner.get(f"/api/actors/{actor['id']}/credentials"))
    kept = [c for c in credentials if not c["revoked_at"]]
    assert [c["label"] for c in kept] == [
        "Kept for runs from this computer; its token was never shown"
    ]
    assert any("Run from the workspace" in c["label"] and c["revoked_at"] for c in credentials)


def test_a_reconcile_request_runs_from_this_computer(owner):
    made = owner.ok(
        owner.post(
            "/api/brain/proposals",
            json={
                "title": "Web project length",
                "statement": "Web projects run ten weeks.",
                "evidence": "The new plan",
            },
        ),
        201,
    )
    task = owner.ok(
        owner.post(
            "/api/brain/reconcile",
            json={
                "proposal_id": made["proposal_id"],
                "entry_id": "facts-services-002",
                "current": "proposal",
            },
        ),
        201,
    )
    assert (task["template"], task["status"], task["assignee_id"]) == ("reconcile", "draft", None)
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": task["id"]}), 201)
    finish(owner, run["id"])
    started = owner.ok(owner.get(f"/api/tasks/{task['id']}"))
    assert started["assignee_id"]  # this computer's Claude Code took it


def test_any_client_can_run_a_task_from_its_prompt(owner, ready_task):
    prompt = owner.ok(owner.get(f"/api/tasks/{ready_task['id']}/prompt"))["prompt"]
    assert ready_task["id"] in prompt and "Test workspace" in prompt and "claim_task" in prompt


def test_a_run_carries_its_contract_in_its_prompt_its_hooks_and_its_record(owner, ready_task):
    from workspace_server.anchoring import FINISH_CHECK

    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    done = finish(owner, run["id"])
    seen = report(done)
    assert seen["prompt"].startswith("## Run contract")
    assert "Objective: Draft launch notes" in seen["prompt"] and ready_task["id"] in seen["prompt"]
    argv = seen["argv"]
    assert "--settings" in argv and "--restricted" in argv
    assert done["contract"]["objective"].startswith("Draft launch notes")
    assert done["contract"]["budget"]["steps"] == 60
    hooks = next(
        json.loads(e["text"][len("hooks ") :])
        for e in done["events"]
        if e["kind"] == "text" and e["text"].startswith("hooks ")
    )
    assert hooks["pre"] == [""] and hooks["post"] == [""]  # in scope, nothing to re-anchor yet
    sent_back = json.loads(hooks["stop"][0])
    assert sent_back["decision"] == "block" and "complete_task" in sent_back["reason"]
    assert hooks["stop"][1] == ""  # the second time it may stop
    checks = done["checks"]
    assert checks["steps"] == 1 and checks["blocked"] == []
    assert checks["gate"] == {"passed": False, "missing": [FINISH_CHECK], "sent_back": False}
    line = next(e for e in done["events"] if e["kind"] == "checks")
    assert "did not finish as its contract asks" in line["text"]


def test_the_apps_replies_to_a_run_repeat_its_contract(owner, ready_task, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "hang")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    seen = wait_for_report(owner, run["id"])
    server = seen["config"]["mcpServers"]["contxt-app"]
    token = server["headers"]["Authorization"].removeprefix("Bearer ")
    texts = []
    for _ in range(5):
        reply = mcp(owner.client, token, "tools/call", {"name": "get_due_tasks", "arguments": {}})
        texts.append(reply.json()["result"]["content"][0]["text"])
    assert "Run contract: Draft launch notes" in texts[0]
    assert all("Run contract" not in text for text in texts[1:4])
    assert "Run contract: Draft launch notes" in texts[4]
    owner.ok(owner.post(f"/api/runners/runs/{run['id']}/cancel"))
    finish(owner, run["id"])
