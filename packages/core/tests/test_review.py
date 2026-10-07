"""Reviewing the Brain's inbox as batches, deciding many at once, and undoing a batch."""

import pytest

from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.services.brain import display_name


def propose(ws, who, title, **fields):
    fields.setdefault("statement", f"{title}.")
    fields.setdefault("evidence", "The calendar")
    return ws.brain.propose(who, title=title, **fields)


def test_proposals_are_grouped_by_the_work_that_made_them(ws, owner, connect, make_task, brain):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    first = propose(ws, claude, "Posting days", run_id=run.id)
    second = propose(ws, claude, "Posting times", run_id=run.id)
    own = propose(ws, owner, "Tone for replies")
    brain.analysis[second.proposal_id] = {"overlaps": [{"id": "voice-guide", "close": True}]}
    review = ws.brain.review(owner)
    by_key = {b.key: b for b in review.batches}
    batch = by_key[f"task:{task.id}"]
    assert batch.title == task.title and batch.task_id == task.id
    assert batch.proposer == "Claude Code"
    assert batch.proposal_ids == [first.proposal_id, second.proposal_id]
    assert (batch.counts["total"], batch.counts["close"], batch.counts["clear"]) == (2, 1, 1)
    assert [b.proposal_ids for b in review.batches if b.task_id is None] == [[own.proposal_id]]
    rows = {row["id"]: row for row in review.proposals}
    assert rows[second.proposal_id]["analysis"]["overlaps"][0]["id"] == "voice-guide"


def test_a_batch_is_decided_at_once_and_saved_as_one_undo_point(ws, owner, brain):
    keep = propose(ws, owner, "Posting days")
    drop = propose(ws, owner, "Posting times")
    result = ws.brain.decide_many(
        owner,
        [
            {
                "action": "approve",
                "proposal_id": keep.proposal_id,
                "replaces": ["voice-guide"],
                "topic": "brand/voice",
                "title": "When we post",
            },
            {"action": "reject", "proposal_id": drop.proposal_id, "reason": "Covered"},
            {"action": "archive", "entry_id": "voice-guide", "reason": "Replaced"},
        ],
        label="Weekly review",
    )
    assert [r["ok"] for r in result["results"]] == [True, True, True]
    assert result["checkpoint"]["label"] == "Weekly review"
    (sent,) = brain.batches
    assert sent["decisions"][0] == {
        "action": "approve",
        "proposal_id": keep.proposal_id,
        "reason": "",
        "replaces": ["voice-guide"],
        "topic": "brand/voice",
        "title": "When we post",
    }
    types = [
        e.type
        for e in ws.events.activity(
            owner, types=["brain.approved", "brain.rejected", "brain.archived"]
        )
    ]
    assert sorted(types) == ["brain.approved", "brain.archived", "brain.rejected"]
    (archived,) = ws.events.activity(owner, types=["brain.archived"])
    assert archived.subject_id == "voice-guide" and archived.reason == "Replaced"
    assert archived.data["checkpoint"] == result["checkpoint"]["id"]


def test_a_proposal_and_an_entry_are_edited_in_the_same_batch(ws, owner, brain):
    made = propose(ws, owner, "Posting days")
    ws.brain.decide_many(
        owner,
        [
            {
                "action": "approve",
                "proposal_id": made.proposal_id,
                "body": "We post on Tuesdays.",
                "summary": "Posting days",
            },
            {
                "action": "edit",
                "entry_id": "voice-guide",
                "body": "Write plainly.",
                "title": "Voice",
                "reason": "Posting days live elsewhere",
            },
        ],
    )
    (sent,) = brain.batches
    assert sent["decisions"] == [
        {
            "action": "approve",
            "proposal_id": made.proposal_id,
            "reason": "",
            "body": "We post on Tuesdays.",
            "summary": "Posting days",
        },
        {
            "action": "edit",
            "entry_id": "voice-guide",
            "reason": "Posting days live elsewhere",
            "body": "Write plainly.",
            "title": "Voice",
        },
    ]
    (edited,) = ws.events.activity(owner, types=["brain.edited"])
    assert edited.subject_id == "voice-guide" and edited.reason == "Posting days live elsewhere"


