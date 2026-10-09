"""Proof that context matters, end to end: a comparison with and without the Brain, the
examples a demo keeps, follow-up questions in the goals interview, the AI apps on this
computer and connecting one, what each AI asked, and the browser opening signed in."""

import json
import os
import time

import pytest

from workspace_core.errors import Conflict
from workspace_server import apps, cli
from workspace_server.difference import parse_differences


def wait_for(owner, path, done=("done", "failed"), seconds=10.0):
    end = time.monotonic() + seconds
    while True:
        found = owner.ok(owner.get(path))
        if found["status"] in done or time.monotonic() > end:
            return found
        time.sleep(0.05)


def test_a_comparison_answers_twice_and_names_what_changed(owner, model, runtime, monkeypatch):
    asked = []

    def ask(who, prompt, timeout=180.0):
        asked.append(prompt)
        if len(asked) == 1:
            return "Exciting news! Join our webinar!"
        if len(asked) == 2:
            return "57% of new supervisors got under 8 hours of training."
        return json.dumps(
            {
                "differences": [
                    {"what": "Opens with a sourced number", "item": "rules-style-001"},
                    {"what": "Invented", "item": "no-such-note"},
                ]
            }
        )

    monkeypatch.setattr(runtime.runners, "ask", ask)
    started = owner.ok(
        owner.post("/api/brain/difference", json={"request": "Write a headline for the site"}),
        202,
    )
    assert started["status"] in ("running", "done") and started["tokens"] > 0
    assert started["brain_tokens"] >= started["tokens"] and started["share"] is not None
    found = wait_for(owner, f"/api/brain/difference/{started['id']}")
    assert found["status"] == "done", found
    assert found["without"].startswith("Exciting") and found["with_context"].startswith("57%")
    assert asked[0] == "Write a headline for the site"  # the same request, nothing else
    assert asked[1].endswith("Write a headline for the site") and "---" in asked[1]
    by_item = {d["what"]: d["item"] for d in found["differences"]}
    pieces = {p["id"] for p in found["pieces"]}
    assert by_item["Invented"] == ""  # kept to the pieces the request got
    assert by_item["Opens with a sourced number"] in pieces | {""}
    assert model.post("/api/brain/difference", json={"request": "x"}).status_code == 403


def test_the_answer_with_the_brain_gets_the_procedure_and_no_tool_to_call(
    owner, runtime, monkeypatch
):
    # Both sides run with no tools: a context that tells the model to call get_skill or the
    # CLI gets those calls written out instead of a draft. The procedure the packet points
    # to comes in full instead.
    asked = []

    def ask(who, prompt, timeout=180.0):
        asked.append(prompt)
        return '{"differences": []}' if len(asked) == 3 else "A draft."

    monkeypatch.setattr(runtime.runners, "ask", ask)
    request = "Create a brand sheet for the new client"
    started = owner.ok(owner.post("/api/brain/difference", json={"request": request}), 202)
    found = wait_for(owner, f"/api/brain/difference/{started['id']}")
    assert found["status"] == "done", found
    without, with_brain, compare = asked
    assert without == request
    assert with_brain.endswith(request)
    assert "Nothing goes to a client before Alex approves it." in with_brain  # startup context
    assert "Write the voice lines in plain language." in with_brain  # the skill's own steps
    for call in (
        "get_task_context",
        "get_skill",
        "get_note",
        "get_reference",
        "search_notes",
        "propose_note",
        "record_output",
        "fallback",
    ):
        assert call not in with_brain, call
    skill = next(p for p in found["pieces"] if p["kind"] == "skill")
    assert (skill["id"], skill["title"]) == ("brand-sheet", "/brand-sheet")
    assert "- brand-sheet: /brand-sheet" in compare  # the comparison knows it was handed over


