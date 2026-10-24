"""The heartbeat: connectors found in the CLIs, read-only reads, the beat, regions and undo."""

import inspect
import json
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from workspace_core.db import schema
from workspace_core.ports import BrainProposal
from workspace_server.app import create_app
from workspace_server.heartbeat import connectors as conn
from workspace_server.heartbeat import service as hb_service
from workspace_server.runners import Runners, RunnerStatus

from .conftest import Api

FAKE_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_mcp_server.py")
FAKE_CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_cli.py")
USAGE = {
    "input_tokens": 100,
    "output_tokens": 20,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0,
}
PROJECT = "state-focus-website-redesign"
ITEM = {
    "id": "msg-1",
    "title": "Morgan approved hero option B",
    "text": "Morgan replied: hero option B is approved for the website.",
    "at": "2026-09-28T12:40:00Z",
    "url": "",
    "speaker": "Morgan",
    "private": False,
}


class FakeProc:
    def __init__(self, cli, argv, kwargs):
        self.cli, self.argv, self.kwargs = cli, list(argv), kwargs
        self.returncode = 0

    def communicate(self, prompt=None, timeout=None):
        argv = self.argv
        config = None
        if "--mcp-config" in argv:
            with open(argv[argv.index("--mcp-config") + 1], encoding="utf-8") as handle:
                config = json.load(handle)
        self.cli.calls.append({"argv": argv, "prompt": prompt, "config": config})
        if "exec" in argv:  # Codex
            last = argv[argv.index("--output-last-message") + 1]
            with open(last, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"cursor": "c1", "items": self.cli.items}))
            usage = {"type": "turn.completed", "usage": {"input_tokens": 50, "output_tokens": 5}}
            return json.dumps(usage) + "\n", ""
        if (config or {}).get("mcpServers"):  # a read through one connector
            if self.cli.read_error:
                return json.dumps({"is_error": True, "result": self.cli.read_error}), ""
            answer = {"cursor": "2026-09-28T12:40:00Z", "items": self.cli.items}
            return json.dumps({"result": json.dumps(answer), "usage": USAGE}), ""
        return json.dumps({"result": json.dumps(self.cli.judge(prompt)), "usage": USAGE}), ""


class FakeCli:
    """Claude Code and Codex as the heartbeat starts them: what each call was given, and the
    answers a read and the judge give."""

    def __init__(self):
        self.calls = []
        self.items = [dict(ITEM)]
        self.read_error = None
        self.writes = lambda item: [
            {
                "kind": "progress",
                "project": PROJECT,
                "text": item["text"],
                "reason": "Morgan approved it by email.",
            }
        ]

    def judge(self, prompt):
        shown = json.loads(prompt.split("\n\n", 1)[1])
        return {
            "items": [
                {
                    "item": i["item"],
                    "region": "state",
                    "project": PROJECT,
                    "line": i["title"],
                    "protected_by": None,
                    "writes": self.writes(i),
                }
                for i in shown["items"]
            ],
            "headlines": {"state": "The website hero is settled."},
            "projects": {PROJECT: "Hero option B approved"},
        }

    def __call__(self, argv, **kwargs):
        return FakeProc(self, argv, kwargs)

    def reads(self):
        return [c for c in self.calls if (c["config"] or {}).get("mcpServers") or "exec" in c["argv"]]

    def judges(self):
        return [c for c in self.calls if c not in self.reads()]


def signed_in(spec, refresh=False):
    return RunnerStatus(
        id=spec.id,
        label=spec.label,
        provider=spec.provider,
        one_click=True,
        installed=True,
        version="9.9.9",
        signed_in=True,
        install="",
        sign_in=f"{spec.executable} login",
    )


