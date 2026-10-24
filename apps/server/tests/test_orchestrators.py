"""Agent orchestrators (AGENTS.md 8b), with a fake runner: no real CLI starts. Each "launch"
gives the task to a connected model with a credential made for that run alone, and the test
plays each CLI through the app's MCP endpoint, as Claude Code would."""

import pytest

POST = "mcp__buffer__create_post"
LIST = "mcp__buffer__list_posts"


class FakeRunner:
    """Starts nothing: records the launch and readies a credential bound to the task."""

    def __init__(self, runtime, owner, actor_id, project_id):
        self.runtime, self.owner = runtime, owner
        self.actor_id, self.project_id = actor_id, project_id
        self.launches = []

    def __call__(self, owner, runner, task_id, model):
        ws = self.runtime.ws
        ws.tasks.update(owner, task_id, assignee_id=self.actor_id)
        ws.tasks.mark_ready(owner, task_id)
        made = ws.actors.issue_token(
            owner, self.actor_id, label=f"Run of {task_id}", projects=[self.project_id]
        )
        self.runtime.runners.contracts.register(
            made.credential.id, {"task": task_id, "objective": "A run", "must_holds": []}
        )
        task = ws.tasks.get(owner, task_id)
        self.launches.append(
            {
                "runner": runner,
                "model": model,
                "task": task,
                "cli": type(self.owner)(self.owner.client, made.token),
            }
        )
        return {"state": "working"}

    def cli(self, n):
        """The nth CLI started, with its claim made: (api, bus run id, task)."""
        launch = self.launches[n]
        api = launch["cli"]
        claimed = api.tool("claim_task", task_id=launch["task"].id)
        assert not claimed["isError"], claimed
        return api, claimed["structuredContent"]["run"]["id"], launch["task"]


def ok(result):
    assert not result["isError"], result["content"][0]["text"]
    return result["structuredContent"]


@pytest.fixture
def brain_project(runtime):
    return runtime.ws.rt.brain.projects()[0].id


@pytest.fixture
def fake(owner, runtime, model, brain_project):
    runtime.ws.agents.save(runtime.ws.owner(), "ads-analyst", {"role": "Reads paid results."}, "")
    pid = owner.client.app.state.orchestration.project_id(
        runtime.ws.owner(), brain_project, make=True
    )
    runner = FakeRunner(runtime, owner, model.actor_id, pid)
    owner.client.app.state.orchestration.launch = runner
    return runner


def make(owner, brain_project):
    return owner.ok(
        owner.post(
            f"/api/projects/{brain_project}/orchestrators",
            json={
                "name": "Carousel pipeline",
                "goal": "Make a carousel and queue it for Tuesday.",
                "cli": "claude",
                "model": "opus",
                "trigger": "ai",
                "agents": [
                    {
                        "id": "a1",
                        "profile": "ads-analyst",
                        "role": "Owns paid performance. Reads last week's spend.",
                        "works_by": "files",
                        "model": "sonnet",
                    },
                    {
                        "id": "a2",
                        "profile": "Publisher",
                        "new_profile": True,
                        "role": "Owns publishing. Queues the final PDF on Buffer.",
                        "works_by": "mcp",
                        "model": "haiku",
                        "tools": [LIST, POST],
                    },
                ],
            },
        ),
        201,
    )


def test_saving_an_orchestrator_saves_a_new_profile_to_agents(owner, fake, brain_project):
    saved = make(owner, brain_project)
    assert saved["slug"] == "carousel-pipeline"
    assert saved["sheet"] == "Carousel pipeline · sheet"
    assert [a["profile"] for a in saved["agents"]] == ["ads-analyst", "publisher"]
    assert saved["agents"][0]["short"] == "paid performance"
    assert any(a["name"] == "publisher" for a in owner.ok(owner.get("/api/agents")))
    listed = owner.ok(owner.get(f"/api/projects/{brain_project}/orchestrators"))
    assert [o["id"] for o in listed["orchestrators"]] == [saved["id"]]
    assert {c["id"] for c in listed["clis"]} == {"claude", "codex", "gemini"}
    refused = owner.post(
        f"/api/projects/{brain_project}/orchestrators",
        json={"name": "X", "agents": [{"profile": "nobody-here", "role": "Owns it."}]},
    )
    assert refused.status_code == 422 and "Pick one, or create it here" in refused.text


