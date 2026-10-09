"""Workflows: steps run as one thing. A run walks its steps in order, each step's task pinned
with what the step before made; a check waits for the owner's yes or edit; upkeep is left for
the server and reported back; a run missed while the app was off starts once and says so; one
run of a workflow at a time; what the last step made can land in a Workspace doc."""

from datetime import timedelta

import pytest

from workspace_core.errors import Conflict, NotFound, ValidationFailed

POSTS = {"kind": "skill", "skill": "weekly-posts", "ask": "Three posts on the Tuesday polls."}
SUMMARY = {"kind": "prompt", "text": "Turn the pinned posts into one newsletter blurb."}


@pytest.fixture
def q4(brain):
    return brain.create_project(
        name="Q4 campaigns", summary="The fourth quarter", aliases=[], proposer="owner"
    )


def finish(ws, model, task_id, *, title="Made", text="It made this."):
    claim = ws.bus.claim(model, task_id)
    ws.skills.save_result(model, run_id=claim.run.id, title=title, text=text)
    ws.bus.complete(model, claim.run.id, summary="Done.")
    return claim


def current_task(ws, owner, run_id):
    run = ws.workflows.run_of(owner, run_id)
    return run.steps[run.step]["task_id"]


def test_a_workflow_is_checked_and_comes_due_on_its_schedule(ws, owner, q4):
    weekly = {"kind": "weekly", "days": ["mon"], "time": "09:00"}
    made = ws.workflows.save(
        owner, name="Weekly posts", schedule=weekly, steps=[POSTS], project=q4.id
    )
    # the clock reads Monday 09:00 in New York, so the next one is a week on
    assert made.next_due_at == "2026-10-05T13:00:00.000000Z"
    assert made.when == "Every Monday at 09:00 (America/New_York)"
    assert (made.revision, made.runner, made.output) == (1, "claude", {"kind": "outputs"})
    changed = ws.workflows.save(
        owner, workflow_id=made.id, name="Weekly posts", schedule=weekly, steps=[POSTS], ai=True
    )
    assert changed.revision == 2 and changed.when.endswith("or from any AI")
    off = ws.workflows.save(
        owner,
        workflow_id=made.id,
        name="Weekly posts",
        schedule=weekly,
        steps=[POSTS],
        enabled=False,
    )
    assert off.next_due_at is None
    with pytest.raises(ValidationFailed, match="at least one step"):
        ws.workflows.save(owner, name="Empty", steps=[])
    with pytest.raises(ValidationFailed, match="start with another step"):
        ws.workflows.save(owner, name="Check first", steps=[{"kind": "check"}, POSTS])
    with pytest.raises(ValidationFailed, match="not a connector tool"):
        ws.workflows.save(
            owner,
            name="Bad tool",
            steps=[{"kind": "connector", "ask": "x", "tools": ["mcp__hubspot"]}],
        )
    with pytest.raises(ValidationFailed, match="not a connector tool"):
        ws.workflows.save(
            owner,
            name="App tool",
            steps=[{"kind": "connector", "ask": "x", "tools": ["mcp__contxt-app__claim_task"]}],
        )
    with pytest.raises(ValidationFailed, match="upkeep step"):
        ws.workflows.save(
            owner, name="Bad upkeep", steps=[{"kind": "upkeep", "action": "delete-everything"}]
        )
    with pytest.raises(NotFound, match="No project"):
        ws.workflows.save(owner, name="Lost", steps=[POSTS], project="nope")


