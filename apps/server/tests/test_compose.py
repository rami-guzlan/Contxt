"""Compose over REST, on the sample Brain: the whole prompt a model gets for a request and its
picks, with its size in tokens; the short request for any AI; a run like any skill run; the
request improved by the chosen model (a stand-in here); and prompts kept word for word in the
Brain, with their versions and uses, whether saved here or by an AI in a chat."""

import json
import os
import time

from workspace_server.knowledge_agent import AgentWork
from workspace_server.models import ModelChoice, Models

POSTS = """---
name: weekly-posts
description: Draft the week's LinkedIn posts from the content calendar.
triggers:
  - draft this week's posts
artifacts:
  - post
---
# /weekly-posts

1. Read the calendar.
2. Draft one post per day.
"""


def add_posts_skill(vault):
    folder = os.path.join(vault, "skills", "social", "weekly-posts")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(POSTS)


class StubModels(Models):
    """Answers from a list, and remembers what it was asked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def list(self):
        return [ModelChoice("claude", "Claude Code (your CLI)", "cli", True, "here", False)]

    def ask(self, who, choice, prompt, *, json_only=False, timeout=240.0, job="agent"):
        self.asked.append({"model": choice.id, "prompt": prompt, "json": json_only})
        return self.answers.pop(0)


def finish(owner, job_id, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = owner.ok(owner.get(f"/api/brain/agent/jobs/{job_id}"))
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def outline(owner):
    doc = owner.ok(owner.post("/api/workspace/docs", json={"title": "Q4 outline"}), 201)
    return owner.ok(
        owner.put(f"/api/notes/{doc['id']}", json={"body": "1. Reviews run on Fridays."})
    )


def test_the_whole_prompt_is_assembled_with_its_size(owner, brain_vault):
    add_posts_skill(brain_vault)
    doc = outline(owner)
    spec = {
        "request": "Three posts from my outline.",
        "skills": ["weekly-posts"],
        "docs": [doc["id"]],
        "library": ["references/style-guide.md"],
    }
    got = owner.ok(owner.post("/api/compose/assemble", json=spec))
    assert got["title"] == "Run /weekly-posts"
    prompt = got["prompt"]
    for part in (
        "## Instructions",
        "## Pinned inputs",
        "Reviews run on Fridays.",
        "references/style-guide.md",
    ):
        assert part in prompt
    assert "## Long-term context" in prompt
    assert got["tokens"] > 0
    assert [p["label"] for p in got["parts"]] == [
        "Instructions",
        "Note: Q4 outline",
        "The Brain's brief",
    ]
    assert got["short"].startswith("Three posts from my outline.")
    assert "skills_get: /weekly-posts" in got["short"] and got["short_tokens"] > 0
    assert (got["skills"], got["agent"], got["makes_files"]) == (["weekly-posts"], None, False)
    assert (
        owner.post("/api/compose/assemble", json={"request": "x", "skills": ["nope"]}).status_code
        == 404
    )
    assert owner.post("/api/compose/assemble", json={"request": ""}).status_code == 422


def test_a_run_is_a_task_and_a_saved_prompt_counts_it(owner, model, brain_vault):
    add_posts_skill(brain_vault)
    saved = owner.ok(
        owner.post(
            "/api/prompts",
            json={
                "title": "Weekly posts",
                "body": "Three posts.",
                "picks": {"skills": ["weekly-posts"]},
            },
        ),
        201,
    )
    assert saved["picks"]["skills"] == ["weekly-posts"] and saved["uses"] == 0
    task = owner.ok(
        owner.post(
            "/api/compose/run",
            json={"request": "Three posts.", "skills": ["weekly-posts"], "prompt_id": saved["id"]},
        ),
        201,
    )
    assert (task["title"], task["template"]) == ("Weekly posts", "skill")
    claim = model.tool("claim_task", task_id=task["id"])["structuredContent"]
    assert "in this order: /weekly-posts" in claim["packet"]["instructions"]["text"]
    assert owner.ok(owner.get("/api/prompts"))[0]["uses"] == 1
    changed = owner.ok(
        owner.put(
            f"/api/prompts/{saved['id']}",
            json={"body": "Three posts, short.", "expected_version": saved["version"]},
        )
    )
    assert changed["revision"] == 2 and [v["revision"] for v in changed["versions"]] == [2, 1]
    stale = owner.put(
        f"/api/prompts/{saved['id']}", json={"body": "Again.", "expected_version": saved["version"]}
    )
    assert stale.status_code == 409
    owner.ok(owner.delete(f"/api/prompts/{saved['id']}"))
    assert owner.ok(owner.get("/api/prompts")) == []
    assert [p["id"] for p in owner.ok(owner.get("/api/prompts", params={"archived": "true"}))] == [
        saved["id"]
    ]
    owner.ok(owner.post(f"/api/prompts/{saved['id']}/restore"))
    assert [p["id"] for p in owner.ok(owner.get("/api/prompts", params={"q": "short"}))] == [
        saved["id"]
    ]


def test_the_chosen_model_improves_the_request(owner, runtime, brain_vault):
    add_posts_skill(brain_vault)
    answer = {
        "prompt": "Three LinkedIn posts for next week, following /weekly-posts.",
        "changes": ["Says how many and for when."],
        "used": ["/weekly-posts"],
        "questions": [],
    }
    models = StubModels([json.dumps(answer)])
    runtime.models = models
    runtime.agent = AgentWork(runtime.ws, models)
    job = owner.ok(
        owner.post("/api/compose/improve", json={"request": "posts", "skills": ["weekly-posts"]}),
        201,
    )
    done = finish(owner, job["id"])
    assert done["status"] == "done", done
    assert done["result"] == answer
    (asked,) = models.asked
    assert asked["json"] is True
    assert (
        "## The request, as" in asked["prompt"]
        and "- /weekly-posts: Draft the week" in asked["prompt"]
    )


def test_a_prompt_saved_in_a_chat_shows_word_for_word_with_its_file(owner, runtime):
    """What an AI does when asked to "save this prompt to my Brain" (the Brain's files_upload)."""
    from brainkit import mcp_server

    engine = runtime.ws.rt.brain.brain
    save = mcp_server.HANDLERS["files_upload"]
    words = "Draft the monthly client update.\n\n1. Wins\n2. Risks\n\nKeep it under 300 words."
    made = save(
        engine,
        {
            "content": words,
            "filename": "client-update.md",
            "title": "Client update",
            "kind": "prompt",
            "tags": "clients, monthly",
        },
    )
    assert made.data.get("status") == "applied", made.text
    sheet = save(
        engine,
        {
            "content": "client,owner\nAcme,Ana\n",
            "filename": "clients.csv",
            "attach_to": made.data["path"],
        },
    )
    assert sheet.data.get("status") == "applied", sheet.text
    (kept,) = owner.ok(owner.get("/api/prompts"))
    assert (kept["title"], kept["body"], kept["tags"], kept["origin"]) == (
        "Client update",
        words,
        ["clients", "monthly"],
        "chat",
    )
    assert [a["path"] for a in kept["attachments"]] == [sheet.data["path"]]
    # A connected AI finds it by name and opens it; no brief carries it unasked.
    hits = engine.search("client update").data.get("hits") or []
    assert kept["id"] in [h["id"] for h in hits]
    brief = engine.context("Draft the monthly client update with wins and risks")
    assert kept["id"] not in (brief.data.get("note_ids") or [])
    # It is a prompt, not a Library item to route: the Library tab leaves it to Prompts.
    assert [
        i["kind"] for i in owner.ok(owner.get("/api/library")) if i["path"] == kept["path"]
    ] == ["prompt"]


def test_prompts_saved_before_the_brain_move_in_with_their_versions(owner, runtime):
    from workspace_core.db import schema

    ws = runtime.ws
    with ws.rt.write() as tx:
        old = tx.insert(
            schema.context_items,
            {
                "id": tx.new_id("ctx"),
                "workspace_id": ws.rt.workspace_id,
                "scope_kind": "workspace",
                "scope_id": None,
                "kind": "prompt",
                "title": "Weekly posts",
                "body": "Three posts, short.",
                "labels": [],
                "revision": 2,
                "provenance": {"picks": {"skills": ["weekly-posts"]}},
                "created_by": "act_owner",
                "created_at": tx.now,
                "updated_at": tx.now,
                "version": 2,
                "archived_at": None,
            },
        )
        for revision, words in ((1, "Three posts."), (2, "Three posts, short.")):
            tx.insert(
                schema.context_item_revisions,
                {
                    "item_id": old["id"],
                    "revision": revision,
                    "title": "Weekly posts",
                    "body": words,
                    "created_by": "act_owner",
                    "created_at": tx.now,
                },
            )
    (moved,) = owner.ok(owner.get("/api/prompts"))
    assert (moved["title"], moved["body"], moved["picks"]["skills"]) == (
        "Weekly posts",
        "Three posts, short.",
        ["weekly-posts"],
    )
    found = owner.ok(owner.get(f"/api/prompts/{old['id']}"))
    assert found["id"] == moved["id"]
    assert [v["body"] for v in found["versions"]] == ["Three posts, short.", "Three posts."]
    assert len(owner.ok(owner.get("/api/prompts"))) == 1  # once
