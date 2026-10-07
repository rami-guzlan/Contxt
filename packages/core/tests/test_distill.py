"""Distillation: a model finds what will last in a person's notes and proposes it to the Brain."""

import pytest

from workspace_core.errors import NotFound, PermissionDenied, ValidationFailed


@pytest.fixture
def notes(ws, owner):
    return [
        ws.notes.create(owner, title="Posting days", body="We post Tue and Thu."),
        ws.notes.create(owner, title="Tone", body="Plain words, no hype."),
    ]


def test_a_request_is_a_ready_task_with_the_notes_pinned(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[n.id for n in notes], assignee_id=claude.actor_id)
    assert (task.template, task.status, task.review_policy) == ("distill", "ready", "auto")
    assert task.title == "Find what to remember in 2 notes"
    assert task.assignee_id == claude.actor_id
    assert "propose_brain_entry" in task.instructions and "run_id" in task.instructions
    assert "Posting days" in (task.brain_request or "")
    pins = ws.tasks.pins(owner, task.id)
    assert {(p.ref_id, p.pinned_version) for p in pins} == {(n.id, 1) for n in notes}


def test_a_request_names_one_note_by_its_title(ws, owner, notes, connect):
    task = ws.distill.request(owner, item_ids=[notes[0].id], assignee_id=connect().actor_id)
    assert task.title == "Find what to remember in Posting days"


def test_a_request_needs_something_to_read(ws, owner, notes, connect):
    claude = connect()
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[], assignee_id=claude.actor_id)
    with pytest.raises(NotFound):
        ws.distill.request(owner, item_ids=["ctx_missing"], assignee_id=claude.actor_id)
    empty = ws.notes.create(owner, title="Later")
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[empty.id], assignee_id=claude.actor_id)
    ws.notes.archive(owner, notes[1].id)
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[notes[1].id], assignee_id=claude.actor_id)


def test_the_model_is_chosen_for_you_when_there_is_one_answer(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id])
    assert task.assignee_id == claude.actor_id


def test_with_several_models_you_choose_or_configure_one(ws, owner, notes, connect):
    connect()
    codex = connect(name="Codex", provider="codex")
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[notes[0].id])
    ws.distill.configure(owner, assignee_id=codex.actor_id)
    assert ws.distill.settings(owner) == {"assignee_id": codex.actor_id}
    assert ws.distill.request(owner, item_ids=[notes[0].id]).assignee_id == codex.actor_id
    with pytest.raises(ValidationFailed):
        ws.distill.configure(owner, assignee_id=owner.actor_id)
    with pytest.raises(PermissionDenied):
        ws.distill.configure(codex, assignee_id=None)


def test_without_a_model_a_request_waits_for_the_first_one(ws, owner, notes, connect):
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[notes[0].id])
    task = ws.distill.request(owner, item_ids=[notes[0].id], wait=True)
    assert (task.status, task.assignee_id) == ("draft", None)
    (request,) = ws.distill.requests(owner)
    assert request.waiting
    claude = connect()
    (started,) = ws.distill.assign_waiting(ws.system())
    assert (started.id, started.status, started.assignee_id) == (task.id, "ready", claude.actor_id)


def test_guidance_and_the_note_reach_the_model(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id], guidance="Focus on the posting rules.")
    packet = ws.bus.claim(claude, task.id).packet
    assert "Focus on the posting rules." in packet["instructions"]["text"]
    (note,) = packet["inputs"]
    assert (note["title"], note["text"], note["type"]) == (
        "Posting days",
        "We post Tue and Thu.",
        "page",
    )


def test_a_request_runs_end_to_end_and_reports_its_proposals(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[n.id for n in notes])
    run = ws.bus.claim(claude, task.id).run
    first = ws.brain.propose(
        claude,
        title="Posting days",
        statement="We post on Tuesdays and Thursdays.",
        evidence="Posting days note",
        sources=[f"context_item:{notes[0].id}"],
        run_id=run.id,
    )
    ws.brain.propose(
        claude,
        title="Tone",
        statement="Plain words, no hype.",
        evidence="Tone note",
        sources=[f"context_item:{notes[1].id}"],
        run_id=run.id,
    )
    ws.bus.complete(claude, run.id, summary="Two durable statements")
    assert ws.tasks.get(owner, task.id).status == "done"
    ws.brain.decide(owner, first.proposal_id, approve=True)
    (request,) = ws.distill.requests(owner)
    assert (request.task_id, request.status) == (task.id, "done")
    assert request.items == [n.id for n in notes]
    assert request.summary == "Two durable statements"
    assert request.assignee_name == "Claude Code"
    assert [(p.title, p.status) for p in request.proposals] == [
        ("Posting days", "approved"),
        ("Tone", "pending"),
    ]


def test_requests_can_be_listed_for_one_note(ws, owner, notes, connect):
    claude = connect()
    one = ws.distill.request(owner, item_ids=[notes[0].id], assignee_id=claude.actor_id)
    ws.distill.request(owner, item_ids=[notes[1].id], assignee_id=claude.actor_id)
    assert [r.task_id for r in ws.distill.requests(owner, item_id=notes[0].id)] == [one.id]
    assert len(ws.distill.requests(owner)) == 2


def test_an_undone_approval_is_waiting_again(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id])
    run = ws.bus.claim(claude, task.id).run
    made = ws.brain.propose(
        claude,
        title="Posting days",
        statement="We post on Tuesdays.",
        evidence="note",
        run_id=run.id,
    )
    point = ws.brain.decide(owner, made.proposal_id, approve=True)["checkpoint"]
    assert ws.distill.requests(owner)[0].proposals[0].status == "approved"
    ws.brain.undo(owner, point["id"])
    assert ws.distill.requests(owner)[0].proposals[0].status == "pending"
