"""Workspace's live context, Activity's tasks and handoffs, and outputs linked to what they
are for (build step 6): a sheet from a template edited in the app, an AI's value arriving
marked or waiting, the composer passing a task on, Catch up's new cards, and an output in its
project and account."""

import os


def make_accounts(owner):
    made = owner.ok(
        owner.post(
            "/api/work/live/act",
            json={"action": "create_sheet", "fields": {"template": "accounts"}},
        )
    )
    assert made["sheet"]["id"] == "accounts"
    owner.ok(
        owner.post(
            "/api/work/live/act",
            json={
                "action": "add_row",
                "fields": {
                    "sheet": "accounts",
                    "key": "Northwind",
                    "values": {"Health": "green", "Renewal date": "2026-11-02"},
                },
            },
        )
    )


def test_a_sheet_from_a_template_is_edited_and_keeps_its_history(owner):
    make_accounts(owner)
    page = owner.ok(owner.get("/api/work/live"))
    assert [s["id"] for s in page["sheets"]] == ["accounts"]
    assert any(t["id"] == "tasks" and t["builtin"] for t in page["templates"])
    sheet = owner.ok(
        owner.post(
            "/api/work/live/act",
            json={
                "action": "write",
                "fields": {"sheet": "accounts", "row": "Northwind", "values": {"Health": "amber"}},
            },
        )
    )
    row = sheet["rows"][0]
    assert row["cells"]["Health"]["value"] == "amber"
    assert "Days until renewal" in row["computed"]
    assert sheet["summary"]["columns"]["Health"]["by_status"] == {"amber": 1}
    history = owner.ok(owner.get("/api/work/live/accounts/history?row=Northwind&column=Health"))
    assert [e["value"] for e in history] == ["amber", "green"]
    bad = owner.post(
        "/api/work/live/act",
        json={
            "action": "write",
            "fields": {"sheet": "accounts", "row": "Northwind", "values": {"Health": "purple"}},
        },
    )
    assert bad.status_code == 422


def test_an_ais_values_arrive_marked_or_wait_in_catch_up(owner, model):
    make_accounts(owner)
    owner.ok(
        owner.post(
            "/api/work/live/act",
            json={
                "action": "add_column",
                "fields": {
                    "sheet": "accounts",
                    "column": {"name": "Contract owner", "friction": "confirm"},
                },
            },
        )
    )
    reply = model.tool(
        "update_state",
        updates=[
            {
                "sheet": "accounts",
                "row": "Northwind",
                "column": "Next step",
                "value": "Send the deck",
            },
            {"sheet": "accounts", "row": "Northwind", "column": "Contract owner", "value": "Dana"},
        ],
        evidence="the call notes",
    )
    assert not reply.get("isError"), reply
    sheet = owner.ok(owner.get("/api/work/live/accounts"))
    assert sheet["rows"][0]["cells"]["Next step"]["ai"] is True
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    waiting = plan["state_waiting"]
    assert [w["column"] for w in waiting] == ["Contract owner"]
    owner.ok(
        owner.post(
            "/api/work/live/act",
            json={
                "action": "decide",
                "fields": {
                    "sheet": "accounts",
                    "row": "Northwind",
                    "event": waiting[0]["event"],
                    "accept": True,
                },
            },
        )
    )
    assert owner.ok(owner.get("/api/brain/catch-up"))["state_waiting"] == []
    read = model.tool("get_state", sheet="accounts", row="Northwind")
    assert "Contract owner: Dana" in read["content"][0]["text"]


def test_the_composer_passes_a_task_on_and_it_shows_where_it_stands(owner, model):
    opened = owner.ok(
        owner.post("/api/work/handoffs", json={"new_task": {"title": "Update the pricing skill"}})
    )
    assert opened["task"]["id"] == "T-1"
    refused = owner.post("/api/work/handoffs", json={"task": "T-1", "to": "Claude Code"})
    assert refused.status_code == 422 and "done_when" in refused.text
    owner.ok(
        owner.post(
            "/api/work/handoffs",
            json={
                "task": "T-1",
                "to": "Claude Code, repo contxt",
                "done_when": "The skill uses the corrected figure",
                "next_step": "Update the figure and propose the change",
            },
        )
    )
    now = owner.ok(owner.get("/api/work/handoffs"))
    assert [t["id"] for t in now["lanes"]["handed_off"]] == ["T-1"]
    detail = owner.ok(owner.get("/api/work/handoffs/T-1"))
    assert "Next step: Update the figure" in detail["rendered"]
    claimed = model.tool("hand_off", task="T-1", claim=True)
    assert not claimed.get("isError"), claimed
    back = owner.ok(owner.post("/api/work/handoffs/T-1/take-back"))
    assert back["task_status"] == "waiting_for_you"
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    assert [t["id"] for t in plan["handed"]] == ["T-1"]
    timeline = owner.ok(owner.get("/api/work/handoffs/timeline"))
    kinds = [e["kind"] for e in timeline["events"]]
    assert kinds[0] == "open" and "handoff" in kinds and "claim" in kinds