def test_a_run_walks_its_steps_and_pins_what_each_made(ws, owner, connect, q4):
    claude = connect()
    flow = ws.workflows.save(owner, name="Posts to blurb", steps=[POSTS, SUMMARY], project=q4.id)
    run = ws.workflows.run(owner, flow.id)
    assert (run.status, run.step, run.steps[0]["status"]) == ("running", 0, "running")
    first = finish(
        ws, claude, run.steps[0]["task_id"], title="Poll posts", text="Post one. Post two."
    )
    assert "This is for the project Q4 campaigns" in first.packet["instructions"]["text"]
    (start,) = ws.workflows.advance(owner)["start"]  # the server starts it on this computer
    run = ws.workflows.run_of(owner, run.id)
    assert start == {"run_id": run.id, "index": 1, "task_id": run.steps[1]["task_id"]}
    assert run.step == 1 and run.steps[0]["status"] == "done"
    assert run.steps[0]["result"]["title"] == "Poll posts"
    second = ws.bus.claim(claude, run.steps[1]["task_id"])
    (pinned,) = [i for i in second.packet["inputs"] if i["ref"].startswith("artifact:")]
    assert pinned["text"] == "Post one. Post two." and pinned["version"] == 1
    assert "The step before made “Poll posts”" in second.packet["instructions"]["text"]
    assert run.steps[1]["read"] == [{"ref": pinned["ref"], "version": 1}]
    ws.skills.save_result(claude, run_id=second.run.id, title="Blurb", text="Polls are back.")
    ws.bus.complete(claude, second.run.id, summary="Done.")
    ws.workflows.advance(owner)
    done = ws.workflows.run_of(owner, run.id)
    assert done.status == "done" and done.finished_at is not None
    assert ws.workflows.get(owner, flow.id).last_run["status"] == "done"
    (task_run,) = ws.skills.runs_where(
        owner, lambda about: (about.get("workflow") or {}).get("step") == 1
    )
    assert task_run["result"]["text"] == "Polls are back."


def test_a_check_waits_for_a_yes_or_an_edit(ws, owner, connect):
    claude = connect()
    check = {"kind": "check", "ask": "Read the posts first."}
    flow = ws.workflows.save(owner, name="Checked", steps=[POSTS, check, SUMMARY])
    run = ws.workflows.run(owner, flow.id)
    finish(ws, claude, run.steps[0]["task_id"], title="Poll posts", text="Post one.")
    ws.workflows.advance(owner)
    waiting = ws.workflows.run_of(owner, run.id)
    assert waiting.status == "waiting" and waiting.waiting["ask"] == "Read the posts first."
    assert waiting.waiting["result"]["title"] == "Poll posts"
    assert ws.workflows.step_result(owner, run.id, 0)["text"] == "Post one."
    with pytest.raises(NotFound):
        ws.workflows.step_result(owner, run.id, 1)
    assert [r.id for r in ws.workflows.waiting(owner)] == [run.id]
    with pytest.raises(Conflict):
        ws.workflows.run(owner, flow.id)  # one run at a time, waiting included
    went = ws.workflows.decide(owner, run.id, go=True, edit="Post one, shorter.")
    assert went.status == "running" and went.step == 2
    assert went.steps[1]["result"]["edited"] is True and went.steps[1]["result"]["version"] == 2
    third = ws.bus.claim(claude, went.steps[2]["task_id"])
    (pinned,) = [i for i in third.packet["inputs"] if i["ref"].startswith("artifact:")]
    assert (pinned["text"], pinned["version"]) == ("Post one, shorter.", 2)
    with pytest.raises(Conflict, match="not waiting"):
        ws.workflows.decide(owner, run.id, go=True)
    # another run, stopped at the check
    ws.workflows.stop(owner, run.id)
    again = ws.workflows.run(owner, flow.id)
    finish(ws, claude, again.steps[0]["task_id"])
    ws.workflows.advance(owner)
    stopped = ws.workflows.decide(owner, again.id, go=False, note="Not this week.")
    assert stopped.status == "stopped" and stopped.note == "Not this week."


def test_a_time_missed_while_off_runs_once_and_says_so(ws, owner, clock):
    weekly = {"kind": "weekly", "days": ["mon"], "time": "09:00"}
    flow = ws.workflows.save(owner, name="Weekly posts", schedule=weekly, steps=[POSTS])
    assert ws.workflows.start_due(owner) == []
    clock.advance(timedelta(days=21, hours=1, minutes=12))  # three Mondays missed
    (run,) = ws.workflows.start_due(owner)
    assert run.trigger == "schedule" and run.due_at == "2026-10-05T13:00:00.000000Z"
    assert run.note.startswith("Due Mon 09:00, ran Mon 10:12")
    assert ws.workflows.start_due(owner) == []  # no pile of missed runs
    later = ws.workflows.get(owner, flow.id)
    assert later.next_due_at == "2026-10-26T13:00:00.000000Z"
    clock.advance(timedelta(days=7))
    assert ws.workflows.start_due(owner) == []  # still going from last time: skipped
    assert ws.workflows.get(owner, flow.id).next_due_at == "2026-11-02T14:00:00.000000Z"


