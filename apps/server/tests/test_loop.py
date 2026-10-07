"""The loop over the real adapters: REST for the person, MCP for the model. A person asks a
model to find what to remember in a note; the model proposes; the person decides."""

import os

TOOLS = {
    "get_due_tasks",
    "claim_task",
    "get_task_packet",
    "append_task_event",
    "complete_task",
    "search_context",
    "get_context_item",
    "get_brain_entry",
    "get_brain_skill",
    "get_brain_reference",
    "propose_brain_entry",
    "save_digest",
    "save_skill_result",
    "propose_brain_skill",
}


def _remember(owner, model, note):
    return owner.ok(
        owner.post(f"/api/notes/{note['id']}/remember", json={"assignee_id": model.actor_id}),
        201,
    )


def test_health_needs_no_token_and_everything_else_does(client, owner):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["brain"] is True
    denied = client.get("/api/me")
    assert denied.status_code == 401 and denied.headers["www-authenticate"] == "Bearer"
    me = owner.ok(owner.get("/api/me"))
    assert me["kind"] == "human" and "brain.govern" in me["actions"]


def test_connecting_a_model_returns_its_token_and_setup_once(owner, model):
    setup = model.connection["setup"]
    assert setup["url"].endswith("/mcp") and model.connection["token"] in setup["config"]
    assert "get_due_tasks" in model.connection["worker_prompt"]
    again = owner.ok(owner.get(f"/api/actors/{model.actor_id}/setup"))
    assert model.connection["token"] not in again["setup"]["config"]


def test_the_full_loop(owner, model, note):
    task = _remember(owner, model, note)
    assert (task["template"], task["status"]) == ("distill", "ready")

    init = model.mcp(
        "initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "test"}}
    )
    assert init["result"]["serverInfo"]["name"] == "contxt-app"
    names = {t["name"] for t in model.mcp("tools/list")["result"]["tools"]}
    assert names == TOOLS

    due = model.tool("get_due_tasks")
    assert due["structuredContent"]["tasks"][0]["id"] == task["id"]
    claim = model.tool("claim_task", task_id=task["id"], idempotency_key=f"{task['id']}:now")
    assert not claim["isError"]
    run_id = claim["structuredContent"]["run"]["id"]
    text = claim["content"][0]["text"]
    assert "Clients prefer async reviews on Fridays." in text and run_id in text
    assert "Long-term context from the Brain" in text  # the fixture brain answered
    assert f'propose_brain_entry(run_id="{run_id}"' in text

    progress = model.tool("append_task_event", run_id=run_id, type="progress", message="Reading")
    assert not progress["isError"]
    made = model.tool(
        "propose_brain_entry",
        run_id=run_id,
        title="Async reviews",
        statement="Clients prefer async design reviews on Fridays.",
        evidence="The note says so.",
        sources=[f"context_item:{note['id']}"],
    )
    proposal_id = made["structuredContent"]["proposal"]["proposal_id"]
    done = model.tool("complete_task", run_id=run_id, summary="One durable statement")
    assert done["structuredContent"]["task_status"] == "done"  # nothing to review but the proposal

    (request,) = owner.ok(owner.get(f"/api/notes/{note['id']}/remember"))
    assert request["summary"] == "One durable statement"
    assert request["proposals"] == [
        {"id": proposal_id, "title": "Async reviews", "status": "pending"}
    ]
    review = owner.ok(owner.get("/api/brain/review"))
    (batch,) = [b for b in review["batches"] if b["task_id"] == task["id"]]
    assert batch["proposal_ids"] == [proposal_id]
    assert batch["documents"] == [{"id": note["id"], "title": "Client notes"}]
    assert (
        model.post(f"/api/brain/proposals/{proposal_id}/decide", json={"approve": True}).status_code
        == 403
    )
    decided = owner.ok(
        owner.post(f"/api/brain/proposals/{proposal_id}/decide", json={"approve": True})
    )
    assert decided["status"] == "approved"
    hits = owner.ok(owner.get("/api/brain/search?q=async design reviews"))
    assert any(h["id"] == proposal_id for h in hits)
    (request,) = owner.ok(owner.get(f"/api/notes/{note['id']}/remember"))
    assert request["proposals"][0]["status"] == "approved"

    kinds = {e["type"] for e in owner.ok(owner.get("/api/events"))}
    assert {"note.created", "task.claimed", "brain.proposed", "brain.approved"} <= kinds
    assert "bus.polled" not in kinds