@pytest.fixture
def cli_home(tmp_path, monkeypatch):
    """The CLIs' own settings in a scratch folder: Claude Code with a mail server that would
    allow a send (and a token in its environment), Gnomon's own Brain server, a computer-use
    server in a project; Codex with a tracker; and a repository's .mcp.json, never read."""
    claude, codex = tmp_path / "claude", tmp_path / "codex"
    claude.mkdir()
    codex.mkdir()
    calls = tmp_path / "tool-calls.txt"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("CODEX_HOME", str(codex))
    monkeypatch.setenv("FAKE_MCP_CALLS", str(calls))
    server = {
        "type": "stdio",
        "command": sys.executable,
        "args": [FAKE_SERVER],
        "env": {"MAIL_TOKEN": "secret-mail-token-123"},
    }
    (claude / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {"mail": server, "contxt": {"command": "uv", "args": []}},
                "projects": {
                    str(tmp_path / "repo"): {
                        "mcpServers": {"computer-use": {"command": "computer-use-mcp"}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    forward = sys.executable.replace("\\", "/")
    (codex / "config.toml").write_text(
        f'[mcp_servers.tracker]\ncommand = "{forward}"\n'
        f'args = ["{FAKE_SERVER.replace(chr(92), "/")}"]\n',
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"repo-only": {"command": "x"}}}), encoding="utf-8"
    )
    monkeypatch.chdir(repo)
    return {"calls": calls}


@pytest.fixture
def fake_cli():
    return FakeCli()


@pytest.fixture
def client(runtime, cli_home, fake_cli):
    runtime.runners = Runners(
        runtime.ws,
        runtime.templates,
        base_url="http://127.0.0.1:8787",
        resolve=lambda spec: [sys.executable, FAKE_CLI],
        popen=fake_cli,
    )
    runtime.runners.status = signed_in
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


@pytest.fixture
def hb(runtime, client):
    return runtime.heartbeat


def found(owner, *, codex=False):
    """Find connectors in the CLIs; the Codex tracker stays off unless a test reads it."""
    result = owner.ok(owner.post("/api/heartbeat/connectors/rescan"))
    if not codex:
        owner.ok(owner.put("/api/heartbeat/connectors/codex:tracker", json={"enabled": False}))
    return result


def beat(owner):
    return owner.ok(owner.post("/api/heartbeat/beat?wait=true"))


def rows(runtime, table):
    with runtime.ws.rt.read() as tx:
        return tx.rows(table.select())


# ---------------------------------------------------------------------- discovery


def test_connectors_are_found_in_each_cli_and_no_secret_is_kept(owner, runtime, cli_home):
    result = found(owner, codex=True)
    by_id = {c["id"]: c for c in result["connectors"]}
    assert set(by_id) == {"claude:mail", "claude:computer-use", "codex:tracker", "scout"}
    mail = by_id["claude:mail"]
    assert mail["status"] == "ok" and mail["enabled"]
    assert mail["tools"] == ["list_messages", "get_thread"]
    assert by_id["claude:computer-use"]["how"] == "computer"
    assert not by_id["claude:computer-use"]["enabled"]
    assert "computer use" in by_id["claude:computer-use"]["status_line"]
    assert by_id["scout"]["status"] == "off"
    assert "Found 3 connectors" not in result["line"]
    stored = json.dumps(rows(runtime, schema.heartbeat_connectors), default=str)
    assert "secret-mail-token-123" not in stored
    assert "secret-mail-token-123" not in json.dumps(result)
    assert not cli_home["calls"].exists()  # listing its tools never called one


def test_only_tools_that_read_are_kept():
    assert conn.read_only({"name": "list_messages"})
    assert conn.read_only({"name": "searchIssues"})
    assert conn.read_only({"name": "slack_list_channels"}, "slack")
    assert conn.read_only({"name": "anything", "annotations": {"readOnlyHint": True}})
    assert not conn.read_only({"name": "send_message"})
    assert not conn.read_only({"name": "get_and_delete"})
    assert not conn.read_only({"name": "delete_all", "annotations": {"readOnlyHint": True}})
    assert not conn.read_only({"name": "list_items", "annotations": {"readOnlyHint": False}})
    assert not conn.read_only({"name": "draft_reply"})


def test_a_server_whose_tools_cannot_be_listed_is_not_read(owner, hb, cli_home):
    def broken(found):
        raise conn.ListingFailed("it did not answer in time")

    hb.list_tools = broken
    by_id = {c["id"]: c for c in found(owner)["connectors"]}
    assert by_id["claude:mail"]["status"] == "cannot_confirm_read_only"
    assert not by_id["claude:mail"]["enabled"]
    refused = owner.put("/api/heartbeat/connectors/claude:mail", json={"enabled": True})
    assert refused.status_code == 409


# ---------------------------------------------------------------------- read-only


def test_a_beat_only_reads_with_a_connector_that_would_allow_a_send(
    owner, hb, fake_cli, cli_home
):
    found(owner)
    done = beat(owner)
    assert done["status"] == "done", done
    (read,) = fake_cli.reads()
    argv = read["argv"]
    allowed = argv[argv.index("--allowedTools") + 1 : argv.index("--disallowedTools")]
    assert allowed == ["mcp__mail__list_messages", "mcp__mail__get_thread"]
    refused = argv[argv.index("--disallowedTools") + 1 : argv.index("--permission-mode")]
    assert "mcp__mail__send_message" in refused and "mcp__mail__delete_all" in refused
    assert not any("send_message" in a for a in allowed)
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--strict-mcp-config" in argv
    assert list(read["config"]["mcpServers"]) == ["mail"]
    (judge,) = fake_cli.judges()
    assert judge["config"] == {"mcpServers": {}}  # the judge has no connector at all
    assert not cli_home["calls"].exists()
    # No code path of the heartbeat can call a tool itself.
    for module in (conn, hb_service):
        assert "tools/call" not in inspect.getsource(module)


def test_codex_reads_with_only_the_read_only_tools(owner, hb, fake_cli):
    found(owner, codex=True)
    owner.ok(owner.put("/api/heartbeat/connectors/claude:mail", json={"enabled": False}))
    beat(owner)
    (read,) = fake_cli.reads()
    argv = read["argv"]
    limit = argv[argv.index("-c") + 1]
    assert limit == 'mcp_servers.tracker.enabled_tools=["list_messages", "get_thread"]'
    assert "send_message" not in " ".join(argv)
    assert argv[argv.index("--sandbox") + 1] == "read-only"


# ---------------------------------------------------------------------- the beat


def test_a_beat_writes_through_governance_with_the_item_as_source(owner, runtime, fake_cli):
    found(owner)
    done = beat(owner)
    assert done["items"] == 1
    assert done["changes"] + done["waits"] == 1
    assert done["tokens"] == 240 and done["tokens_known"]  # the read and the judge, as said
    (line,) = rows(runtime, schema.heartbeat_lines)
    assert line["item_id"] == "connector:claude:mail:msg-1"
    assert line["status"] in ("applied", "waiting")
    assert line["proposal_id"]
    waiting = [p for p in runtime.ws.brain.proposals(runtime.ws.owner())]
    cited = [p for p in waiting if "connector:claude:mail:msg-1" in json.dumps(p, default=str)]
    assert cited, waiting
    regions = {r["id"]: r for r in owner.ok(owner.get("/api/heartbeat/regions"))}
    state = regions["state"]
    assert state["headline"] == "The website hero is settled."
    assert state["new_this_beat"] == 1
    (shown,) = state["lines"]
    assert shown["connector"] == "mail" and shown["cli_label"] == "Claude Code"
    assert shown["wrote"].endswith("Website Redesign › latest progress")
    assert state["projects"][0]["status"] == "Hero option B approved"
    assert state["projects"][0]["from"] == ["mail"]


def test_the_same_items_twice_make_no_new_writes(owner, runtime, fake_cli):
    found(owner)
    beat(owner)
    proposals = len(runtime.ws.brain.proposals(runtime.ws.owner()))
    lines = len(rows(runtime, schema.heartbeat_lines))
    (mail,) = [r for r in rows(runtime, schema.heartbeat_connectors) if r["id"] == "claude:mail"]
    assert mail["cursor"] == "2026-09-28T12:40:00Z"
    again = beat(owner)
    assert again["items"] == 0 and again["changes"] == 0 and again["waits"] == 0
    assert again["nothing_new"]
    assert len(fake_cli.judges()) == 1  # nothing new: no model call
    assert len(rows(runtime, schema.heartbeat_lines)) == lines
    assert len(runtime.ws.brain.proposals(runtime.ws.owner())) == proposals
    assert len(rows(runtime, schema.heartbeat_beats)) == 2  # only its record


def test_a_beat_with_nothing_new_writes_only_its_record(owner, runtime, fake_cli):
    found(owner)
    fake_cli.items = []
    done = beat(owner)
    assert done["nothing_new"] and done["details"] == ["Read 1 connectors. Nothing new."]
    assert rows(runtime, schema.heartbeat_lines) == []
    assert rows(runtime, schema.heartbeat_regions) == []
    assert fake_cli.judges() == []


def test_one_beat_at_a_time_and_a_stale_lock_expires(owner, runtime, clock):
    found(owner)
    with runtime.ws.rt.write() as tx:
        tx.insert(
            schema.heartbeat_locks,
            {
                "id": tx.workspace_id,
                "beat_id": "beat_other",
                "expires_at": (clock.now() + timedelta(minutes=5)).isoformat(),
            },
        )
    assert beat(owner)["skipped"] == "busy"
    assert rows(runtime, schema.heartbeat_beats) == []
    clock.advance(timedelta(minutes=10))  # the other beat stopped: its lock ran out
    assert beat(owner)["status"] == "done"
    assert rows(runtime, schema.heartbeat_locks) == []  # released


def test_pause_and_quiet_hours_skip(owner, runtime, hb, clock):
    found(owner)
    owner.ok(owner.put("/api/heartbeat/settings", json={"paused": True}))
    assert beat(owner)["skipped"] == "paused"
    status = owner.ok(owner.get("/api/heartbeat/status"))
    assert status["state"] == "paused" and status["next_beat_at"] is None
    owner.ok(owner.put("/api/heartbeat/settings", json={"paused": False, "quiet_hours": "night"}))
    clock.set(datetime(2026, 9, 29, 3, 0, tzinfo=UTC))  # 11pm in New York
    status = owner.ok(owner.get("/api/heartbeat/status"))
    assert status["state"] == "quiet" and status["in_quiet_hours"]
    assert status["next_beat_at"].startswith("2026-09-29T11:00")  # 7am there
    assert hb.start(runtime.ws.owner(), "schedule")["skipped"] == "quiet"
    assert hb_service.HeartbeatWorker(hb).run_once() is None
    assert rows(runtime, schema.heartbeat_beats) == []
    assert beat(owner)["status"] == "done"  # Beat now still beats


def test_a_scheduled_beat_runs_when_due(owner, runtime, hb, clock):
    found(owner)
    worker = hb_service.HeartbeatWorker(hb)
    assert worker.run_once()["status"] == "done"
    assert worker.run_once() is None  # not due again yet
    clock.advance(timedelta(minutes=15))
    assert worker.run_once()["trigger"] == "schedule"


# ---------------------------------------------------------------------- undo


def test_an_undone_line_is_not_written_again(owner, runtime, fake_cli):
    found(owner)
    beat(owner)
    (line,) = rows(runtime, schema.heartbeat_lines)
    undone = owner.ok(owner.post(f"/api/heartbeat/lines/{line['id']}/undo"))
    assert undone["status"] == "undone"
    assert "won't write that again" in undone["line"]
    left = [p for p in runtime.ws.brain.proposals(runtime.ws.owner()) if p.get("id") == line["proposal_id"]]
    assert left == []  # the waiting change was turned down
    # The item changes a little; the judge would make the same write again.
    fake_cli.items = [dict(ITEM, title="Morgan approved hero option B (edited)")]
    fake_cli.writes = lambda item: [
        {"kind": "progress", "project": PROJECT, "text": ITEM["text"], "reason": "again"}
    ]
    again = beat(owner)
    assert again["items"] == 1 and again["changes"] == 0 and again["waits"] == 0
    assert any("you undid it" in d for d in again["details"])
    assert [r["status"] for r in rows(runtime, schema.heartbeat_lines)] == ["undone"]
    assert owner.post(f"/api/heartbeat/lines/{line['id']}/undo").status_code == 409


def test_undoing_a_line_that_went_in_takes_its_undo_point_back(owner, runtime, hb, monkeypatch):
    found(owner)
    monkeypatch.setattr(
        hb,
        "_propose",
        lambda *a: BrainProposal(
            status="applied", message="in", proposal_id="p-1", checkpoint_id="cp-1"
        ),
    )
    taken = []
    monkeypatch.setattr(
        runtime.ws.brain, "undo", lambda who, cp, together=False: taken.append(cp) or {}
    )
    done = beat(owner)
    assert done["changes"] == 1 and done["waits"] == 0
    (line,) = rows(runtime, schema.heartbeat_lines)
    assert line["status"] == "applied" and line["checkpoint_id"] == "cp-1"
    owner.ok(owner.post(f"/api/heartbeat/lines/{line['id']}/undo"))
    assert taken == ["cp-1"]


# ---------------------------------------------------------------------- what is held back


def test_an_item_a_must_hold_protects_is_held_back(owner, runtime, hb, fake_cli, monkeypatch):
    found(owner)
    monkeypatch.setattr(
        hb,
        "protecting",
        lambda text: {"id": "rules-pricing", "line": "Never share pricing until it is final."}
        if "pricing" in text.lower()
        else None,
    )
    fake_cli.items = [dict(ITEM, id="sheet-4", title="Pricing sheet v4", text="Draft pricing v4")]
    done = beat(owner)
    assert done["held"] == 1 and done["changes"] == 0 and done["waits"] == 0
    (line,) = rows(runtime, schema.heartbeat_lines)
    assert line["status"] == "held"
    assert line["wrote"] == "Held back: must-hold: Never share pricing until it is final."
    assert line["proposal_id"] is None


def test_a_private_item_is_held_back(owner, runtime, fake_cli):
    found(owner)
    fake_cli.items = [dict(ITEM, private=True)]
    done = beat(owner)
    assert done["held"] == 1
    assert rows(runtime, schema.heartbeat_lines)[0]["wrote"] == "Held back: a private item"


def test_a_write_out_of_scope_is_refused(owner, runtime, fake_cli):
    found(owner)
    fake_cli.writes = lambda item: [{"kind": "send", "text": "Reply to Morgan"}]
    done = beat(owner)
    assert done["changes"] == done["waits"] == 0
    assert rows(runtime, schema.heartbeat_lines)[0]["status"] == "refused"


# ---------------------------------------------------------------------- backing off


def test_a_cli_signed_out_skips_the_beat_and_says_so(owner, runtime, hb):
    found(owner)

    def signed_out(spec, refresh=False):
        return RunnerStatus(**{**signed_in(spec).__dict__, "signed_in": False})

    runtime.runners.status = signed_out
    assert beat(owner)["skipped"] == "unhealthy_sign_in"
    assert owner.ok(owner.get("/api/heartbeat/status"))["state"] == "unhealthy_sign_in"


def test_a_provider_limit_backs_off_and_says_so(owner, runtime, hb, fake_cli):
    found(owner)
    fake_cli.read_error = "API Error: 429 rate limit reached for this organization"
    done = beat(owner)
    assert done["status"] == "done"
    assert any("429" in e for e in done["errors"])
    status = owner.ok(owner.get("/api/heartbeat/status"))
    assert status["state"] == "provider_limit"
    mail = next(c for c in status["connectors"] if c["id"] == "claude:mail")
    assert mail["status"] == "provider_limit"
    assert hb.start(runtime.ws.owner(), "schedule")["skipped"] == "provider_limit"


# ---------------------------------------------------------------------- settings and MCP


def test_settings_are_checked(owner):
    owner.ok(owner.put("/api/heartbeat/settings", json={"cadence": 30, "quiet_hours": "off"}))
    status = owner.ok(owner.get("/api/heartbeat/status"))
    assert status["cadence"] == 30 and status["quiet_hours"] == "off"
    assert owner.put("/api/heartbeat/settings", json={"cadence": 7}).status_code == 422
    assert owner.put("/api/heartbeat/settings", json={"quiet_hours": "lunch"}).status_code == 422


def test_the_app_mcp_tools_and_their_confirmation(model, owner):
    found(owner)
    names = {t["name"] for t in model.mcp("tools/list")["result"]["tools"]}
    assert {
        "heartbeat_status",
        "heartbeat_beat",
        "heartbeat_beats",
        "heartbeat_regions",
        "heartbeat_undo",
        "heartbeat_configure",
    } <= names
    status = model.tool("heartbeat_status")
    assert "every 15 min" in status["content"][0]["text"]
    asked = model.tool("heartbeat_configure", cadence=60)
    assert asked["isError"] and "needs_user_confirmation" in asked["content"][0]["text"]
    done = model.tool("heartbeat_configure", cadence=60, confirmed_by_user={"quote": "yes, hourly"})
    assert not done.get("isError")
    assert owner.ok(owner.get("/api/heartbeat/status"))["cadence"] == 60
    ran = model.tool("heartbeat_beat")
    assert "Beat beat_" in ran["content"][0]["text"]
    assert model.tool("heartbeat_regions")["structuredContent"]["regions"]


def test_a_model_cannot_change_settings_over_http(model):
    assert model.put("/api/heartbeat/settings", json={"paused": True}).status_code == 403


def test_beats_list_since(owner, clock):
    found(owner)
    beat(owner)
    clock.advance(timedelta(minutes=20))
    later = clock.now().isoformat()
    beat(owner)
    assert len(owner.ok(owner.get("/api/heartbeat/beats"))) == 2
    assert Api  # the conftest client is the one these tests speak through
    assert len(owner.ok(owner.get("/api/heartbeat/beats", params={"since": later}))) <= 1


def test_a_real_must_hold_protects_what_its_words_name(owner, runtime, hb):
    ws = runtime.ws
    made = ws.brain.propose(
        ws.owner(),
        title="Pricing stays private",
        statement="Never share pricing until it is final.",
        kind="rule",
        evidence="The owner said so.",
        topic="rules/delivery",
        must_hold={
            "applies_to": "facts",
            "triggers": "pricing, price sheet",
            "must_text": "Never share pricing until it is final.",
        },
    )
    assert made.proposal_id, made
    ws.brain.decide(ws.owner(), made.proposal_id, approve=True)
    held = hb.protecting("Pricing sheet v4 is edited, still on the Draft tab: new pricing.")
    assert held and "pricing" in str(held.get("line")).lower()
    assert hb.protecting("Morgan approved hero option B.") is None