def test_runs_from_other_ais_only_when_allowed(ws, owner):
    flow = ws.workflows.save(owner, name="Weekly posts", steps=[POSTS])
    with pytest.raises(Conflict, match="does not run from other AIs"):
        ws.workflows.run(owner, flow.id, trigger="ai")
    ws.workflows.save(owner, workflow_id=flow.id, name="Weekly posts", steps=[POSTS], ai=True)
    run = ws.workflows.run(owner, flow.id, trigger="ai", request="Focus on the new poll.")
    assert run.trigger == "ai" and run.request == "Focus on the new poll."
    task = ws.tasks.get(owner, run.steps[0]["task_id"])
    assert "This run: Focus on the new poll." in task.instructions
    assert ws.workflows.find(owner, "weekly POSTS").id == flow.id


def test_upkeep_is_left_for_the_server_and_reported_back(ws, owner):
    flow = ws.workflows.save(
        owner, name="Upkeep then posts", steps=[{"kind": "upkeep", "action": "tidy-repeats"}, POSTS]
    )
    run = ws.workflows.run(owner, flow.id)
    assert run.steps[0]["status"] == "pending"
    todo = ws.workflows.advance(owner)
    assert todo["upkeep"] == [{"run_id": run.id, "index": 0, "action": "tidy-repeats"}]
    ws.workflows.upkeep_started(owner, run.id, 0, "ajob_1")
    running = ws.workflows.advance(owner)
    assert running["upkeep"] == [] and running["watch"] == [
        {"run_id": run.id, "index": 0, "job_id": "ajob_1"}
    ]
    moved = ws.workflows.upkeep_finished(
        owner, run.id, 0, ok=True, summary="2 repeats to merge, in Catch up."
    )
    assert moved.step == 1 and moved.steps[0]["result"] == {
        "text": "2 repeats to merge, in Catch up."
    }
    task = ws.tasks.get(owner, moved.steps[1]["task_id"])
    assert "The step before reported: 2 repeats to merge" in task.instructions
    flow2 = ws.workflows.save(
        owner, name="Upkeep alone", steps=[{"kind": "upkeep", "action": "freshen-up"}]
    )
    run2 = ws.workflows.run(owner, flow2.id)
    failed = ws.workflows.upkeep_finished(
        owner, run2.id, 0, ok=False, summary="The app restarted while it ran."
    )
    assert failed.status == "failed" and failed.note == "The app restarted while it ran."


def test_a_step_that_cannot_run_or_fails_ends_the_run(ws, owner, connect, brain):
    claude = connect()
    gone = ws.workflows.save(
        owner, name="Gone skill", steps=[{"kind": "skill", "skill": "vanished", "ask": "x"}]
    )
    run = ws.workflows.run(owner, gone.id)
    assert run.status == "failed" and "No skill vanished" in run.note
    flow = ws.workflows.save(owner, name="Cancelled", steps=[POSTS, SUMMARY])
    run = ws.workflows.run(owner, flow.id)
    ws.tasks.cancel(owner, run.steps[0]["task_id"])
    ws.workflows.advance(owner)
    assert ws.workflows.run_of(owner, run.id).status == "failed"
    nothing = ws.workflows.save(owner, name="Made nothing", steps=[POSTS])
    run = ws.workflows.run(owner, nothing.id)
    claim = ws.bus.claim(claude, run.steps[0]["task_id"])
    ws.bus.complete(claude, claim.run.id, summary="Nothing to say.")
    ws.workflows.advance(owner)
    ended = ws.workflows.run_of(owner, run.id)
    assert ended.status == "failed" and ended.steps[0]["note"] == "It finished without a result."


