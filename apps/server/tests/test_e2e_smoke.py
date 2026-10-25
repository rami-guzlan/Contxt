"""End to end on a demo Brain, the way the AI apps use it: two Brain processes over stdio that
share one session ledger, the app's AI work over its HTTP MCP endpoint on the same Brain, an
approval in the app that the running Brain process sees without a restart, and, after every
write, a clean git tree (each governed change committed).

The logic comes from the October 2026 MCP test run's harness; the content is the invented
knowledge-company demo."""

import contextlib
import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading

import pytest

from workspace_server import homes

TIMEOUT = 120


class Stdio:
    """An AI app's view of the Brain: its MCP server as a process, newline-delimited JSON-RPC."""

    def __init__(self, vault: str) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("CONTXT_", "WORKSPACE_", "BRAIN_"))
        }
        env["PYTHONIOENCODING"] = "utf-8"
        env["BRAIN_LOCAL_MODELS"] = "1"  # never fetch a model in a test; match by words
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "brainkit", "--vault", vault, "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 0

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.lines.get(timeout=TIMEOUT)
            assert line is not None, "the Brain's MCP server exited"
            reply = json.loads(line)
            if reply.get("id") == self.next_id:
                return reply

    def init(self):
        reply = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "claude-code", "version": "2"},
            },
        )
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.proc.stdin.write("\n")
        self.proc.stdin.flush()
        return reply["result"]

    def call(self, tool, **arguments):
        result = self.request("tools/call", {"name": tool, "arguments": arguments})["result"]
        return result["content"][0]["text"], bool(result.get("isError"))

    def close(self) -> None:
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.close()
            self.proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            self.proc.kill()
            self.proc.wait(timeout=15)
        if self.proc.stdout is not None:
            self.proc.stdout.close()


def session_of(text: str) -> str:
    return text.split("session_id: ")[1].split(" ")[0]


def last_packet(vault: str, session: str) -> dict:
    ledger = os.path.join(vault, ".brain", "sessions.sqlite")
    with contextlib.closing(sqlite3.connect(ledger, timeout=15)) as conn:
        (data,) = conn.execute(
            "SELECT data FROM packets WHERE session_id = ? ORDER BY at DESC, rowid DESC LIMIT 1",
            (session,),
        ).fetchone()
    return json.loads(data)


def git_clean(repo: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True, check=True
    ).stdout.strip()


def commits(repo: str) -> int:
    out = subprocess.run(
        ["git", "-C", repo, "rev-list", "--count", "HEAD"], capture_output=True, text=True
    )
    return int(out.stdout.strip() or 0)


@pytest.fixture
def home(tmp_path):
    return homes.create_home(
        str(tmp_path / "home"), homes.find_starter("knowledge-company"), port=8799
    )


@pytest.fixture
def brain_vault(home):
    """The app runs on the demo home's Brain (overrides the sample vault in conftest)."""
    return home["vault"]


@pytest.fixture
def apps(home):
    opened = [Stdio(home["vault"]), Stdio(home["vault"])]
    yield opened
    for app in opened:
        app.close()