def test_a_run_spawns_agents_fills_its_sheet_pins_a_final_and_waits_at_the_gate(
    owner, fake, brain_project
):
    base = f"/api/projects/{brain_project}/orchestrators"
    orc = make(owner, brain_project)
    run = owner.ok(owner.post(f"{base}/{orc['id']}/run", json={"steer": "focus on paid"}), 201)
    assert run["status"] == "running" and run["steer"] == "focus on paid"
    assert [(x["runner"], x["model"]) for x in fake.launches] == [("claude", "opus")]
    assert fake.launches[0]["task"].template == "orchestrator"

    # The orchestrator plans and spawns each agent on its own CLI and model.
    boss, boss_run, _ = fake.cli(0)
    seen = ok(boss.tool("orchestrators_context", run_id=run["id"]))
    assert seen["steer"] == "focus on paid" and [a["id"] for a in seen["agents"]] == ["a1", "a2"]
    for agent_id in ("a1", "a2"):
        ok(boss.tool("orchestrators_spawn", run_id=run["id"], agent_id=agent_id, brief="Go."))
    assert [x["model"] for x in fake.launches] == ["opus", "sonnet", "haiku"]
    # The publisher may read Buffer, but its own run never gets the tool that posts.
    publisher_task = fake.launches[2]["task"]
    assert publisher_task.provenance["skill"]["connector"]["tools"] == [LIST]

    # An agent cannot act as the orchestrator.
    analyst, analyst_run, _ = fake.cli(1)
    refused = analyst.tool("orchestrators_spawn", run_id=run["id"], agent_id="a2")
    assert refused["isError"] and "orchestrator" in refused["content"][0]["text"]

    mine = ok(analyst.tool("orchestrators_agent_context", run_id=run["id"], agent_id="a1"))
    assert mine["brief"] == "Go." and mine["role"].startswith("Owns paid performance")
    out = ok(
        analyst.tool(
            "outputs_save", run_id=analyst_run, title="Spend, Oct 13 to 19", text="# Spend\n$412."
        )
    )
    ok(
        analyst.tool(
            "orchestrators_report",
            run_id=run["id"],
            agent_id="a1",
            output_id=out["output_id"],
            summary="Spend $412 last week.",
            sources=["Campaign export.csv"],
        )
    )

    # The publisher asks to post: the run stops at the gate, and nothing is posted.
    publisher, publisher_run, _ = fake.cli(2)
    out2 = ok(
        publisher.tool(
            "outputs_save", run_id=publisher_run, title="Buffer draft", text="Ready to queue."
        )
    )
    gated = ok(
        publisher.tool(
            "orchestrators_report",
            run_id=run["id"],
            agent_id="a2",
            output_id=out2["output_id"],
            summary="Ready to queue for Tuesday 9:00.",
            sources=["Buffer · via MCP"],
            action={
                "kind": "other",
                "what": "Post the carousel to LinkedIn through Buffer on Tuesday 9:00",
                "tools": [POST],
                "approve_label": "Yes, post it",
            },
        )
    )
    assert gated["status"] == "needs_user_confirmation"
    assert gated["gate"]["kind"] == "post" and gated["gate"]["status"] == "pending"
    assert gated["run"]["status"] == "waiting"
    assert len(fake.launches) == 3  # nothing started that could post

    # The orchestrator fills its sheet (every cell with its source and agent) and finishes.
    no_source = boss.tool(
        "orchestrators_sheet_fill",
        run_id=run["id"],
        rows=[{"what": "Spend", "value": "$412", "source": "", "agent": "a1"}],
    )
    assert no_source["isError"] and "needs its source" in no_source["content"][0]["text"]
    ok(
        boss.tool(
            "orchestrators_sheet_fill",
            run_id=run["id"],
            rows=[
                {
                    "what": "Spend, last 7 days",
                    "value": "$412",
                    "source": "Campaign export.csv",
                    "agent": "a1",
                },
                {
                    "what": "Scheduled",
                    "value": "Tue 9:00",
                    "source": "Buffer · via MCP",
                    "agent": "publisher",
                },
            ],
        )
    )
    final = ok(
        boss.tool(
            "outputs_save",
            run_id=boss_run,
            title="Carousel queued for Tuesday",
            text="# Final\nAll set.",
        )
    )
    done = ok(
        boss.tool(
            "orchestrators_finish",
            run_id=run["id"],
            final_output_id=final["output_id"],
            summary="Spend is fine; the carousel waits for your yes to post.",
        )
    )
    assert done["status"] == "waiting"

    # The page: agent tasks apart from the person's, the sheet, Outputs and the timeline.
    page = owner.ok(owner.get(base))
    tasks = page["agent_tasks"]
    assert [(t["kind"], t["state"]) for t in tasks] == [
        ("agent", "reported"),
        ("agent", "reported"),
        ("orchestrator", "waiting"),
    ]
    (sheet,) = owner.ok(owner.get(f"{base}/sheets"))
    assert sheet["name"] == "Carousel pipeline · sheet"
    assert sorted((c["what"], c["agent"]) for c in sheet["cells"]) == [
        ("Scheduled", "publisher"),
        ("Spend, last 7 days", "ads-analyst"),
    ]
    (grouped,) = owner.ok(owner.get(f"{base}/outputs"))
    assert grouped["final"]["output_id"] == final["output_id"]
    assert grouped["final"]["sources"] == ["Campaign export.csv", "Buffer · via MCP"]
    assert [t["output_id"] for t in grouped["trail"]] == [out["output_id"], out2["output_id"]]
    kinds = [e["kind"] for e in owner.ok(owner.get(f"{base}/timeline"))]
    for kind in ("plan", "spawn", "report", "sheet", "final", "approval"):
        assert kind in kinds, kinds

    # A connected AI cannot say yes for the owner; the owner's yes starts the run that posts.
    gate = grouped["gates"][0]
    assert (
        boss.post(
            f"{base}/runs/{run['id']}/gates/{gate['id']}", json={"decision": "approve"}
        ).status_code
        == 403
    )
    decided = owner.ok(
        owner.post(
            f"{base}/runs/{run['id']}/gates/{gate['id']}",
            json={"decision": "approve", "quote": "Yes, post it"},
        )
    )
    assert decided["run"]["status"] == "done"
    assert decided["gate"]["status"] == "approved" and decided["gate"]["quote"] == "Yes, post it"
    assert len(fake.launches) == 4
    act = fake.launches[3]["task"]
    assert POST in act.provenance["skill"]["connector"]["tools"]
    assert "Post the carousel to LinkedIn" in act.instructions
    assert any(
        e["text"].startswith("You approved") for e in owner.ok(owner.get(f"{base}/timeline"))
    )


