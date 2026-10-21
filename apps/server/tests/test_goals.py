"""Goals and Projects over REST (goals plan G1), with a stand-in coach: set a goal with the
coach and see its draft page, check in, see a suggestion become an accepted step; only shared
board blocks reach an AI; a slipped agent goal makes exactly one Catch up card; without goals
nothing about them shows."""

import json
import time
from unittest import mock

from workspace_server.knowledge_agent import AgentWork
from workspace_server.models import ModelChoice, Models

CHOICES = [ModelChoice("claude", "Claude Code (your CLI)", "cli", True, "here", False)]


class StubModels(Models):
    """Answers from a list, and remembers what it was asked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def list(self):
        return list(CHOICES)

    def ask(self, who, choice, prompt, *, json_only=False, timeout=240.0, job="agent"):
        self.asked.append({"model": choice.id, "prompt": prompt, "json": json_only})
        return self.answers.pop(0)


def stub(runtime, *answers):
    models = StubModels(answers)
    runtime.models = models
    runtime.agent = AgentWork(runtime.ws, models)
    return models


def finish(owner, job_id, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = owner.ok(owner.get(f"/api/brain/agent/jobs/{job_id}"))
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def draft(**extra):
    found = {
        "title": "Grow webinar attendance to 150 a session",
        "why": "More qualified conversations.",
        "due": "2026-12-15",
        "cadence": "weekly",
        "measure": {"kind": "enter", "target": 150, "unit": "a session"},
        "board": {
            "wish": "150 people a session.",
            "outcome": "More qualified conversations.",
            "obstacle": "Promotion stalls after the first email.",
            "plan": "If sign-ups stall by week two, add a partner promo.",
        },
        "first_steps": ["Book 2 partner promos", "Follow up within 48 hours"],
        "project": "",
    }
    found.update(extra)
    return found


def test_without_goals_the_ladder_and_home_stay_quiet(owner):
    found = owner.ok(owner.get("/api/goals"))
    assert found["has_goals"] is False and found["yours"] == []
    home = owner.ok(owner.get("/api/goals/home"))
    assert home["check_ins"] == [] and home["agent_goals"] == [] and home["has_goals"] is False


def test_the_coach_asks_then_drafts_and_the_draft_becomes_a_goal_page(owner, runtime):
    models = stub(
        runtime,
        json.dumps({"questions": ["What would reaching it get you?", "What gets in the way?"]}),
        json.dumps({"draft": draft()}),
    )
    first = owner.ok(
        owner.post(
            "/api/goals/coach",
            json={"messages": [{"role": "you", "text": "150 people a session by December."}]},
        ),
        201,
    )
    asked = finish(owner, first["id"])
    assert asked["result"]["questions"][0] == "What would reaching it get you?"
    second = owner.ok(
        owner.post(
            "/api/goals/coach",
            json={
                "messages": [
                    {"role": "you", "text": "150 people a session by December."},
                    {"role": "coach", "text": " ".join(asked["result"]["questions"])},
                    {"role": "you", "text": "More conversations. Promotion stalls."},
                ]
            },
        ),
        201,
    )
    written = finish(owner, second["id"])["result"]["draft"]
    assert "write the draft now" in models.asked[1]["prompt"]
    page = owner.ok(owner.post("/api/goals", json=written), 201)
    assert page["title"] == "Grow webinar attendance to 150 a session"
    notes = {b["title"]: b for b in page["board"]["blocks"]}
    assert "Promotion stalls" in notes["Obstacles and plan"]["text"]
    assert [s["text"] for s in page["suggestions"]] == [
        "Book 2 partner promos",
        "Follow up within 48 hours",
    ]
    assert "Shared plan: notes_get" in page["context"]


def test_a_check_in_then_a_suggestion_becomes_a_step(owner, runtime):
    page = owner.ok(owner.post("/api/goals", json=draft()), 201)
    goal = page["id"]
    checked = owner.ok(
        owner.post(
            f"/api/goals/{goal}/check-in",
            json={"call": "on_track", "value": 71, "line": "Two partner promos booked"},
        )
    )
    assert (checked["status"], checked["now"]) == ("on_track", 71.0)
    step = page["suggestions"][0]
    after = owner.ok(
        owner.post(f"/api/goals/{goal}/suggestions/{step['id']}", json={"accept": True})
    )
    key_results = next(b for b in after["board"]["blocks"] if b["type"] == "checklist")
    assert key_results["items"][-1]["text"] == "T-1 Book 2 partner promos"
    assert "Book 2 partner promos" in after["plan"]
    no = after["suggestions"][0]
    later = owner.ok(
        owner.post(f"/api/goals/{goal}/suggestions/{no['id']}", json={"accept": False})
    )
    assert later["suggestions"] == []
    # A step you said no to never comes back.
    again = runtime.ws.goals.suggest(runtime.ws.owner(), goal, no["text"], source="test")
    assert again is False
    ladder = owner.ok(owner.get("/api/goals"))
    assert ladder["has_goals"] is True and ladder["yours"][0]["suggestions"] == 0
    bad = owner.post(f"/api/goals/{goal}/check-in", json={"call": "great"})
    assert bad.status_code == 422


def test_only_shared_blocks_reach_the_plan_an_ai_reads(owner, runtime):
    page = owner.ok(owner.post("/api/goals", json=draft(first_steps=[])), 201)
    goal = page["id"]
    layout = page["board"]
    layout["blocks"].append(
        {
            "type": "note",
            "title": "Scratch",
            "text": "Private thinking: call Dana.",
            "shared": False,
        }
    )
    saved = owner.ok(
        owner.put(
            f"/api/goals/{goal}/board",
            json={"layout": layout, "expected_version": layout["version"]},
        )
    )
    assert "Private thinking" not in saved["plan"]
    assert "partner promo" in saved["plan"]
    opened = runtime.brain.brain.note(goal).text
    assert "Private thinking" not in opened and "partner promo" in opened
    stale = owner.put(
        f"/api/goals/{goal}/board", json={"layout": layout, "expected_version": layout["version"]}
    )
    assert stale.status_code == 409
    wrong = owner.put(
        f"/api/goals/{goal}/board", json={"layout": {"blocks": [{"type": "spreadsheet"}]}}
    )
    assert wrong.status_code == 422


def test_a_slipped_agent_goal_makes_exactly_one_card(owner, runtime):
    from brainkit import measures

    ladder = owner.ok(owner.post("/api/goals/starters"))
    assert len(ladder["agents"]) == 4 and ladder["has_goals"] is False
    values = iter([0.0, 6.0, 6.0])
    with mock.patch.object(measures.SIGNALS["waiting"], "compute", lambda *_: next(values)):
        for _ in range(3):
            runtime.ws.goals.run_checks(runtime.ws.owner(), force=True)
            plan = owner.ok(owner.get("/api/brain/catch-up"))
            if _ == 0:
                assert plan["goals"] == []
        assert len(plan["goals"]) == 1
        assert plan["goals"][0]["goal"]["id"] == "goal-nothing-waits"
        assert "turned off track" in plan["goals"][0]["why"]
    home = owner.ok(owner.get("/api/goals/home"))
    assert [g["id"] for g in home["agent_goals"]] == ["goal-nothing-waits"]


def test_changing_and_pausing_a_goal_and_linking_a_project(owner):
    page = owner.ok(owner.post("/api/goals", json=draft(first_steps=[])), 201)
    goal = page["id"]
    project = owner.ok(
        owner.post(
            "/api/brain/projects",
            json={"name": "Q4 webinar series", "summary": "Three webinars."},
        ),
        201,
    )
    linked = owner.ok(owner.post(f"/api/goals/{goal}/projects", json={"project": project["id"]}))
    assert [p["id"] for p in linked["projects"]] == [project["id"]]
    paused = owner.ok(owner.patch(f"/api/goals/{goal}", json={"status": "paused"}))
    assert paused["status"] == "paused"
    refused = owner.post(f"/api/goals/{goal}/check-in", json={"call": "on_track"})
    assert refused.status_code == 422
    decided = owner.ok(
        owner.post(f"/api/goals/{goal}/decisions", json={"text": "Third session moves to Dec 3."})
    )
    assert decided["journal"][0]["kind"] == "decision"


def test_the_weekly_review_is_off_until_turned_on(owner):
    assert owner.ok(owner.get("/api/goals/settings")) == {"weekly_review": False}
    on = owner.ok(owner.put("/api/goals/settings", json={"weekly_review": True}))
    assert on == {"weekly_review": True}


def test_an_agents_goal_line_that_names_no_goal_is_offered_as_one(owner):
    role = {
        "name": "accounts",
        "role": "Keeps the accounts sheet current.",
        "goals": ["Every account row updated within 30 days", "the Brain's purpose"],
        "prompt": "You keep the account rows current.",
    }
    owner.ok(owner.post("/api/agents", json=role), 201)
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    lines = [n for n in plan["nudges"] if n["type"] == "agent_goal"]
    assert [n["line"] for n in lines] == ["Every account row updated within 30 days"]
    owner.ok(
        owner.post("/api/goals", json=draft(title="Every account row updated within 30 days")), 201
    )
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    assert not [n for n in plan["nudges"] if n["type"] == "agent_goal"]
