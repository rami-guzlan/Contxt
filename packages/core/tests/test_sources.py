"""Every capture says where it stands, from captured to searchable, with excluded and failed
beside them (Release 1 plan, M03). Kept is not searchable until the Brain's index holds it."""

import pytest

from workspace_core.errors import ValidationFailed


@pytest.fixture
def note(ws, owner):
    return ws.notes.create(owner, title="Kickoff call", body="Dana said yes for the twelfth.")


def _status(ws, owner, note):
    return ws.sources.status(owner, [note.id])[note.id]


def _proposes(ws, claude, run, note, *titles):
    return [
        ws.brain.propose(
            claude,
            title=title,
            statement=f"{title}.",
            evidence="kickoff call",
            sources=[f"context_item:{note.id}"],
            run_id=run.id,
        )
        for title in titles
    ]


def test_a_new_capture_is_captured_and_then_analysis_pending(ws, owner, note, connect):
    claude = connect()
    found = _status(ws, owner, note)
    assert (found.status, found.stage) == ("captured", "captured")
    ws.distill.request(owner, item_ids=[note.id], assignee_id=claude.actor_id)
    assert _status(ws, owner, note).status == "analysis_pending"


def test_proposals_wait_then_kept_is_indexing_until_the_index_holds_it(
    ws, owner, note, connect, brain
):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[note.id], assignee_id=claude.actor_id)
    run = ws.bus.claim(claude, task.id).run
    kept, skipped = _proposes(ws, claude, run, note, "Dana confirmed", "Lunch plans")
    ws.bus.complete(claude, run.id, summary="Two pieces")
    found = _status(ws, owner, note)
    assert (found.status, found.waiting) == ("awaiting_review", 2)
    brain.not_indexed.add(kept.proposal_id)
    ws.brain.decide(owner, kept.proposal_id, approve=True)
    ws.brain.decide(owner, skipped.proposal_id, approve=False)
    found = _status(ws, owner, note)
    assert (found.status, found.kept, found.skipped) == ("indexing", 1, 1)
    assert "not searchable yet" in found.label
    brain.not_indexed.clear()
    found = _status(ws, owner, note)
    assert (found.status, found.searchable) == ("searchable", 1)


def test_a_run_that_keeps_nothing_says_so(ws, owner, note, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[note.id], assignee_id=claude.actor_id)
    run = ws.bus.claim(claude, task.id).run
    ws.bus.complete(claude, run.id, summary="Nothing durable")
    assert _status(ws, owner, note).status == "nothing_kept"


def test_a_failed_run_says_why_and_a_retry_keeps_the_same_model(ws, owner, note, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[note.id], assignee_id=claude.actor_id)
    run = ws.bus.claim(claude, task.id).run
    ws.bus.complete(claude, run.id, summary="Claude Code did not respond", outcome="failed")
    found = _status(ws, owner, note)
    assert (found.status, found.can_retry) == ("failed", True)
    assert "did not respond" in found.detail
    again = ws.sources.retry(owner, note.id)
    assert again.assignee_id == claude.actor_id
    assert _status(ws, owner, note).status == "retrying"


def test_an_excluded_capture_stays_out_until_it_is_included(ws, owner, note, connect):
    ws.sources.exclude(owner, note.id, reason="Personal: never kept")
    found = _status(ws, owner, note)
    assert (found.status, found.detail) == ("excluded", "Personal: never kept")
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[note.id], assignee_id=connect().actor_id)
    ws.sources.include(owner, note.id)
    assert _status(ws, owner, note).status == "captured"


def test_reading_again_after_a_failed_transcription_says_to_retry_the_transcription(
    ws, owner, note
):
    from workspace_core.db import schema
    from workspace_core.errors import Conflict

    with ws.rt.write() as tx:  # as the speech worker leaves a transcription that failed
        row = tx.one(schema.context_items, note.id, "note")
        tx.update(schema.context_items, row, {"shadow_status": "failed"})
    assert ws.sources.status(owner, [note.id])[note.id].status == "failed"
    with pytest.raises(Conflict, match="transcription"):
        ws.sources.retry(owner, note.id)