def test_notes_reach_a_model_only_pinned_to_its_work(owner, model, note):
    found = model.tool("search_context", query="async reviews")
    assert note["id"] not in str(found["structuredContent"])
    hidden = model.tool("get_context_item", item_id=note["id"])
    assert hidden["isError"]
    assert model.get(f"/api/notes/{note['id']}").status_code == 404
    assert model.ok(model.get("/api/notes")) == []
    _remember(owner, model, note)
    opened = model.tool("get_context_item", item_id=note["id"])
    assert not opened["isError"] and "async reviews" in opened["content"][0]["text"]


def test_models_cannot_use_human_gates(owner, model, note):
    assert (
        model.post("/api/connections", json={"name": "x", "provider": "other"}).status_code == 403
    )
    assert model.post("/api/notes", json={"title": "Mine"}).status_code == 403
    assert model.put(f"/api/notes/{note['id']}", json={"body": "x"}).status_code in (403, 404)
    assert model.put("/api/brain/distill/settings", json={"assignee_id": None}).status_code == 403
    assert model.post("/api/legacy/bring-into-brain").status_code == 403


def test_a_second_claim_gets_no_work(owner, model, note):
    task = _remember(owner, model, note)
    model.tool("claim_task", task_id=task["id"])
    again = model.tool("claim_task", task_id=task["id"])
    assert again["isError"] and "not available" in again["content"][0]["text"]


def test_waiting_ai_work_can_be_cancelled(owner, note):
    task = owner.ok(owner.post(f"/api/notes/{note['id']}/remember", json={}), 201)
    assert (task["status"], task["assignee_id"]) == ("draft", None)  # no model yet: it waits
    (request,) = owner.ok(owner.get(f"/api/notes/{note['id']}/remember"))
    assert request["waiting"] is True
    cancelled = owner.ok(owner.post(f"/api/tasks/{task['id']}/cancel", json={"reason": "Not now"}))
    assert cancelled["status"] == "cancelled"
    assert owner.ok(owner.get(f"/api/tasks/{task['id']}"))["status"] == "cancelled"


def test_mcp_protocol_edges(client, owner, model):
    assert (
        client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401
    )
    notice = model.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notice.status_code == 202
    unknown = model.mcp("tools/call", {"name": "create_artifact", "arguments": {}})
    assert unknown["error"]["code"] == -32602  # gone with the outputs
    missing = model.mcp("nope/nope")
    assert missing["error"]["code"] == -32601
    foreign = model.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Origin": "https://evil.example"},
    )
    assert foreign.status_code == 403
    old = model.mcp("tools/call", {"name": "get_due_tasks", "arguments": {}}, version="2024-11-05")
    assert "structuredContent" not in old["result"]
    prompt = model.mcp("prompts/get", {"name": "worker"})
    text = prompt["result"]["messages"][0]["content"]["text"]
    assert "Claude Code" in text and "create_artifact" not in text
    assert client.get("/mcp").status_code == 405


def test_browser_sign_in_uses_a_cookie_and_a_csrf_header(client):
    signed = client.get(
        f"/auth/login?token={'wst_' + 'owner-token-for-tests-' + 'x' * 20}", follow_redirects=False
    )
    assert signed.status_code == 303 and "httponly" in signed.headers["set-cookie"].lower()
    # Its own name: another workspace on this computer keeps its own sign-in.
    assert signed.headers["set-cookie"].startswith("workspace_token_ws")
    assert client.get("/api/me").status_code == 200
    blocked = client.post("/api/notes", json={"title": "No header"})
    assert blocked.status_code == 403
    allowed = client.post(
        "/api/notes", json={"title": "With header"}, headers={"X-Workspace-CSRF": "1"}
    )
    assert allowed.status_code == 201


def test_a_session_from_before_each_workspace_named_its_cookie_still_works(client):
    client.cookies.set("workspace_token", "wst_" + "owner-token-for-tests-" + "x" * 20)
    assert client.get("/api/me").status_code == 200
    client.cookies.clear()
    client.cookies.set("workspace_token", "wst_someone-elses-workspace-token-xxxxxxxxxx")
    assert client.get("/api/me").status_code == 401