def test_an_accepted_suggestion_becomes_a_task_on_its_goal(owner):
    page = owner.ok(
        owner.post(
            "/api/goals",
            json={"title": "Grow webinar attendance", "first_steps": ["Book 2 partner promos"]},
        ),
        201,
    )
    step = page["suggestions"][0]
    after = owner.ok(
        owner.post(f"/api/goals/{page['id']}/suggestions/{step['id']}", json={"accept": True})
    )
    assert [t["task"] for t in after["tasks"]] == ["Book 2 partner promos"]
    checklist = next(b for b in after["board"]["blocks"] if b["type"] == "checklist")
    assert checklist["items"][-1]["text"] == "T-1 Book 2 partner promos"


def test_an_output_says_its_project_and_what_it_is_for(owner, runtime):
    make_accounts(owner)
    root = runtime.outputs.root
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, "renewal.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Renewal")
    with open(os.path.join(root, "loose.md"), "w", encoding="utf-8") as handle:
        handle.write("x")
    runtime.brain.brain.record_output(
        path, title="Renewal deck", for_row="Northwind", maker="Accounts agent"
    )
    files = {f["path"]: f for f in owner.ok(owner.get("/api/outputs"))["files"]}
    assert files["renewal.md"]["for"] == "accounts/Northwind"
    assert files["renewal.md"]["maker"] == "Accounts agent"
    assert files["loose.md"]["for"] is None
    owner.ok(
        owner.post("/api/outputs/link", json={"path": "loose.md", "row": "accounts/Northwind"})
    )
    files = {f["path"]: f for f in owner.ok(owner.get("/api/outputs"))["files"]}
    assert files["loose.md"]["for"] == "accounts/Northwind"


def test_a_task_handed_to_an_agent_starts_its_run_which_must_save_before_it_stops(owner, runtime):
    from workspace_server import anchoring

    owner.ok(
        owner.post(
            "/api/agents",
            json={
                "name": "accounts",
                "role": "Keeps the accounts sheet current.",
                "prompt": "You keep the account rows current.",
            },
        ),
        201,
    )
    owner.ok(owner.post("/api/work/handoffs", json={"new_task": {"title": "Refresh Northwind"}}))
    passed = owner.ok(
        owner.post(
            "/api/work/handoffs",
            json={
                "task": "T-1",
                "to": "agent:accounts",
                "done_when": "The row is current",
                "next_step": "Read the last call notes",
            },
        )
    )
    assert passed["run"]
    ws = runtime.ws
    run = ws.tasks.get(ws.owner(), passed["run"])
    assert "Pick up T-1" in run.instructions or "Pick up T-1" in str(run.provenance)
    contract = anchoring.build(ws, run, run_id="run-1", minutes=5, folder=None, tools=())
    assert any("hand_off" in check for check in contract["checks"])
    assert {"check": contract["finish"][1]["check"], "any": ["hand_off"]} in contract["finish"]


def test_a_sheet_on_a_goals_board_drives_its_progress(owner, runtime):
    page = owner.ok(
        owner.post(
            "/api/goals",
            json={"title": "Grow webinar attendance", "measure": {"kind": "enter", "target": 150}},
        ),
        201,
    )
    owner.ok(
        owner.post(
            "/api/work/live/act",
            json={
                "action": "create_sheet",
                "fields": {
                    "title": "Sign-ups",
                    "key": "Session",
                    "columns": [{"name": "Session"}, {"name": "Sign-ups", "type": "number"}],
                },
            },
        )
    )
    for session, count in (("October", 60), ("November", 70)):
        owner.ok(
            owner.post(
                "/api/work/live/act",
                json={
                    "action": "add_row",
                    "fields": {"sheet": "sign-ups", "key": session, "values": {"Sign-ups": count}},
                },
            )
        )
    board = page["board"]
    board["blocks"].append(
        {
            "type": "sheet",
            "title": "Sign-ups",
            "shared": True,
            "sheet_id": "sign-ups",
            "drives": "Sign-ups",
            "agg": "average",
        }
    )
    saved = owner.ok(
        owner.put(
            f"/api/goals/{page['id']}/board",
            json={"layout": board, "expected_version": board["version"]},
        )
    )
    assert saved["measure"]["signal"] == "sheet_column"
    assert saved["measure"]["target"] == 150
    assert "get_state" in saved["plan"]
    checks = owner.ok(owner.post("/api/goals/checks"))["checks"]
    mine = next(c for c in checks if c["goal"] == page["id"])
    assert mine["value"] == 65.0 and mine["status"] == "off_track"
