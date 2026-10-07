"""Reconciling two pieces of context: a person says which is current, a model rewrites the other
so both can stand, and the review shows its suggestion beside the pair."""

import pytest

from workspace_core.errors import NotFound, PermissionDenied, ValidationFailed


def figures(ws, who, **fields):
    fields.setdefault("statement", "We post on Tuesdays and Thursdays, at 9am.")
    fields.setdefault("evidence", "The new calendar")
    return ws.brain.propose(who, title="Posting times", **fields)


def test_a_reconcile_request_is_a_task_with_both_pieces(ws, owner, brain):
    made = figures(ws, owner)
    task = ws.distill.reconcile(
        owner, proposal_id=made.proposal_id, entry_id="voice-guide", current="proposal"
    )
    assert (task.template, task.status, task.assignee_id) == ("reconcile", "draft", None)
    assert task.title == "Reconcile “Voice guide” with “Posting times”"
    text = task.instructions
    assert "We post on Tuesdays and Thursdays, at 9am." in text  # the proposal, quoted
    assert 'revises="voice-guide"' in text
    assert task.provenance["reconcile"] == {
        "proposal_id": made.proposal_id,
        "entry_id": "voice-guide",
        "current": "proposal",
    }
    (pin,) = ws.tasks.pins(owner, task.id)
    assert (pin.ref_type, pin.ref_id) == ("brain_entry", "voice-guide")


def test_when_the_entry_is_current_the_proposal_is_rewritten(ws, owner, brain):
    made = figures(ws, owner)
    task = ws.distill.reconcile(
        owner,
        proposal_id=made.proposal_id,
        entry_id="voice-guide",
        current="entry",
        guidance="Keep the times.",
    )
    assert "revises=" not in task.instructions
    assert "Keep the times." in task.instructions
    assert "brain:voice-guide" in task.instructions


def test_a_model_can_be_named_to_reconcile(ws, owner, brain, connect):
    claude = connect()
    made = figures(ws, owner)
    task = ws.distill.reconcile(
        owner,
        proposal_id=made.proposal_id,
        entry_id="voice-guide",
        current="proposal",
        assignee_id=claude.actor_id,
    )
    assert (task.status, task.assignee_id) == ("ready", claude.actor_id)


def test_a_waiting_reconcile_request_goes_to_the_next_model(ws, owner, brain, connect):
    made = figures(ws, owner)
    task = ws.distill.reconcile(
        owner, proposal_id=made.proposal_id, entry_id="voice-guide", current="proposal"
    )
    claude = connect()
    (started,) = ws.distill.assign_waiting(ws.system())
    assert (started.id, started.assignee_id, started.status) == (task.id, claude.actor_id, "ready")


def test_reconciling_is_a_persons_call_about_real_pieces(ws, owner, brain, connect):
    claude = connect()
    made = figures(ws, owner)
    with pytest.raises(PermissionDenied):
        ws.distill.reconcile(
            claude, proposal_id=made.proposal_id, entry_id="voice-guide", current="proposal"
        )
    with pytest.raises(NotFound):
        ws.distill.reconcile(owner, proposal_id="nope", entry_id="voice-guide", current="entry")
    with pytest.raises(NotFound):
        ws.distill.reconcile(owner, proposal_id=made.proposal_id, entry_id="nope", current="entry")
    with pytest.raises(ValidationFailed):
        ws.distill.reconcile(
            owner, proposal_id=made.proposal_id, entry_id="voice-guide", current="both"
        )


def test_a_model_proposes_a_change_to_an_entry(ws, owner, brain, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    ws.brain.propose(
        claude,
        title="Voice guide",
        statement="Write plainly, and date every figure.",
        evidence="The new calendar",
        revises="voice-guide",
        run_id=run.id,
    )
    assert brain.proposed[-1]["revises"] == "voice-guide"
    (event,) = ws.events.activity(owner, types=["brain.proposed"])
    assert event.data["revises"] == "voice-guide"
    with pytest.raises(ValidationFailed):
        ws.brain.propose(
            claude,
            title="Both",
            statement="Text.",
            evidence="x",
            revises="voice-guide",
            replaces=["voice-guide"],
        )
    with pytest.raises(ValidationFailed):
        ws.brain.propose(claude, title="Bad", statement="Text.", evidence="x", revises="a b")


def test_the_review_shows_a_suggestion_beside_the_pair(ws, owner, brain, connect):
    claude = connect()
    made = figures(ws, owner)
    brain.analysis[made.proposal_id] = {"conflicts": [{"id": "voice-guide", "title": "Voice"}]}
    task = ws.distill.reconcile(
        owner,
        proposal_id=made.proposal_id,
        entry_id="voice-guide",
        current="proposal",
        assignee_id=claude.actor_id,
    )
    run = ws.bus.claim(claude, task.id).run
    suggestion = ws.brain.propose(
        claude,
        title="Voice guide",
        statement="Write plainly. Posting times live elsewhere.",
        evidence="Reconciled",
        revises="voice-guide",
        run_id=run.id,
    )
    review = ws.brain.review(owner)
    rows = {row["id"]: row for row in review.proposals}
    (reconciling,) = rows[made.proposal_id]["reconciliations"]
    assert reconciling["task_id"] == task.id and reconciling["current"] == "proposal"
    assert reconciling["entry_id"] == "voice-guide"
    assert reconciling["suggestion_ids"] == [suggestion.proposal_id]
    batch = next(b for b in review.batches if b.task_id == task.id)
    assert batch.reconciles == task.provenance["reconcile"]