def test_the_last_result_lands_in_a_workspace_doc(ws, owner, connect, q4):
    claude = connect()
    doc = ws.docs.create(owner, title="Newsletter", projects=[q4.id])
    doc = ws.notes.save(owner, doc.id, body="Last week's blurb.")
    into = ws.workflows.save(
        owner, name="Blurb", steps=[POSTS], output={"kind": "workspace", "doc_id": doc.id}
    )
    run = ws.workflows.run(owner, into.id)
    finish(ws, claude, run.steps[0]["task_id"], title="Blurb", text="This week's blurb.")
    ws.workflows.advance(owner)
    assert ws.workflows.run_of(owner, run.id).note == "Kept as the next version of “Newsletter”."
    assert ws.notes.get(owner, doc.id).body == "This week's blurb."
    assert ws.notes.versions(owner, doc.id)[0].label == "From the workflow Blurb"
    fresh = ws.workflows.save(
        owner, name="Fresh doc", steps=[POSTS], project=q4.id, output={"kind": "workspace"}
    )
    run = ws.workflows.run(owner, fresh.id)
    finish(ws, claude, run.steps[0]["task_id"], title="Plan", text="The plan.")
    ws.workflows.advance(owner)
    made = next(n for n in ws.notes.list(owner) if n.title == "Fresh doc: Plan")
    assert made.body == "The plan." and made.projects == [q4.id]


def test_a_connector_step_names_its_tools_and_reads_only(ws, owner):
    tools = ["mcp__hubspot__search_crm_objects", "mcp__hubspot__get_crm_objects"]
    flow = ws.workflows.save(
        owner,
        name="Deals",
        steps=[{"kind": "connector", "ask": "This week's new deals.", "tools": tools}],
    )
    run = ws.workflows.run(owner, flow.id)
    task = ws.tasks.get(owner, run.steps[0]["task_id"])
    about = task.provenance["skill"]
    assert about["connector"] == {"tools": tools, "writes": False}
    assert "mcp__hubspot__search_crm_objects, mcp__hubspot__get_crm_objects" in task.instructions
    assert (
        "They read only." in task.instructions and "Never send, post, publish" in task.instructions
    )


def test_the_server_is_told_which_step_tasks_to_start_here(ws, owner):
    here = ws.workflows.save(owner, name="Here", steps=[POSTS])
    anywhere = ws.workflows.save(owner, name="Anywhere", steps=[POSTS], runner="any")
    run = ws.workflows.run(owner, here.id)
    ws.workflows.run(owner, anywhere.id)
    assert ws.workflows.advance(owner)["start"] == [
        {"run_id": run.id, "index": 0, "task_id": run.steps[0]["task_id"]}
    ]
    (listed,) = ws.workflows.runs(owner, workflow_id=here.id)
    assert listed.steps[0]["task_status"] == "draft"  # no model yet: it waits for one
    stopped = ws.workflows.stop(owner, run.id)
    assert stopped.status == "stopped"
    assert ws.tasks.get(owner, run.steps[0]["task_id"]).status == "cancelled"
    assert [w.name for w in ws.workflows.list(owner)] == ["Anywhere", "Here"]
    ws.workflows.archive(owner, anywhere.id)
    assert [w.name for w in ws.workflows.list(owner)] == ["Here"]
    with pytest.raises(Conflict, match="archived"):
        ws.workflows.run(owner, anywhere.id)


def test_a_check_waiting_for_the_owner_counts_in_catch_up(ws, owner, connect):
    claude = connect()
    flow = ws.workflows.save(
        owner, name="Checked posts", steps=[POSTS, {"kind": "check", "ask": "Read them."}]
    )
    run = ws.workflows.run(owner, flow.id)
    assert ws.catch_up.plan(owner)["counts"]["checks"] == 0
    finish(ws, claude, run.steps[0]["task_id"])
    ws.workflows.advance(owner)
    plan = ws.catch_up.plan(owner)
    (check,) = plan["work"]
    assert (check["run_id"], check["workflow"], check["ask"]) == (
        run.id,
        "Checked posts",
        "Read them.",
    )
    assert plan["counts"]["checks"] == 1 and plan["caught_up"] is False and plan["seconds"] >= 60