def test_a_comparison_that_cannot_run_says_why(owner, runtime, monkeypatch):
    def ask(who, prompt, timeout=180.0):
        raise Conflict("Claude Code is not installed on this computer: npm install")

    monkeypatch.setattr(runtime.runners, "ask", ask)
    started = owner.ok(owner.post("/api/brain/difference", json={"request": "Hello"}), 202)
    found = wait_for(owner, f"/api/brain/difference/{started['id']}")
    assert found["status"] == "failed" and "not installed" in found["error"]
    assert owner.get("/api/brain/difference/cmp_none").status_code == 404


def test_differences_are_read_from_whatever_the_model_wrapped_them_in():
    text = 'Here you go:\n```json\n{"differences": [{"what": "A", "item": "n1"}]}\n```'
    assert parse_differences(text, {"n1"}) == [{"what": "A", "item": "n1"}]
    assert parse_differences("no json at all", {"n1"}) == []


def test_a_demo_keeps_its_examples_beside_its_vault(owner, runtime):
    folder = os.path.join(os.path.dirname(runtime.settings.brain_vault), "examples")
    os.makedirs(folder, exist_ok=True)
    pair = {"request": "Plan dinners", "without": "Satay", "with_context": "No peanuts"}
    with open(os.path.join(folder, "difference-dinners.json"), "w", encoding="utf-8") as handle:
        json.dump(pair, handle)
    with open(os.path.join(folder, "notes.txt"), "w", encoding="utf-8") as handle:
        handle.write("not an example")
    (example,) = owner.ok(owner.get("/api/brain/examples"))
    assert example["id"] == "difference-dinners" and example["with_context"] == "No peanuts"


def test_a_follow_up_question_only_when_an_answer_is_vague(owner, runtime, monkeypatch):
    replies = iter(["Where do follow-ups usually start: meetings, email or calls?", "NONE"])
    monkeypatch.setattr(runtime.runners, "ask", lambda who, prompt, timeout=90: next(replies))
    body = {"question": "Where do things slip today?", "answer": "Follow-ups."}
    first = owner.ok(owner.post("/api/brain/goals/followup", json=body))
    assert first["followup"].startswith("Where do follow-ups")
    second = owner.ok(owner.post("/api/brain/goals/followup", json=body))
    assert second["followup"] is None