def test_model_proposals_wait_for_a_person(owner, model, runtime):
    result = model.tool(
        "propose_brain_entry",
        title="Friday reviews",
        statement="Design reviews happen on Fridays.",
        evidence="Client email, 28 Sep",
    )
    assert not result["isError"]
    assert result["structuredContent"]["proposal"]["status"] == "pending"
    waiting = owner.ok(owner.get("/api/brain/proposals"))
    assert waiting[0]["proposer"].startswith("model:Claude Code")
    home = owner.ok(owner.get("/api/home"))
    assert home["counts"]["brain_proposals"] == 1
    assert home["workspace"]["name"] == "Test workspace"


def test_search_covers_the_brain_its_projects_and_your_notes(owner, note):
    owner.ok(
        owner.post(
            "/api/brain/projects",
            json={"name": "Async reviews pilot", "summary": "Try async reviews with two clients"},
        ),
        201,
    )
    found = owner.ok(owner.get("/api/search?q=async reviews"))
    assert [n["id"] for n in found["notes"]] == [note["id"]]
    assert found["notes"][0]["body"] is None  # listed, not read out
    assert [p["title"] for p in found["projects"]] == ["Async reviews pilot"]
    assert owner.ok(owner.get("/api/search?q=web design"))["brain"]


def test_without_a_web_build_the_root_explains_itself(client):
    page = client.get("/")
    assert page.status_code == 200 and "The web app is not here yet" in page.text
    assert client.get("/api/nope").status_code == 404


def test_the_built_web_app_is_served_with_a_single_page_fallback(client, runtime):
    dist = runtime.settings.web_dist
    os.makedirs(os.path.join(dist, "assets"))
    with open(os.path.join(dist, "index.html"), "w", encoding="utf-8") as handle:
        handle.write("<div id=root></div>")
    with open(os.path.join(dist, "assets", "app.js"), "w", encoding="utf-8") as handle:
        handle.write("console.log(1)")
    assert client.get("/").text == "<div id=root></div>"
    assert client.get("/projects/proj_1").text == "<div id=root></div>"  # client-side route
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/../../secrets").status_code in (200, 404)
    assert "owner-token" not in client.get("/../../secrets").text


def test_packets_carry_the_brains_knowledge_without_its_session_plumbing(runtime):
    context = runtime.brain.context(
        "Write a headline for our web design service page. Always follow the brief."
    )
    text = context.text
    assert "Headlines use sentence case" in text  # the brain's house style still arrives
    assert "# Standing context" in text and "## Identity" in text
    for plumbing in (
        "get_task_context",
        "session_id",
        "## Capture",
        "## Continuity",
        "## Start",
        "propose_note",
        "record_focus_update",
    ):
        assert plumbing not in text, plumbing


def test_models_open_brain_procedures_and_references_over_mcp(owner, model):
    skill = model.tool("get_brain_skill", name="/brand-sheet")
    assert not skill["isError"] and "Export a one-page PDF" in skill["content"][0]["text"]
    assert skill["structuredContent"]["skill"]["loads"]
    reference = model.tool("get_brain_reference", path="references/style-guide.md")
    assert not reference["isError"] and "Studio style guide" in reference["content"][0]["text"]
    missing = model.tool("get_brain_skill", name="nope")
    assert missing["isError"]


def test_skill_candidates_in_a_packet_say_how_to_open_them(runtime):
    text = runtime.brain.context("Create a brand sheet for the new client").text
    assert "/brand-sheet" in text and "get_brain_skill" in text


def test_the_owner_verifies_and_marks_brain_entries(owner, model, runtime):
    marked = owner.ok(
        owner.post(
            "/api/brain/entries/facts-services-002/mark",
            json={"state": "stale", "reason": "Timelines changed"},
        )
    )
    assert marked["stale"] and marked["stale_reason"] == "marked stale"
    packet = runtime.brain.context("How long do web design projects run?").text
    assert "stale: marked stale" in packet
    assert model.post("/api/brain/entries/facts-services-002/verify", json={}).status_code == 403
    verified = owner.ok(
        owner.post("/api/brain/entries/facts-services-002/verify", json={"confidence": "confirmed"})
    )
    assert not verified["stale"] and verified["confidence"] == "confirmed"
    assert owner.post("/api/brain/entries/nope/verify", json={}).status_code == 404
    bad = owner.post(
        "/api/brain/entries/facts-services-002/mark", json={"state": "forgotten", "reason": "x"}
    )
    assert bad.status_code == 422
