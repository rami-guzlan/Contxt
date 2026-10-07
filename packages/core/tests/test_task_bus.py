"""The pull-based task bus: models fetch, claim and complete only their own due work."""

from datetime import timedelta

import pytest

from workspace_core.errors import (
    Conflict,
    IdempotencyMismatch,
    InvalidTransition,
    LeaseLost,
    PermissionDenied,
    ValidationFailed,
    VersionConflict,
)


def test_a_model_sees_only_its_own_due_work(ws, connect, make_task, clock):
    claude, codex = connect("Claude Code"), connect("Codex", provider="codex")
    mine = make_task(claude)
    theirs = make_task(codex, title="Summarize the pipeline")
    make_task(claude, title="Still a draft", ready=False)
    make_task(claude, title="Tomorrow", schedule={"kind": "once", "at": "2026-09-29T09:00"})

    assert [t.id for t in ws.bus.due(claude).tasks] == [mine.id]
    assert [t.id for t in ws.bus.due(codex).tasks] == [theirs.id]

    clock.advance(timedelta(days=1, minutes=1))
    assert {t.title for t in ws.bus.due(claude).tasks} == {mine.title, "Tomorrow"}


def test_full_loop_claim_progress_artifact_complete_approve(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)

    claim = ws.bus.claim(claude, task.id)
    assert claim.run.status == "claimed" and claim.run.attempt == 1
    assert ws.tasks.get(owner, task.id).status == "claimed"
    packet = claim.packet
    assert packet["instructions"]["text"].startswith("Draft three posts")
    assert packet["purpose"]["project"]["title"] == "Content creation"
    assert "goal" not in packet["purpose"] and "project_memory" not in packet
    assert packet["brain"]["entry_ids"] == ["voice-guide"]
    assert packet["output_contract"] == {"artifacts": [{"type": "social_post", "count": 3}]}

    ws.bus.append(claude, claim.run.id, type="progress", message="Read the calendar")
    assert ws.tasks.get(owner, task.id).status == "in_progress"

    made = ws.artifacts.create(
        claude,
        run_id=claim.run.id,
        type="social_post",
        title="Post 1",
        content="AI leadership starts with judgment.",
    )
    assert made.artifact.status == "draft" and made.version.number == 1
    assert made.version.run_id == claim.run.id
    assert made.artifact.project_id == task.project_id

    approval = ws.approvals.request(
        claude,
        subject_type="artifact",
        subject_id=made.artifact.id,
        run_id=claim.run.id,
        reason="Ready for review",
    )
    assert ws.artifacts.get(owner, made.artifact.id).status == "in_review"

    run = ws.bus.complete(claude, claim.run.id, summary="Three drafts ready")
    assert run.status == "completed" and run.finished_at
    assert ws.tasks.get(owner, task.id).status == "review"

    ws.approvals.decide(owner, approval.id, decision="approved", note="Good")
    assert ws.artifacts.get(owner, made.artifact.id).status == "approved"
    assert ws.tasks.get(owner, task.id).status == "done"


def test_only_the_assignee_can_claim_and_the_first_lease_wins(ws, connect, make_task):
    claude, codex = connect("Claude Code"), connect("Codex", provider="codex")
    task = make_task(claude)
    with pytest.raises(PermissionDenied):
        ws.bus.claim(codex, task.id)
    ws.bus.claim(claude, task.id)
    with pytest.raises(Conflict) as info:
        ws.bus.claim(claude, task.id)
    assert "claimed" in str(info.value)


def test_a_retried_claim_with_the_same_key_returns_the_same_run(ws, connect, make_task):
    claude = connect()
    task = make_task(claude)
    first = ws.bus.claim(claude, task.id, idempotency_key="k1")
    again = ws.bus.claim(claude, task.id, idempotency_key="k1")
    assert again.run.id == first.run.id
    other = make_task(claude, title="Another")
    with pytest.raises(IdempotencyMismatch):
        ws.bus.claim(claude, other.id, idempotency_key="k1")


def test_an_expired_lease_frees_the_task_and_fences_the_old_run(
    ws, owner, connect, make_task, clock
):
    claude = connect()
    task = make_task(claude)
    old = ws.bus.claim(claude, task.id, lease_seconds=60).run
    clock.advance(timedelta(seconds=61))
    expired = ws.bus.expire_leases()
    assert [r.id for r in expired] == [old.id]
    assert ws.tasks.get(owner, task.id).status == "ready"
    with pytest.raises(LeaseLost):
        ws.bus.append(claude, old.id, type="progress", message="still here?")
    with pytest.raises(LeaseLost):
        ws.artifacts.create(claude, run_id=old.id, type="social_post", title="late", content="x")
    fresh = ws.bus.claim(claude, task.id).run
    assert fresh.attempt == 2 and fresh.id != old.id


