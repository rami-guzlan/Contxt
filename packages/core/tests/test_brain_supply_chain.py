"""The workspace's part of the context supply chain: AI work counts the Brain entries it is
handed, and outputs record the version of each. Governing an entry (restore, bring back,
details, a mark that it needs an update, policy) is a decision."""

import pytest

from workspace_core.errors import NotFound, PermissionDenied, ValidationFailed


def _output(ws, model, task_id, title="Launch email"):
    claim = ws.bus.claim(model, task_id)
    made = ws.artifacts.create(
        model, run_id=claim.run.id, type="document", title=title, content="Hello."
    )
    return claim, made.artifact


def test_ai_work_counts_the_entries_it_is_handed(ws, connect, make_task, brain):
    claude = connect()
    task = make_task(claude)
    claim = ws.bus.claim(claude, task.id)
    assert claim.packet["brain"]["entries"] == [{"id": "voice-guide", "hash": "h1", "tokens": 6}]
    assert brain.used == [(claim.run.id, [{"id": "voice-guide", "hash": "h1", "tokens": 6}])]


def test_counting_never_stands_in_the_way_of_the_work(ws, connect, make_task, brain):
    def broken(ref, entries):
        raise RuntimeError("ledger locked")

    brain.record_use = broken
    claude = connect()
    claim = ws.bus.claim(claude, make_task(claude).id)
    assert claim.run.status == "claimed"


def test_an_output_records_the_version_of_each_entry_it_was_built_on(ws, owner, connect, make_task):
    claude = connect()
    _claim, artifact = _output(ws, claude, make_task(claude).id)
    (version,) = ws.artifacts.versions(owner, artifact.id)
    assert {"ref": "brain_entry:voice-guide", "version": None, "content_hash": "h1"} in (
        version.inputs
    )


def test_an_entrys_use_names_the_ai_work_it_went_to(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude, title="Draft the newsletter")
    claim = ws.bus.claim(claude, task.id)
    use = ws.brain.use(owner, "voice-guide")
    (row,) = use["recent"]
    assert row["work"]["run_id"] == claim.run.id
    assert (row["work"]["title"], row["work"]["actor"]) == ("Draft the newsletter", "Claude Code")


def test_restore_bring_back_and_details_are_decisions_with_events(ws, owner, brain):
    result = ws.brain.decide_many(
        owner,
        [
            {"action": "restore", "entry_id": "voice-guide", "ref": "abc1234"},
            {"action": "update", "entry_id": "voice-guide", "fields": {"owner": "person:sam"}},
            {"action": "unarchive", "entry_id": "voice-guide", "reason": "still true"},
        ],
    )
    assert [r["ok"] for r in result["results"]] == [True, True, True]
    sent = brain.batches[-1]["decisions"]
    assert sent[0]["ref"] == "abc1234"
    assert sent[1]["fields"] == {"owner": "person:sam"}
    events = [e.type for e in ws.events.activity(owner, subject_id="voice-guide")]
    assert {"brain.restored", "brain.updated", "brain.unarchived"} <= set(events)


@pytest.mark.parametrize(
    ("decision", "field"),
    [
        ({"action": "restore", "entry_id": "voice-guide"}, "ref"),
        ({"action": "restore", "entry_id": "voice-guide", "ref": "../etc"}, "ref"),
        ({"action": "update", "entry_id": "voice-guide", "fields": {}}, "fields"),
        ({"action": "update", "entry_id": "voice-guide", "fields": {"status": "x"}}, "fields"),
        ({"action": "unarchive"}, "entry_id"),
    ],
)
def test_entry_decisions_say_what_they_need(ws, owner, decision, field):
    with pytest.raises(ValidationFailed) as raised:
        ws.brain.decide_many(owner, [decision])
    assert raised.value.details.get("field") == field


def test_only_a_person_governs_and_any_reader_sees_the_supply_chain(ws, owner, connect, brain):
    claude = connect()
    assert ws.brain.inventory(owner)[0]["id"] == "voice-guide"
    assert ws.brain.versions(owner, "voice-guide")[0]["ref"] == "current"
    assert ws.brain.version(owner, "voice-guide", "abc1234")["body"] == "Write plainly. No hype."
    assert ws.brain.activity(owner)[0]["action"] == "approved"
    assert ws.brain.flow(owner)["days"] == 7
    assert ws.brain.gaps(owner)[0]["kind"] == "nothing"
    with pytest.raises(NotFound):
        ws.brain.version(owner, "voice-guide", "zzz9999")
    with pytest.raises(PermissionDenied):
        ws.brain.dismiss_gap(claude, "packet:p1")
    with pytest.raises(PermissionDenied):
        ws.brain.set_policies(claude, {"retention_days": 30})
    ws.brain.dismiss_gap(owner, "packet:p1")
    assert ws.brain.gaps(owner) == []


def test_policy_changes_are_recorded(ws, owner, brain):
    result = ws.brain.set_policies(owner, {"review_days": {"rule": 180}})
    assert result["policy"]["review_days"] == {"rule": 180}
    assert ws.brain.policies(owner)["review_days"] == {"rule": 180}
    (event,) = ws.events.activity(owner, subject_id="policy")
    assert (event.type, event.data["checkpoint"]) == ("brain.policy_changed", "cp-policy")
    with pytest.raises(ValidationFailed):
        ws.brain.set_policies(owner, {})


# ---- an entry that needs an update is marked, with what to check


def test_an_entry_that_needs_an_update_is_marked_with_why(ws, owner, connect):
    entry = ws.brain.mark(owner, "voice-guide", "stale", reason="Add the new offer")
    assert entry.stale
    (event,) = ws.events.activity(owner, subject_id="voice-guide", types=["brain.marked"])
    assert (event.reason, event.data["state"]) == ("Add the new offer", "stale")
    with pytest.raises(ValidationFailed):
        ws.brain.mark(owner, "voice-guide", "stale", reason=" ")
    with pytest.raises(PermissionDenied):
        ws.brain.mark(connect(), "voice-guide", "stale", reason="Models only propose")
