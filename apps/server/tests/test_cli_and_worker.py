"""The operator's side: the CLI, the worker, the stdio bridge, and exporting the earlier
workspace."""

import io
import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from workspace_server import cli
from workspace_server.mcp import bridge
from workspace_server.worker import Worker


@pytest.fixture
def env(tmp_path, monkeypatch, brain_vault, owner_token):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WORKSPACE_BRAIN_VAULT", brain_vault)
    monkeypatch.setenv("WORKSPACE_OWNER_TOKEN", owner_token)
    monkeypatch.setenv("WORKSPACE_NAME", "CLI workspace")
    monkeypatch.delenv("WORKSPACE_DATABASE_URL", raising=False)
    return tmp_path


def run(capsys, *argv):
    code = cli.main(["--env-file", "", *argv])
    return code, capsys.readouterr().out


def test_status_and_token(env, capsys, owner_token):
    code, out = run(capsys, "status")
    assert code == 0 and "CLI workspace" in out
    code, out = run(capsys, "token")
    assert f"/auth/login?token={owner_token}" in out
    code, out = run(capsys, "token", "--new")
    assert out.strip().startswith("wst_") and len(out.strip()) > 30


def test_serve_shows_the_sign_in_link_in_a_terminal_and_keeps_it_out_of_logs():
    """A person at a terminal sees the link; a server's log (Docker, a service) never holds
    the owner token, and says how to print the link instead."""
    shown = cli.sign_in_line("https://contxt.example", "wst_secret", terminal=True)
    assert shown == "Sign in: https://contxt.example/auth/login?token=wst_secret"
    logged = cli.sign_in_line("https://contxt.example", "wst_secret", terminal=False)
    assert "wst_secret" not in logged and "contxt token" in logged


def test_add_model_prints_the_token_once_with_its_setup(env, capsys):
    code, out = run(capsys, "add-model", "Codex", "codex")
    assert code == 0 and "Token (shown once): wst_" in out
    assert "[mcp_servers.contxt-app]" in out and "get_due_tasks" in out


def test_migrate_backup_and_restore(env, capsys, monkeypatch):
    run(capsys, "add-model", "Claude Code", "claude-code")
    code, out = run(capsys, "migrate")
    assert code == 0 and "Up to date" in out
    archive = env / "backup.zip"
    code, out = run(capsys, "backup", str(archive), "--with-brain")
    assert code == 0 and archive.exists()
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(env / "restored"))
    code, out = run(capsys, "restore", str(archive), "--brain-dir", str(env / "brain2"))
    assert code == 0 and json.loads(out)["objects"] == 0
    assert (env / "brain2" / "brain.json").exists()


def test_status_counts_ai_work_and_what_waits(env, capsys):
    code, out = run(capsys, "status")
    assert code == 0 and "AI work: none; waiting for your review: 0" in out


def test_the_earlier_workspace_exports_to_a_new_folder(env, capsys):
    out_dir = env / "earlier"
    code, out = run(capsys, "export-legacy", "--out", str(out_dir))
    assert code == 0 and f"to {out_dir}" in out
    assert (out_dir / "README.md").exists() and (out_dir / "todos.md").exists()
    code, out = run(capsys, "export-legacy")
    assert code == 0 and "workspace-export-" in out  # a dated folder under the exports


def test_worker_expires_leases_and_wakes_recurring_work(runtime, clock):
    ws, owner = runtime.ws, runtime.ws.owner()
    connection = ws.actors.connect_model(owner, name="Claude Code", provider="claude-code")
    model = ws.actors.authenticate(connection.token)
    project = ws.projects.create(owner, title="Ops")
    task = ws.tasks.create(
        owner,
        project_id=project.id,
        title="Daily check",
        instructions="Check.",
        assignee_id=model.actor_id,
        schedule={"kind": "daily", "time": "09:00"},
        review_policy="auto",
    )
    ws.tasks.mark_ready(owner, task.id)
    worker = Worker(ws, interval=1)
    clock.advance(timedelta(days=1))
    run_ = ws.bus.claim(model, task.id, lease_seconds=60).run
    clock.advance(timedelta(minutes=5))
    tick = worker.tick()
    assert tick.expired == 1 and ws.bus.run(model, run_.id).status == "expired"
    run_ = ws.bus.claim(model, task.id).run
    ws.bus.complete(model, run_.id, summary="ok")
    clock.advance(timedelta(days=1))
    assert worker.tick().woke == 1
    assert ws.tasks.get(owner, task.id).status == "ready"


def test_worker_thread_starts_and_stops(runtime):
    worker = Worker(runtime.ws, interval=1)
    worker.start()
    worker.stop()
    assert not worker._thread.is_alive()


class _Echo(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        auth = self.headers.get("Authorization")
        version = self.headers.get("MCP-Protocol-Version")
        if "id" not in body:
            self.send_response(202)
            self.end_headers()
            return
        result = (
            {"protocolVersion": "2025-06-18"}
            if body["method"] == "initialize"
            else {"auth": auth, "version": version}
        )
        payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def test_the_stdio_bridge_forwards_with_the_token_and_version():
    server = HTTPServer(("127.0.0.1", 0), _Echo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        stdin = io.StringIO(
            "\n".join(
                [
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                    "not json",
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                ]
            )
            + "\n"
        )
        stdout = io.StringIO()
        bridge.run(url, "wst_bridge", stdin=stdin, stdout=stdout)
        replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
        assert [r.get("id") for r in replies] == [1, None, 2]
        assert replies[1]["error"]["code"] == -32700
        assert replies[2]["result"] == {"auth": "Bearer wst_bridge", "version": "2025-06-18"}
    finally:
        server.shutdown()
        server.server_close()


def test_the_bridge_reports_an_unreachable_server():
    reply = bridge.forward(
        "http://127.0.0.1:9/mcp",
        "wst_x",
        {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        None,
        timeout=2,
    )
    assert reply["id"] == 7 and "not reachable" in reply["error"]["message"]