def test_two_brain_processes_share_one_conversation(home, apps):
    first, second = apps
    vault = home["vault"]
    info = first.init()
    assert info["serverInfo"]["name"] == "brain" and "gnomon_get_context" in info["instructions"]
    second.init()
    names = {t["name"] for t in first.request("tools/list")["result"]["tools"]}
    assert {"gnomon_get_context", "notes_propose", "projects_create", "outputs_save"} <= names

    opened, error = first.call(
        "gnomon_get_context", request="Write a LinkedIn post announcing the Q4 webinar series"
    )
    assert not error and "# Startup context (kernel " in opened
    session = session_of(opened)
    kernel = opened.split("# Startup context (kernel ")[1][:12]

    # The same conversation, continued from another process: nothing again, no kernel.
    edit, _ = second.call(
        "gnomon_get_context", request="Make the opening line punchier", session_id=session
    )
    assert f"session_id: {session} (continuing)" in edit
    assert "# Startup context" not in edit and f"kernel: {kernel} (current)" in edit
    assert last_packet(vault, session)["followup"] == "edit"
    side, _ = second.call(
        "gnomon_get_context", request="Who approves posts before they go out?", session_id=session
    )
    summary, _ = first.call(
        "gnomon_get_context", request="Make the executive summary warmer", session_id=session
    )
    assert last_packet(vault, session)["followup"] == "edit"  # the draft, not the side question
    again, _ = second.call(
        "gnomon_get_context",
        request="Write a LinkedIn post announcing the Q4 webinar series",
        session_id=session,
        fresh=True,
    )
    assert "# Startup context (kernel " in again  # after a compaction, everything again

    # A new conversation that already holds the kernel skips it (the person's own layer,
    # never in a shared file, comes once); a stale fingerprint gets it.
    held, _ = first.call(
        "gnomon_get_context", request="Draft a newsletter intro", startup_fingerprint=kernel
    )
    assert "# Startup context (kernel " not in held
    stale, _ = first.call(
        "gnomon_get_context", request="Draft a newsletter intro", startup_fingerprint="0" * 12
    )
    assert "# Startup context" in stale

    # A new Brain is auto-governed: the owner's own scope and a shared rule from their AI both
    # go in at once as commits (undo points); a must-hold would still wait.
    before = commits(home["brain"])
    own, error = first.call(
        "notes_propose",
        text="Jordan wants webinar recaps sent within two days of each session.",
        title="Webinar recap timing",
        area="people",
        topic="jordan-avery",
        kind="fact",
        scope="person:jordan",
        evidence="said in this conversation",
    )
    assert not error and "appl" in own.lower(), own
    assert commits(home["brain"]) > before
    shared, error = first.call(
        "notes_propose",
        text="Every LinkedIn post about a webinar must name the guest plant manager.",
        title="Name the guest",
        area="marketing",
        topic="linkedin",
        kind="rule",
        scope="company",
        evidence="said in this conversation",
    )
    assert not error and "appl" in shared.lower(), shared
    made, error = first.call(
        "projects_create",
        name="Spring open house",
        summary="An open house for plant managers in March.",
        aliases=["the open house"],
    )
    assert not error, made
    # ...and the other process sees the new project at once, by its alias.
    found, _ = second.call("gnomon_get_context", request="Where does the open house stand?")
    assert "Spring open house" in found
    assert git_clean(home["brain"]) == ""


def test_an_approval_in_the_app_reaches_a_running_brain_process(home, apps, owner, model):
    # Governed, so the AI's proposal waits for the owner's yes (in Auto it would go in at once).
    owner.ok(owner.put("/api/brain/policies", json={"mode": "governed"}))
    brain = apps[0]
    brain.init()
    note = owner.ok(
        owner.post(
            "/api/notes",
            json={"title": "Call notes", "body": "Plant managers prefer webinars at 11 AM."},
        ),
        201,
    )
    task = owner.ok(
        owner.post(f"/api/notes/{note['id']}/remember", json={"assignee_id": model.actor_id}),
        201,
    )
    claim = model.tool("claim_task", task_id=task["id"], idempotency_key=f"{task['id']}:once")
    retry = model.tool("claim_task", task_id=task["id"], idempotency_key=f"{task['id']}:once")
    run_id = claim["structuredContent"]["run"]["id"]
    assert retry["structuredContent"]["run"]["id"] == run_id  # the same claim, not a second
    made = model.tool(
        "propose_brain_entry",
        run_id=run_id,
        title="Webinar time",
        statement="Plant managers prefer webinars that start at 11 AM Eastern.",
        evidence="Call notes say so.",
        sources=[f"context_item:{note['id']}"],
    )
    assert not made["isError"], made
    proposal_id = made["structuredContent"]["proposal"]["proposal_id"]
    done = model.tool("complete_task", run_id=run_id, summary="One durable statement")
    assert not done["isError"]
    late = model.tool("append_task_event", run_id=run_id, type="progress", message="late")
    assert late["isError"]  # fenced: the run is over

    owner.ok(owner.post(f"/api/brain/proposals/{proposal_id}/decide", json={"approve": True}))
    text, error = brain.call("notes_search", query="what time do plant managers want webinars")
    assert not error and "11 AM" in text, text  # no restart needed
    assert git_clean(home["brain"]) == ""
