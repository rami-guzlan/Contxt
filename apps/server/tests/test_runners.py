"""Running a task now with a CLI on this machine: status, sign-in, isolation and clean-up."""

import json
import os
import sys
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from workspace_core.errors import Conflict
from workspace_server import runners as runners_module
from workspace_server.app import create_app
from workspace_server.runners import Runners

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_cli.py")
FAKE_OTHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_other_cli.py")


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


def run_token(seen):
    """The run's own credential, read from the settings file the CLI was given (its stream
    shows it masked); only while the run is going, since its folder goes when it ends."""
    argv = seen["argv"]
    with open(argv[argv.index("--mcp-config") + 1], encoding="utf-8") as handle:
        config = json.load(handle)
    return config["mcpServers"]["contxt-app"]["headers"]["Authorization"].removeprefix("Bearer ")


def wait_for_report(owner, run_id, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            return report(owner.ok(owner.get(f"/api/runners/runs/{run_id}")))
        except AssertionError:
            time.sleep(0.2)
    raise AssertionError("the CLI never reported")


def test_each_cli_says_whether_it_is_installed_and_signed_in(owner, model):
    claude, codex, gemini = owner.ok(owner.get("/api/runners"))
    assert (claude["id"], claude["installed"], claude["signed_in"]) == ("claude", True, True)
    assert claude["version"] == "9.9.9 (Claude Code)" and claude["actor_id"] == model.actor_id
    assert (codex["installed"], codex["one_click"]) == (False, False)
    assert codex["install"] == "npm install -g @openai/codex" and codex["sign_in"] == "codex login"
    assert (gemini["id"], gemini["installed"], gemini["one_click"]) == ("gemini", False, False)
    assert gemini["install"] == "npm install -g @google/gemini-cli"


def test_a_signed_out_cli_says_how_to_sign_in(owner, ready_task, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_SIGNED_IN", "0")
    (claude, _codex, _gemini) = owner.ok(owner.get("/api/runners", params={"refresh": "true"}))
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

    # the run's credential never shows in its stream, and works for nothing once it is over
    assert server["headers"]["Authorization"] == "Bearer [masked]"
    credentials = owner.ok(owner.get(f"/api/actors/{model.actor_id}/credentials"))
    assert all(
        c["revoked_at"] for c in credentials if "Run from the workspace" in (c["label"] or "")
    )


def test_a_runs_stream_is_kept_masked_and_replays_after_a_restart(owner, ready_task, runtime):
    """One stream per run (UX C): kept on disk with its credentials masked, so a finished run
    replays after the app restarts, with the brief it was given."""
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    done = finish(owner, run["id"])
    shown = json.dumps(done["events"])
    # The run's own credential (in the settings the CLI printed) never reaches the stream.
    assert "wst_" not in shown and "Bearer [masked]" in shown
    folder = os.path.join(runtime.ws.data_dir, "runs")
    with open(os.path.join(folder, f"{run['id']}.jsonl"), encoding="utf-8") as handle:
        kept = handle.read()
    assert "wst_" not in kept and '"kind": "done"' in kept

    runtime.runners.runs.clear()  # what a restart forgets
    again = owner.ok(owner.get(f"/api/runners/runs/{run['id']}"))
    assert again["status"] == "succeeded"
    assert [e["seq"] for e in again["events"]] == [e["seq"] for e in done["events"]]
    assert run["id"] in [r["id"] for r in owner.ok(owner.get("/api/runners/runs"))]
    brief = owner.ok(owner.get(f"/api/runners/runs/{run['id']}/packet"))
    assert brief["available"] and "# Run: Draft launch notes" in brief["text"]
    assert owner.get("/api/runners/runs/lrun_nothing_here").status_code == 404


def test_secrets_are_masked_and_ordinary_words_are_not():
    mask = runners_module.mask
    assert mask("token: abcdef123456") == "token: [masked]"
    assert mask("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.x") == "Authorization: Bearer [masked]"
    assert mask("key sk-ant-api03-abcdefghijklmnop") == "key [masked]"
    assert mask("my password=hunter2xyz") == "my password=[masked]"
    for plain in ("token count 123456 used", "tokens: 1200", "the bearer of good news"):
        assert mask(plain) == plain


def test_a_run_whose_workspace_tools_do_not_connect_fails_and_says_so(
    owner, ready_task, monkeypatch
):
    # Claude Code carries on without a server that failed to connect, and its answer says it
    # could do nothing; the run must not count as done.
    monkeypatch.setenv("FAKE_CLI_MCP", "failed")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    done = finish(owner, run["id"])
    assert done["status"] == "failed"
    said = " ".join(e.get("text") or "" for e in done["events"])
    assert "did not connect" in said and "/mcp" in said


def test_serving_on_another_port_points_runs_at_it(runtime):
    from workspace_server.cli import listen

    listen(runtime, "0.0.0.0", 8911)
    assert runtime.runners.base_url == "http://127.0.0.1:8911"
    assert runtime.settings.port == 8911


def test_a_run_stopped_midway_leaves_a_blocker_on_the_task(owner, ready_task, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_MODE", "hang")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    seen = wait_for_report(owner, run["id"])
    token = run_token(seen)
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


def test_an_older_claude_code_keeps_the_persons_settings_out_another_way(
    owner, ready_task, runtime, monkeypatch
):
    """Before Claude Code had --restricted, loading project settings only keeps the person's
    own settings (and so their hooks) out of a run: its empty folder has none. A Claude Code
    with neither is refused, with how to update it, instead of failing in a second."""
    monkeypatch.setenv("FAKE_CLI_FLAGS", "older")
    argv = json.loads(runtime.runners.ask(runtime.ws.owner(), "Draft the update"))["argv"]
    assert "--restricted" not in argv
    assert argv[argv.index("--setting-sources") + 1] == "project"
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    argv = wait_for_report(owner, run["id"])["argv"]
    assert "--restricted" not in argv and "--setting-sources" in argv
    assert finish(owner, run["id"])["status"] == "succeeded"
    monkeypatch.setenv("FAKE_CLI_FLAGS", "oldest")
    oldest = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=fake_resolve
    )
    with pytest.raises(Conflict, match="npm install -g @anthropic-ai/claude-code"):
        oldest.ask(runtime.ws.owner(), "Draft the update")


def test_a_login_that_no_longer_works_says_sign_in_again(owner, ready_task, runtime, monkeypatch):
    """Claude Code can say it is signed in while its saved login no longer works: the first
    answer that fails to authenticate shows it signed out, with how to sign in again, until a
    check finds it working."""
    monkeypatch.setenv("FAKE_CLI_AUTH", "expired")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]}), 201)
    done = finish(owner, run["id"])
    assert done["status"] == "failed"
    assert any("claude auth login" in str(e.get("text")) for e in done["events"]), done["events"]
    (claude, *_others) = owner.ok(owner.get("/api/runners"))
    assert claude["signed_in"] is False and "sign in again" in claude["detail"]
    refused = owner.post("/api/runners/claude/runs", json={"task_id": ready_task["id"]})
    assert refused.status_code == 409 and "claude auth login" in refused.text
    with pytest.raises(Conflict, match="claude auth login"):
        runtime.runners.ask(runtime.ws.owner(), "Draft the update")
    monkeypatch.delenv("FAKE_CLI_AUTH")
    (claude, *_others) = owner.ok(owner.get("/api/runners", params={"refresh": "true"}))
    assert claude["signed_in"] is True
    assert json.loads(runtime.runners.ask(runtime.ws.owner(), "Draft the update"))["prompt"]