def test_decisions_are_checked_before_anything_changes(ws, owner, brain):
    made = propose(ws, owner, "Posting days")
    for bad in (
        [{"action": "publish", "proposal_id": made.proposal_id}],
        [{"action": "approve"}],
        [{"action": "archive"}],
        [{"action": "approve", "proposal_id": made.proposal_id, "topic": "no slash"}],
        [{"action": "approve", "proposal_id": made.proposal_id, "body": "   "}],
        [{"action": "edit", "entry_id": "voice-guide"}],
        [{"action": "edit", "entry_id": "voice-guide", "body": "x" * 60001}],
        [],
    ):
        with pytest.raises(ValidationFailed):
            ws.brain.decide_many(owner, bad)
    assert brain.batches == []


def test_one_decision_is_a_batch_of_one(ws, owner, brain):
    made = propose(ws, owner, "Posting days")
    result = ws.brain.decide(owner, made.proposal_id, approve=True)
    assert result["status"] == "approved" and result["checkpoint"]["id"]
    with pytest.raises(NotFound):
        ws.brain.decide(owner, made.proposal_id, approve=True)


def test_only_a_person_decides_or_undoes(ws, owner, connect):
    claude = connect()
    made = propose(ws, claude, "Posting days")
    with pytest.raises(PermissionDenied):
        ws.brain.decide_many(claude, [{"action": "approve", "proposal_id": made.proposal_id}])
    point = ws.brain.decide_many(owner, [{"action": "approve", "proposal_id": made.proposal_id}])[
        "checkpoint"
    ]
    with pytest.raises(PermissionDenied):
        ws.brain.undo(claude, point["id"])


def test_an_undo_puts_the_batch_back_and_is_logged(ws, owner, brain):
    made = propose(ws, owner, "Posting days")
    point = ws.brain.decide_many(owner, [{"action": "approve", "proposal_id": made.proposal_id}])[
        "checkpoint"
    ]
    assert [p["id"] for p in ws.brain.proposals(owner)] == []
    undone = ws.brain.undo(owner, point["id"])
    assert undone["undone"] == point["id"]
    assert [p["id"] for p in ws.brain.proposals(owner)] == [made.proposal_id]
    (event,) = ws.events.activity(owner, types=["brain.undone"])
    assert (
        event.subject_id == point["id"] and event.data["checkpoint"] == undone["checkpoint"]["id"]
    )
    assert [c["id"] for c in ws.brain.checkpoints(owner)][:2] == [
        undone["checkpoint"]["id"],
        point["id"],
    ]
    with pytest.raises(Conflict):
        ws.brain.undo(owner, point["id"])
    with pytest.raises(NotFound):
        ws.brain.undo(owner, "cp-missing")


def test_a_proposal_says_what_it_replaces_contradicts_and_where_it_goes(ws, owner, brain):
    propose(
        ws,
        owner,
        "Posting days",
        replaces=["voice-guide"],
        contradicts=["old-days"],
        topic="brand/voice",
    )
    sent = brain.proposed[-1]
    assert (sent["replaces"], sent["contradicts"], sent["topic"]) == (
        ["voice-guide"],
        ["old-days"],
        "brand/voice",
    )
    with pytest.raises(ValidationFailed):
        propose(ws, owner, "Elsewhere", topic="voice")
    with pytest.raises(ValidationFailed):
        propose(ws, owner, "Self", replaces=["x"], contradicts=["x"])


def test_a_proposal_carries_one_line_of_summary(ws, owner, brain):
    propose(ws, owner, "Posting days", summary="  Which days   we post.\n")
    assert brain.proposed[-1]["summary"] == "Which days we post."
    propose(ws, owner, "Posting times")
    assert brain.proposed[-1]["summary"] is None  # the Brain writes one from the statement
    with pytest.raises(ValidationFailed):
        propose(ws, owner, "Posting rules", summary="word " * 50)


def test_a_proposer_reads_as_a_name():
    assert (
        display_name("model:Claude Code (this computer) (act_01)") == "Claude Code (this computer)"
    )
    assert display_name("human:Owner (act_02)") == "Owner"
    assert display_name("person:alex") == "person:alex"
    assert display_name("") == "Someone"
