"""Skills from the app, end to end: run one and see what it made (in a folder of its own when
it makes files), improve one or write a new one through Review, edit one yourself."""

import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

from workspace_server.app import create_app
from workspace_server.runners import Runners

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_cli.py")
POSTS = """---
name: weekly-posts
description: Draft the week's LinkedIn posts from the content calendar.
triggers:
  - draft this week's posts
artifacts:
  - post
loads:
  - rules/style
---
# /weekly-posts

1. Read the calendar.
2. Draft one post per day.
"""


def add_skill(vault, category, name, text, files=None):
    folder = os.path.join(vault, "skills", category, name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    for rel, data in (files or {}).items():
        path = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)


@pytest.fixture
def client(runtime):
    """The app with a stand-in for Claude Code, so runs started here are real processes."""
    runtime.runners = Runners(
        runtime.ws,
        runtime.templates,
        base_url="http://127.0.0.1:8787",
        resolve=lambda spec: [sys.executable, FAKE] if spec.id == "claude" else None,
        outputs=runtime.settings.exports_dir,
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


def report(run):
    """What the stand-in CLI saw: its arguments, folder (with what was in it) and prompt."""
    for event in run["events"]:
        if event["kind"] == "text" and event["text"].startswith("debug "):
            return json.loads(event["text"][len("debug ") :])
    raise AssertionError("no report from the CLI")


def test_a_skill_runs_from_the_app_and_its_result_comes_back(owner, model, brain_vault):
    add_skill(brain_vault, "social", "weekly-posts", POSTS)
    cards = {c["name"]: c for c in owner.ok(owner.get("/api/skills"))["skills"]}
    assert cards["weekly-posts"]["makes_files"] is False
    assert cards["brand-sheet"]["makes_files"] is True  # it makes a PDF
    assert cards["weekly-posts"]["triggers"] == ["draft this week's posts"]
    task = owner.ok(
        owner.post("/api/skills/weekly-posts/runs", json={"ask": "Three posts on async reviews."}),
        201,
    )
    assert (task["template"], task["status"]) == ("skill", "ready")
    claim = model.tool("claim_task", task_id=task["id"])
    run_id = claim["structuredContent"]["run"]["id"]
    packet = claim["structuredContent"]["packet"]
    assert 'get_brain_skill (name "weekly-posts")' in packet["instructions"]["text"]
    skill = model.tool("get_brain_skill", name="weekly-posts")
    assert "Draft one post per day." in skill["content"][0]["text"]
    saved = model.tool(
        "save_skill_result", run_id=run_id, title="Async posts", text="**Monday:** Reviews."
    )
    assert not saved.get("isError"), saved
    model.tool("complete_task", run_id=run_id, summary="Three posts.")
    (run,) = owner.ok(owner.get("/api/skills/weekly-posts/runs"))
    assert run["status"] == "done" and run["result"]["text"] == "**Monday:** Reviews."
    cards = {c["name"]: c for c in owner.ok(owner.get("/api/skills"))["skills"]}
    assert cards["weekly-posts"]["last_run"]["status"] == "done"


def test_a_skill_that_makes_files_works_in_its_own_folder(owner, runtime, brain_vault, monkeypatch):
    add_skill(
        brain_vault,
        "design",
        "shared-assets",
        "---\nname: shared-assets\ndescription: Fonts and logos.\n---\n# /shared-assets\n",
        {"logo.png": b"png"},
    )
    path = os.path.join(brain_vault, "skills", "design", "brand-sheet", "SKILL.md")
    with open(path, encoding="utf-8") as handle:
        text = handle.read().replace("artifacts:", "depends_on:\n  - shared-assets\nartifacts:")
    add_skill(brain_vault, "design", "brand-sheet", text, {"scripts/build.py": b"print('pdf')"})
    task = owner.ok(owner.post("/api/skills/brand-sheet/runs", json={"ask": "One for Acme."}), 201)
    assert "./skill" in task["instructions"]
    monkeypatch.setenv("FAKE_CLI_MAKE", "acme-brand-sheet.pdf,skill/stray.png")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": task["id"]}), 201)
    done = finish(owner, run["id"])
    seen = report(done)
    argv = seen["argv"]
    assert "--restricted" in argv
    assert argv[argv.index("--tools") + 1] == "Read,Write,Edit,Glob,Grep,Bash"
    allowed = argv[argv.index("--allowedTools") + 1 : argv.index("--no-session-persistence")]
    assert allowed[0] == "mcp__contxt-app" and "Bash(python:*)" in allowed
    exports = runtime.settings.exports_dir
    assert os.path.dirname(seen["cwd"]) == os.path.join(exports, "skill-runs")
    assert os.path.basename(seen["cwd"]).endswith("-brand-sheet")
    assert {"skill/SKILL.md", "skill/scripts/build.py", "shared-assets/logo.png"} <= set(
        seen["listing"]
    )
    assert not any(p.endswith("mcp.json") for p in seen["listing"])  # its credential is elsewhere
    assert [f["name"] for f in done["made"]] == ["acme-brand-sheet.pdf", "stray.png"]
    assert sorted(os.listdir(done["folder"])) == ["acme-brand-sheet.pdf", "stray.png"]
    assert next(e for e in done["events"] if e["kind"] == "files")["text"].startswith("Made 2")
    (listed,) = owner.ok(owner.get("/api/skills/brand-sheet/runs"))
    assert [f["name"] for f in listed["files"]] == ["acme-brand-sheet.pdf", "stray.png"]
    got = owner.get(f"/api/skills/runs/{task['id']}/files/acme-brand-sheet.pdf")
    assert got.status_code == 200 and got.content == b"made by the run: acme-brand-sheet.pdf"
    assert "attachment" in got.headers["content-disposition"]
    missing = owner.get(f"/api/skills/runs/{task['id']}/files/..%2Fsecret.txt")
    assert missing.status_code == 404
    # A picture it made shows in place; nothing it made runs in the app's origin.
    picture = owner.get(
        f"/api/skills/runs/{task['id']}/files/stray.png", params={"download": "false"}
    )
    assert picture.headers["content-disposition"].startswith("inline")
    assert "sandbox" in picture.headers["content-security-policy"]
    assert picture.headers["x-content-type-options"] == "nosniff"


def test_the_skills_page_runs_several_skills_with_each_ones_files(
    owner, runtime, brain_vault, monkeypatch
):
    add_skill(brain_vault, "social", "weekly-posts", POSTS)
    task = owner.ok(
        owner.post(
            "/api/skills/runs",
            json={"names": ["weekly-posts", "brand-sheet"], "ask": "A sheet, then posts."},
        ),
        201,
    )
    assert task["title"] == "Run /weekly-posts, /brand-sheet"
    assert "in this order: /weekly-posts, /brand-sheet" in task["instructions"]
    assert "named after it" in task["instructions"]  # one of them makes files
    monkeypatch.setenv("FAKE_CLI_MAKE", "sheet.pdf")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": task["id"]}), 201)
    seen = report(finish(owner, run["id"]))
    assert {"weekly-posts/SKILL.md", "brand-sheet/SKILL.md"} <= set(seen["listing"])
    (latest, *_) = owner.ok(owner.get("/api/skills/runs"))
    assert latest["task_id"] == task["id"]
    assert latest["skills"] == ["weekly-posts", "brand-sheet"]
    assert [f["name"] for f in latest["files"]] == ["sheet.pdf"]
    # with none chosen, the Brain picks
    picked = owner.ok(owner.post("/api/skills/runs", json={"ask": "Posts for Tuesday."}), 201)
    assert picked["title"].startswith("Run what fits")
    too_many = owner.post("/api/skills/runs", json={"names": list("abcdefg"), "ask": "x"})
    assert too_many.status_code == 422


def test_a_folder_a_stopped_server_left_is_tidied_and_listed(owner, runtime):
    task = owner.ok(owner.post("/api/skills/brand-sheet/runs", json={"ask": "One for Acme."}), 201)
    folder = os.path.join(runtime.settings.exports_dir, "skill-runs", "2026-09-28-brand-sheet")
    os.makedirs(os.path.join(folder, "skill"))
    with open(os.path.join(folder, "skill", "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("# /brand-sheet")
    with open(os.path.join(folder, "acme.pdf"), "wb") as handle:
        handle.write(b"%PDF")
    marker = os.path.join(folder, ".run.json")
    with open(marker, "w", encoding="utf-8") as handle:
        json.dump({"task_id": task["id"], "copies": {"skill": ["SKILL.md"]}}, handle)
    runners = runtime.runners
    runners.sweep()
    assert os.path.isdir(os.path.join(folder, "skill"))  # it may still be running: left alone
    old = time.time() - runners.timeout - 600
    os.utime(marker, (old, old))
    runners.sweep()
    assert sorted(os.listdir(folder)) == ["acme.pdf"]
    (listed,) = owner.ok(owner.get("/api/skills/brand-sheet/runs"))
    assert [f["name"] for f in listed["files"]] == ["acme.pdf"]


def test_html_a_run_made_always_downloads(owner, runtime, monkeypatch):
    task = owner.ok(owner.post("/api/skills/brand-sheet/runs", json={"ask": "A page."}), 201)
    monkeypatch.setenv("FAKE_CLI_MAKE", "page.html,picture.svg")
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": task["id"]}), 201)
    finish(owner, run["id"])
    for name in ("page.html", "picture.svg"):
        got = owner.get(f"/api/skills/runs/{task['id']}/files/{name}", params={"download": "false"})
        assert got.status_code == 200
        assert got.headers["content-disposition"].startswith("attachment"), name


def test_a_run_that_makes_nothing_leaves_no_folder(owner, runtime):
    task = owner.ok(owner.post("/api/skills/brand-sheet/runs", json={"ask": "Nothing."}), 201)
    run = owner.ok(owner.post("/api/runners/claude/runs", json={"task_id": task["id"]}), 201)
    done = finish(owner, run["id"])
    assert done["folder"] is None and done["made"] == []
    assert os.listdir(os.path.join(runtime.settings.exports_dir, "skill-runs")) == []


def test_improving_a_skill_waits_in_review_beside_what_it_changes(owner, model):
    task = owner.ok(
        owner.post("/api/skills/brand-sheet/improve", json={"ask": "Add a step for the logo."}),
        201,
    )
    claim = model.tool("claim_task", task_id=task["id"])
    run_id = claim["structuredContent"]["run"]["id"]
    made = model.tool(
        "propose_brain_skill",
        run_id=run_id,
        target="brand-sheet",
        body="# /brand-sheet\n\n1. Gather the palette.\n2. Place the logo.\n3. Export.",
        reason="Adds the logo step.",
    )
    proposal = made["structuredContent"]["proposal"]
    assert proposal["status"] == "pending", made
    model.tool("complete_task", run_id=run_id, summary="Proposed.")
    review = owner.ok(owner.get("/api/brain/review"))
    waiting = next(p for p in review["proposals"] if p["id"] == proposal["proposal_id"])
    assert waiting["kind"] == "skill.update"
    assert "Write the voice lines" in waiting["analysis"]["skill_before"]["body"]
    assert any(task["id"] == b["task_id"] for b in review["batches"])
    owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={"decisions": [{"action": "approve", "proposal_id": proposal["proposal_id"]}]},
        )
    )
    skill = owner.ok(owner.get("/api/brain/skills/brand-sheet"))
    assert "Place the logo." in skill["text"]
    (run,) = owner.ok(owner.get("/api/skills/brand-sheet/runs"))
    assert run["kind"] == "improve" and run["proposal"]["id"] == proposal["proposal_id"]


def test_an_improvement_sent_as_edits_keeps_the_rest_word_for_word(owner, model):
    task = owner.ok(
        owner.post("/api/skills/brand-sheet/improve", json={"ask": "Check contrast first."}),
        201,
    )
    run_id = model.tool("claim_task", task_id=task["id"])["structuredContent"]["run"]["id"]
    missed = model.tool(
        "propose_brain_skill",
        run_id=run_id,
        target="brand-sheet",
        edits=[{"find": "3. Print it.", "replace": "3. Check contrast."}],
    )
    assert missed["isError"] and "occurs 0 times" in missed["content"][0]["text"]
    made = model.tool(
        "propose_brain_skill",
        run_id=run_id,
        target="brand-sheet",
        edits=[
            {
                "find": "1. Gather the palette and type choices.",
                "replace": "1. Gather the palette and type choices.\n2. Check the contrast.",
            }
        ],
    )
    proposal = made["structuredContent"]["proposal"]
    review = owner.ok(owner.get("/api/brain/review"))
    waiting = next(p for p in review["proposals"] if p["id"] == proposal["proposal_id"])
    assert "2. Check the contrast." in waiting["body"]
    assert "2. Write the voice lines in plain language." in waiting["body"]  # untouched
    assert waiting["body"].startswith("# /brand-sheet")


def test_a_new_skill_is_written_by_a_model_and_waits_in_review(owner, model):
    task = owner.ok(
        owner.post("/api/skills/drafts", json={"ask": "A skill for client kickoff agendas."}),
        201,
    )
    claim = model.tool("claim_task", task_id=task["id"])
    run_id = claim["structuredContent"]["run"]["id"]
    assert "design" in claim["structuredContent"]["packet"]["instructions"]["text"]
    made = model.tool(
        "propose_brain_skill",
        run_id=run_id,
        name="kickoff-agenda",
        category="design",
        description="Write a client kickoff agenda.",
        triggers="write a kickoff agenda",
        artifacts=["document"],
        body="# /kickoff-agenda\n\n1. List the goals.\n2. Set the times.",
    )
    assert made["structuredContent"]["proposal"]["status"] == "pending", made
    listed = owner.ok(owner.get("/api/skills"))
    assert [w["name"] for w in listed["waiting"]] == ["kickoff-agenda"]
    review = owner.ok(owner.get("/api/brain/review"))
    (waiting,) = [p for p in review["proposals"] if p["kind"] == "skill.create"]
    assert waiting["target"]["triggers"] == ["write a kickoff agenda"]


def test_your_own_edit_applies_at_once_and_undo_takes_it_back(owner):
    before = owner.ok(owner.get("/api/brain/skills/brand-sheet"))["text"]
    done = owner.ok(
        owner.put(
            "/api/skills/brand-sheet",
            json={"body": "# /brand-sheet\n\n1. Ask for the palette first.", "reason": "Simpler"},
        )
    )
    assert done["checkpoint"]["id"]
    after = owner.ok(owner.get("/api/brain/skills/brand-sheet"))["text"]
    assert "Ask for the palette first." in after
    versions = owner.ok(owner.get("/api/skills/brand-sheet/versions", params={"text": "true"}))
    assert "Ask for the palette first." in versions[0]["body"]
    owner.ok(owner.post(f"/api/brain/checkpoints/{done['checkpoint']['id']}/undo"))
    assert owner.ok(owner.get("/api/brain/skills/brand-sheet"))["text"] == before
    refused = owner.put("/api/skills/no-such-skill", json={"body": "# /x"})
    assert refused.status_code == 404