def other_resolve(spec):
    """Codex and Gemini CLI stand in; Claude Code is not here."""
    return [sys.executable, FAKE_OTHER, spec.id] if spec.id in ("codex", "gemini") else None


def test_codex_and_gemini_answer_from_the_prompt_alone(runtime, monkeypatch):
    """The knowledge agent's other CLIs, asked for one answer: in an empty folder that goes,
    with none of the person's MCP servers, told to answer from the prompt alone, a model the
    person names passed on; only the answer comes back, without what the CLI prints beside."""
    runners = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=other_resolve
    )
    owner = runtime.ws.owner()
    codex = json.loads(runners.ask(owner, "Judge these.", runner="codex", model="gpt-5.1-codex"))
    argv = codex["argv"]
    assert argv[0] == "exec" and argv[-1] == "-"  # the prompt comes on stdin
    assert argv[argv.index("--sandbox") + 1] == "read-only" and "--skip-git-repo-check" in argv
    assert argv[argv.index("-c") + 1] == "mcp_servers={}"
    assert argv[argv.index("--model") + 1] == "gpt-5.1-codex"
    assert codex["prompt"].startswith(runners_module.ANSWER_ONLY)
    assert codex["prompt"].endswith("Judge these.")
    assert not os.path.exists(codex["cwd"])
    gemini = json.loads(runners.ask(owner, "Judge these.", runner="gemini"))
    argv = gemini["argv"]
    assert argv[argv.index("--allowed-mcp-server-names") + 1] == "none"
    assert argv[argv.index("--extensions") + 1] == "none"
    # Gemini CLI 0.1 reads stdin only when no -p is given: the whole prompt goes there.
    assert "-p" not in argv and "--model" not in argv
    assert gemini["prompt"].endswith("Judge these.") and not os.path.exists(gemini["cwd"])
    monkeypatch.setenv("FAKE_CLI_MODE", "fail")
    with pytest.raises(Conflict, match="quota exceeded"):
        runners.ask(owner, "Judge these.", runner="gemini")
    # A crash names its error line, not the last frame of its stack trace.
    monkeypatch.setenv("FAKE_CLI_MODE", "crash")
    with pytest.raises(Conflict, match="requires setting the GOOGLE_CLOUD_PROJECT"):
        runners.ask(owner, "Judge these.", runner="gemini")
    with pytest.raises(Conflict, match="not installed"):
        runners.ask(owner, "Judge these.", runner="claude")