def test_a_connected_ai_starts_the_same_run_by_slug_with_a_steer(model, owner, fake, brain_project):
    make(owner, brain_project)
    started = ok(
        model.tool(
            "orchestrators_run",
            project=brain_project,
            orchestrator="carousel-pipeline",
            steer="focus on paid",
        )
    )
    assert started["trigger"] == "ai" and started["steer"] == "focus on paid"
    (line,) = owner.ok(owner.get(f"/api/projects/{brain_project}/orchestrators"))["orchestrators"]
    assert line["latest_run"]["id"] == started["id"]
    unconfirmed = model.tool("orchestrators_save", project=brain_project, spec={"name": "Another"})
    assert unconfirmed["isError"] and "confirmed_by_user" in unconfirmed["content"][0]["text"]


def test_a_cli_that_cannot_start_stops_the_run_with_why(owner, fake, brain_project):
    orc = make(owner, brain_project)
    owner.client.app.state.orchestration.launch = lambda *a: {
        "state": "waiting",
        "note": "Claude Code is not installed on this computer.",
    }
    run = owner.ok(
        owner.post(f"/api/projects/{brain_project}/orchestrators/{orc['id']}/run", json={}), 201
    )
    assert run["status"] == "stopped" and "not installed" in run["note"]


def test_only_a_tool_whose_name_plainly_reads_is_in_an_agents_own_run():
    from workspace_core.services.orchestrators import acts

    for reads in ("list_posts", "mcp__hubspot__get_campaign", "search_messages", "read_file"):
        assert not acts(reads), reads
    for could_act in (
        "create_post",
        "read_and_delete",
        "get_or_send",
        "submit_order",
        "approve_invoice",
        "launch_campaign",
        "mcp__slack__chat",
        "",
    ):
        assert acts(could_act), could_act