@pytest.fixture
def places(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    found = apps.Places(
        home=str(home), appdata=str(tmp_path / "appdata"), platform="win32", which=lambda c: None
    )
    monkeypatch.setattr(apps.Places, "here", classmethod(lambda cls: found))
    return found


def test_the_apps_on_this_computer_and_connecting_one(owner, model, places):
    listed = {a["client"]: a for a in owner.ok(owner.get("/api/brain/apps"))}
    assert listed["cursor"]["found"] and not listed["cursor"]["connected"]
    assert not listed["claude-code"]["found"] and not listed["claude-desktop"]["found"]
    assert listed["cursor"]["setup"]["server"] == "contxt"
    with open(places.cursor_file(), "w", encoding="utf-8") as handle:
        json.dump({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}, handle)
    refused = owner.post("/api/brain/apps/cursor/connect", json={})
    assert refused.status_code == 422
    assert model.post("/api/brain/apps/cursor/connect", json={"confirm": True}).status_code == 403
    done = owner.ok(owner.post("/api/brain/apps/cursor/connect", json={"confirm": True}))
    assert done["changed"] and done["backup"] and os.path.isfile(done["backup"])
    with open(places.cursor_file(), encoding="utf-8") as handle:
        written = json.load(handle)
    assert set(written["mcpServers"]) == {"other", "contxt"} and written["theme"] == "dark"
    again = owner.ok(owner.post("/api/brain/apps/cursor/connect", json={"confirm": True}))
    assert not again["changed"]
    listed = {a["client"]: a for a in owner.ok(owner.get("/api/brain/apps"))}
    assert listed["cursor"]["connected"]


def test_a_settings_file_that_is_not_json_is_left_alone(owner, places):
    with open(places.cursor_file(), "w", encoding="utf-8") as handle:
        handle.write("{ not json")
    refused = owner.post("/api/brain/apps/cursor/connect", json={"confirm": True})
    assert refused.status_code == 409
    with open(places.cursor_file(), encoding="utf-8") as handle:
        assert handle.read() == "{ not json"


def test_codex_gets_its_block_once(tmp_path):
    places = apps.Places(home=str(tmp_path), appdata=None, platform="linux", which=lambda c: None)
    os.makedirs(os.path.dirname(places.codex_file()))
    with open(places.codex_file(), "w", encoding="utf-8") as handle:
        handle.write('model = "o4"')
    from datetime import UTC, datetime

    now = datetime(2026, 10, 7, tzinfo=UTC)
    done = apps.connect("codex", vault="/v", python="/py", places=places, moment=now)
    assert done["changed"] and done["backup"]
    again = apps.connect("codex", vault="/v", python="/py", places=places, moment=now)
    assert not again["changed"]
    with open(places.codex_file(), encoding="utf-8") as handle:
        text = handle.read()
    assert text.startswith('model = "o4"') and text.count("[mcp_servers.contxt]") == 1


def test_claude_code_is_connected_with_its_own_command(tmp_path):
    calls = []

    class Done:
        def __init__(self, code):
            self.returncode, self.stdout, self.stderr = code, "", ""

    def run(argv, timeout=30):
        calls.append(argv[1:3])
        return Done(1 if argv[1:3] == ["mcp", "get"] else 0)

    places = apps.Places(home=str(tmp_path), appdata=None, platform="linux", which=lambda c: "/c")
    from datetime import UTC, datetime

    done = apps.connect(
        "claude-code", vault="/v", python="/py", places=places, moment=datetime.now(UTC), run=run
    )
    assert done["changed"] and calls == [["mcp", "get"], ["mcp", "add"]]


def test_what_each_ai_asked_over_rest(owner, runtime):
    engine = runtime.ws.rt.brain.brain
    engine.client = "claude-code 2.1.0"
    engine.context("How long do web projects take?")
    found = owner.ok(owner.get("/api/brain/requests"))
    (request,) = found["requests"]
    assert request["app"] == "Claude Code" and request["got"]
    assert found["apps"] == ["Claude Code"]
    assert owner.ok(owner.get("/api/brain/requests?app=Cursor"))["requests"] == []
    listed = {a["label"]: a for a in owner.ok(owner.get("/api/brain/apps"))}
    assert listed["Claude Code"]["last_request"]["request"] == "How long do web projects take?"
    # One request in full: the exact text it got, and the startup context that went with it.
    full = owner.ok(owner.get(f"/api/brain/requests/{request['id']}"))
    assert full["id"] == request["id"] and full["text"]
    assert full["startup"]["text"].startswith("# Startup context")
    assert owner.get("/api/brain/requests/pkt-none").status_code == 404


def test_serve_and_demo_both_take_the_browser_flags():
    # _serve reads them, so every command that serves must define them
    for argv in (["serve"], ["demo", "personal"], ["demo", "personal", "--no-open"]):
        args = cli._parser().parse_args(argv)
        assert (args.open, args.no_open) == (False, argv[-1] == "--no-open")


def test_the_browser_opens_the_first_time_unless_told_not_to(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    data = str(tmp_path)
    assert cli.should_open(data, "127.0.0.1", wanted=False, refused=False)
    assert not cli.should_open(data, "127.0.0.1", wanted=True, refused=True)
    assert not cli.should_open(data, "10.0.0.5", wanted=True, refused=False)
    (tmp_path / cli.OPENED).write_text("opened")
    assert not cli.should_open(data, "127.0.0.1", wanted=False, refused=False)
    assert cli.should_open(data, "127.0.0.1", wanted=True, refused=False)
    monkeypatch.setenv("CI", "true")
    assert not cli.should_open(data, "127.0.0.1", wanted=True, refused=False)