def test_gemini_counts_as_signed_in_by_its_saved_login_or_a_key(tmp_path, monkeypatch):
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(tmp_path))
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    spec = runners_module.RUNNERS["gemini"]
    unknown = runners_module.detect(spec, other_resolve)
    assert (unknown.installed, unknown.version, unknown.signed_in) == (True, "0.9.9", None)
    monkeypatch.setenv("GEMINI_API_KEY", "a key")
    assert runners_module.detect(spec, other_resolve).signed_in is True
    monkeypatch.delenv("GEMINI_API_KEY")
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "oauth_creds.json").write_text("{}", encoding="utf-8")
    assert runners_module.detect(spec, other_resolve).signed_in is True


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
    credentials = owner.ok(owner.get(f"/api/actors/{model.actor_id}/credentials"))
    assert all(
        c["revoked_at"] for c in credentials if "Run from the workspace" in (c["label"] or "")
    )


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
    token = run_token(seen)
    texts = []
    for _ in range(5):
        reply = mcp(owner.client, token, "tools/call", {"name": "get_due_tasks", "arguments": {}})
        texts.append(reply.json()["result"]["content"][0]["text"])
    assert "Run contract: Draft launch notes" in texts[0]
    assert all("Run contract" not in text for text in texts[1:4])
    assert "Run contract: Draft launch notes" in texts[4]
    owner.ok(owner.post(f"/api/runners/runs/{run['id']}/cancel"))
    finish(owner, run["id"])


def test_ask_answers_from_the_brain_alone_and_returns_its_receipts(runtime, monkeypatch):
    """Release 1 plan, M10: Claude Code runs with the Brain's MCP server and nothing else,
    on a session named in advance, so every packet it asked for is the answer's receipt."""
    from brainkit import models_client
    from workspace_server.models import Models

    monkeypatch.setenv("FAKE_CLI_ASK", "1")
    runtime.runners = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=fake_resolve
    )
    runtime.models = Models(
        runtime.runners,
        fetch=lambda *a, **k: {},
        service=models_client.Status,
        settings=lambda: {},
    )
    with TestClient(create_app(runtime=runtime)) as client:
        reply = client.post(
            "/api/brain/agent/ask",
            json={"question": "How long do web design projects run?"},
            headers={"Authorization": f"Bearer {runtime.owner_token}"},
        )
    assert reply.status_code == 200, reply.text
    found = reply.json()
    assert found["asked_brain"] and len(found["receipts"]) == 1
    assert found["cited"] and found["cited"][0] in found["answer"], found["answer"]
    assert found["provider"]["vendor"] == "Anthropic"


def test_work_with_ai_makes_one_job_in_the_project_and_shows_it_on_the_timeline(
    owner, runtime, model
):
    """Release 1 plan, section 11: a prompt becomes one task in the project, run now with the
    app's tools only; the timeline shows its status, model and cost."""
    project = runtime.ws.projects.create(runtime.ws.owner(), title="Spring launch")
    started = owner.ok(
        owner.post(
            f"/api/work/projects/{project.id}/ask",
            json={"prompt": "Draft the launch email.", "skill": "launch-email"},
        ),
        201,
    )
    assert started["task"]["template"] == "work"
    assert "launch-email" in started["task"]["instructions"]
    run = finish(owner, started["run"]["id"])
    assert run["status"] == "succeeded", run
    (line,) = owner.ok(owner.get(f"/api/work/projects/{project.id}/timeline"))
    assert (line["task_id"], line["status"], line["runner"]) == (
        started["task"]["id"],
        "succeeded",
        "claude",
    )
    assert line["model"] and line["asked_by"]


def test_work_with_ai_takes_the_brains_project_id(owner, runtime, model):
    """The page knows a project by the Brain's id: its first job makes the workspace row."""
    brain_project = runtime.ws.rt.brain.projects()[0]
    assert owner.ok(owner.get(f"/api/work/projects/{brain_project.id}/timeline")) == []
    started = owner.ok(
        owner.post(f"/api/work/projects/{brain_project.id}/ask", json={"prompt": "Draft notes."}),
        201,
    )
    finish(owner, started["run"]["id"])
    (line,) = owner.ok(owner.get(f"/api/work/projects/{brain_project.id}/timeline"))
    assert line["task_id"] == started["task"]["id"]