def test_a_write_after_the_lease_ran_out_is_refused_even_before_the_sweep(
    ws, connect, make_task, clock
):
    claude = connect()
    run = ws.bus.claim(claude, make_task(claude).id, lease_seconds=60).run
    clock.advance(timedelta(seconds=90))
    with pytest.raises(LeaseLost):
        ws.bus.complete(claude, run.id, summary="done")


def test_heartbeat_renews_the_lease_quietly(ws, owner, connect, make_task, clock):
    claude = connect()
    run = ws.bus.claim(claude, make_task(claude).id, lease_seconds=60).run
    clock.advance(timedelta(seconds=50))
    ws.bus.append(claude, run.id, type="heartbeat")
    clock.advance(timedelta(seconds=50))
    assert ws.bus.expire_leases() == []
    renewed = ws.bus.run(claude, run.id)
    assert renewed.lease_expires_at > run.lease_expires_at
    assert all(e.type != "run.heartbeat" for e in ws.events.activity(owner))


def test_a_blocked_task_needs_a_person(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    with pytest.raises(ValidationFailed):
        ws.bus.append(claude, run.id, type="blocker", message="")
    ws.bus.append(claude, run.id, type="blocker", message="The calendar file is missing")
    assert ws.tasks.get(owner, task.id).status == "blocked"
    assert ws.bus.run(claude, run.id).status == "blocked"
    assert ws.bus.due(claude).tasks == []
    ws.tasks.mark_ready(owner, task.id)
    assert [t.id for t in ws.bus.due(claude).tasks] == [task.id]


def test_changes_requested_sends_the_task_back_with_the_note(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    made = ws.artifacts.create(
        claude, run_id=run.id, type="social_post", title="Post", content="Draft one"
    )
    approval = ws.approvals.request(
        claude, subject_type="artifact", subject_id=made.artifact.id, run_id=run.id
    )
    ws.bus.complete(claude, run.id, summary="done")
    ws.approvals.decide(
        owner, approval.id, decision="changes_requested", note="Lead with the event date"
    )
    assert ws.tasks.get(owner, task.id).status == "ready"
    second = ws.bus.claim(claude, task.id)
    assert second.run.attempt == 2
    assert second.packet["review_notes"] == [
        {
            "artifact_id": made.artifact.id,
            "decision": "changes_requested",
            "note": "Lead with the event date",
            "version": 1,
        }
    ]
    revised = ws.artifacts.create(
        claude,
        run_id=second.run.id,
        artifact_id=made.artifact.id,
        type="social_post",
        title="Post",
        content="Oct 14: draft two",
    )
    assert revised.version.number == 2 and revised.artifact.status == "draft"


def test_auto_review_completes_without_a_person(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude, review_policy="auto")
    run = ws.bus.claim(claude, task.id).run
    ws.bus.complete(claude, run.id, summary="Done")
    assert ws.tasks.get(owner, task.id).status == "done"


def test_a_failed_run_can_be_retried(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    ws.bus.complete(claude, run.id, summary="API was down", outcome="failed")
    assert ws.tasks.get(owner, task.id).status == "failed"
    ws.tasks.mark_ready(owner, task.id)
    assert ws.bus.claim(claude, task.id).run.attempt == 2


def test_a_recurring_task_comes_due_again(ws, owner, connect, make_task, clock):
    claude = connect()
    task = make_task(
        claude, schedule={"kind": "weekly", "days": ["mon"], "time": "09:00"}, review_policy="auto"
    )
    # Created and made ready at 09:00 exactly: the first occurrence is next Monday.
    assert ws.tasks.get(owner, task.id).next_due_at == "2026-10-05T13:00:00.000000Z"
    assert ws.bus.due(claude).tasks == []
    clock.advance(timedelta(days=7))
    run = ws.bus.claim(claude, task.id).run
    assert run.occurrence == "2026-10-05T13:00:00.000000Z"
    ws.bus.complete(claude, run.id, summary="Week 1 done")
    done = ws.tasks.get(owner, task.id)
    assert done.status == "done" and done.next_due_at == "2026-10-12T13:00:00.000000Z"
    assert ws.bus.due(claude).tasks == []
    clock.advance(timedelta(days=7))
    assert [t.id for t in ws.bus.due(claude).tasks] == [task.id]
    second = ws.bus.claim(claude, task.id).run
    assert second.occurrence == "2026-10-12T13:00:00.000000Z" and second.attempt == 1


def test_packets_are_deterministic_for_the_run(ws, owner, connect, make_task, project):
    claude = connect()
    calendar = ws.context.capture(
        owner,
        scope=f"project:{project.id}",
        kind="note",
        title="Content calendar",
        body="Oct 14: webinar",
    )
    task = make_task(claude, ready=False)
    ws.tasks.pin(owner, task.id, ref_type="context_item", ref_id=calendar.id)
    ws.tasks.pin(owner, task.id, ref_type="brain_entry", ref_id="voice-guide")
    ws.tasks.mark_ready(owner, task.id)
    claim = ws.bus.claim(claude, task.id)
    inputs = {i["ref"]: i for i in claim.packet["inputs"]}
    assert inputs[f"context_item:{calendar.id}"]["version"] == 1
    assert inputs[f"context_item:{calendar.id}"]["text"] == "Oct 14: webinar"
    assert inputs["brain_entry:voice-guide"]["text"] == "Write plainly. No hype."

    ws.context.update(owner, calendar.id, body="Oct 14: webinar moved to Oct 21")
    assert ws.bus.packet(claude, run_id=claim.run.id) == claim.packet
    made = ws.artifacts.create(
        claude,
        run_id=claim.run.id,
        type="social_post",
        title="Post",
        content="x",
        context_used=[f"context_item:{calendar.id}"],
    )
    assert made.version.inputs[0]["ref"] == f"context_item:{calendar.id}"
    assert made.version.inputs[0]["version"] == 1
    assert made.version.context_used == [{"ref": f"context_item:{calendar.id}"}]
    preview = ws.tasks.preview_packet(owner, task.id)
    assert {i["ref"]: i for i in preview["inputs"]}[f"context_item:{calendar.id}"]["version"] == 2


def test_a_model_cannot_decide_or_reach_other_projects(ws, owner, connect, make_task, project):
    other = ws.projects.create(owner, title="Private project")
    scoped = connect("Scoped", projects=[other.id])
    claude = connect()
    task = make_task(claude)
    with pytest.raises(PermissionDenied):
        ws.tasks.get(scoped, task.id)
    with pytest.raises(ValidationFailed):  # work it could never claim is refused up front
        make_task(scoped)
    run = ws.bus.claim(claude, task.id).run
    made = ws.artifacts.create(claude, run_id=run.id, type="social_post", title="P", content="x")
    approval = ws.approvals.request(
        claude, subject_type="artifact", subject_id=made.artifact.id, run_id=run.id
    )
    with pytest.raises(PermissionDenied):
        ws.approvals.decide(claude, approval.id, decision="approved")


def test_stale_edits_are_refused(ws, owner, connect, make_task):
    task = make_task(connect(), ready=False)
    ws.tasks.update(owner, task.id, expected_version=task.version, title="New title")
    with pytest.raises(VersionConflict):
        ws.tasks.update(owner, task.id, expected_version=task.version, title="Older edit")


def test_editing_the_prompt_bumps_its_version_and_keeps_history(ws, owner, connect, make_task):
    task = make_task(connect(), ready=False)
    edited = ws.tasks.update(owner, task.id, instructions="Draft two posts instead.")
    assert edited.prompt_version == 2 and edited.revision == 2
    retitled = ws.tasks.update(owner, task.id, title="Renamed")
    assert retitled.prompt_version == 2 and retitled.revision == 3
    history = ws.tasks.revisions(owner, task.id)
    assert [h["revision"] for h in history] == [1, 2, 3]
    assert history[0]["definition"]["instructions"].startswith("Draft three posts")


def test_only_listed_transitions_happen(ws, owner, connect, make_task):
    task = make_task(connect(), ready=False)
    with pytest.raises(InvalidTransition):
        ws.tasks.complete_review(owner, task.id)


def test_every_consequential_write_names_its_actor(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    ws.bus.complete(claude, run.id, summary="ok")
    events = ws.events.activity(owner)
    claimed = next(e for e in events if e.type == "task.claimed")
    assert claimed.actor_id == claude.actor_id
    created = next(e for e in events if e.type == "task.created")
    assert created.actor_id == owner.actor_id
    # Polling is recorded for "last seen", but hidden from the activity view by default.
    ws.bus.due(claude)
    assert all(not e.noise for e in ws.events.activity(owner))
    assert any(e.type == "bus.polled" for e in ws.events.activity(owner, include_noise=True))
