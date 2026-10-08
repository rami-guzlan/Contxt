"""Catch up: what waits as a plan rather than a pile (three tiers, a recommendation on every
decision, paced upkeep, offers to decide once), the health score, and the person's state."""

from datetime import UTC, datetime, timedelta

import pytest

from workspace_core.errors import PermissionDenied, ValidationFailed
from workspace_core.services.catchup import QUOTA, drift, health, judgment_kind, offers


def propose(ws, who, title, **fields):
    fields.setdefault("statement", f"{title}.")
    fields.setdefault("evidence", "The calendar")
    return ws.brain.propose(who, title=title, **fields)


def by_key(cards):
    return {c["key"]: c for c in cards}


def test_clear_suggestions_are_quick_groups_and_the_rest_one_at_a_time(ws, owner, brain):
    first = propose(ws, owner, "Posting days", kind="rule", topic="brand/voice")
    second = propose(ws, owner, "Posting times", kind="rule", topic="brand/voice")
    clash = propose(ws, owner, "Headlines in title case", kind="rule")
    brain.analysis[clash.proposal_id] = {
        "conflicts": [{"id": "voice-guide", "title": "Voice guide", "body": "Sentence case."}],
        "route_key": "brand/voice",
    }
    for made in (first, second):
        brain.analysis[made.proposal_id] = {"route_key": "brand/voice"}
    plan = ws.catch_up.plan(owner)
    (group,) = plan["quick"]
    assert group["proposal_ids"] == [first.proposal_id, second.proposal_id]
    assert group["title"] == "2 rules for Brand"
    assert group["shapes"] and group["detail"] == "nothing they disagree with"
    (card,) = plan["judgment"]
    assert (card["type"], card["proposal_id"]) == ("conflict", clash.proposal_id)
    assert card["with"]["id"] == "voice-guide"
    assert card["recommend"]["action"] == "use_this"  # the person wrote it, in the app
    assert card["actions"][0] == "keep_mine"
    assert plan["counts"]["judgment"] == 1 and plan["counts"]["quick_items"] == 2
    assert plan["seconds"] == 40 + 8 and plan["minutes"] == 1
    assert not plan["caught_up"]


def test_why_a_suggestion_needs_judgment():
    row = {"kind": "note.create", "target": {}}
    assert judgment_kind(row, {}) is None
    assert judgment_kind(row, {"overlaps": [{"may_contradict": True}]}) == "conflict"
    assert judgment_kind(row, {"overlaps": [{"close": True}]}) == "close"
    assert judgment_kind(row, {"duplicates": [{"id": "p2"}]}) == "duplicate"
    assert judgment_kind(row, {"problems": ["Its text names a path"]}) == "problem"
    assert (
        judgment_kind({"kind": "note.create", "target": {"private": "an email"}}, {}) == "private"
    )
    assert judgment_kind({"kind": "note.update", "target": {}}, {}) == "change"
    assert judgment_kind({"kind": "note.archive", "target": {}}, {}) == "retire"
    assert judgment_kind({"kind": "skill.create", "target": {}}, {}) == "skill"
    assert judgment_kind(row, {"replaces": [{"id": "voice-guide"}]}) == "replace"


def test_later_hides_an_item_and_seen_starts_the_next_recap(ws, owner, brain, clock):
    made = propose(ws, owner, "Posting days")
    key = f"proposal:{made.proposal_id}"
    ws.catch_up.snooze(owner, key)
    plan = ws.catch_up.plan(owner)
    assert plan["caught_up"] and plan["counts"]["snoozed"] == 1
    clock.advance(timedelta(days=4))
    assert not ws.catch_up.plan(owner)["caught_up"]  # back after the snooze
    assert ws.catch_up.plan(owner)["seen_at"] is None
    ws.catch_up.seen(owner)
    clock.advance(timedelta(days=5))
    plan = ws.catch_up.plan(owner)
    assert plan["away_days"] == 5 and plan["recap_first"]
    ws.catch_up.dismiss(owner, key)
    assert ws.catch_up.plan(owner)["caught_up"]
    with pytest.raises(ValidationFailed):
        ws.catch_up.snooze(owner, "not a key!")


def test_upkeep_comes_in_weekly_doses_most_used_first(ws, owner, brain):
    brain.watch["recheck"] = [
        {"id": f"note-{i}", "title": f"Note {i}", "why": "past its date"} for i in range(5)
    ]
    plan = ws.catch_up.plan(owner)
    rechecks = [c for c in plan["upkeep"] if c["type"] == "recheck"]
    assert len(rechecks) == QUOTA["recheck"]
    # Confirming one this week leaves room for two.
    ws.brain.decide_many(
        owner,
        [{"action": "verify", "entry_id": "voice-guide"}],
        source={"catch_up": "recheck:voice-guide"},
    )
    plan = ws.catch_up.plan(owner)
    assert len([c for c in plan["upkeep"] if c["type"] == "recheck"]) == QUOTA["recheck"] - 1


def test_two_notes_that_look_alike_can_be_set_aside(ws, owner, brain):
    brain.watch["twins"] = [
        {"a": "voice-guide", "a_title": "Voice guide", "b": "tone", "b_title": "Tone", "score": 0.8}
    ]
    (card,) = [c for c in ws.catch_up.plan(owner)["upkeep"] if c["type"] == "duplicate"]
    assert card["key"] == "twin:voice-guide|tone"
    assert card["recommend"]["action"].startswith("keep:")
    ws.catch_up.dismiss(owner, card["key"])
    assert not [c for c in ws.catch_up.plan(owner)["upkeep"] if c["type"] == "duplicate"]


def test_offers_follow_a_run_of_the_same_yes():
    capture = {"fact": {"chat": "wait"}, "rule": {"chat": "apply"}}
    yes = {"action": "approved", "capture": "fact:chat"}
    assert offers([yes] * 4, capture, "personal") == []
    (offer,) = offers([yes] * 5, capture, "careful")
    assert offer["key"] == "offer:fact:chat" and offer["kept"] == 5
    assert offer["title"] == "Let facts from your AI go straight in?"
    broken = [yes, yes, {"action": "rejected", "capture": "fact:chat"}] + [yes] * 5
    assert offers(broken, capture, "personal") == []  # newest first: only two since the no
    assert offers([yes] * 9, capture, "regulated") == []
    assert offers([{"action": "approved", "capture": "rule:chat"}] * 9, capture, "personal") == []


def test_an_offer_comes_from_the_journal_and_can_be_turned_down(ws, owner, brain):
    brain.policy.update(preset="careful", capture={"fact": {"chat": "wait"}})
    brain.events = [
        {"at": "2026-09-27T10:00:00Z", "action": "approved", "capture": "fact:chat"}
    ] * 6
    plan = ws.catch_up.plan(owner)
    (offer,) = plan["offers"]
    ws.catch_up.dismiss(owner, offer["key"], days=90)
    assert ws.catch_up.plan(owner)["offers"] == []


def test_health_is_three_factors_with_fixes():
    today = datetime(2026, 9, 28, tzinfo=UTC)
    old = "2026-06-01"
    rows = [
        {
            "type": "note",
            "live": True,
            "kind": "fact",
            "added": old,
            "stale": None,
            "uses": {"d30": 1},
        }
        for _ in range(8)
    ]
    rows[0]["stale"] = "past its review date"
    rows[1]["uses"] = {"d30": 0}
    found = health(rows, {"twins": [{"a": "x", "b": "y"}], "flagged": []}, today)
    assert [f["key"] for f in found["factors"]] == ["fresh", "tidy", "used"]
    assert found["factors"][0]["fix"]["to"] == "/review"
    assert 60 <= found["score"] < 100 and found["label"] in ("good", "fair")
    assert health(rows[:3], {}, today) == {"score": None, "label": "new", "factors": []}


def test_only_the_person_sets_items_aside(ws, owner, connect):
    claude = connect()
    assert "judgment" in ws.catch_up.plan(claude)  # a model may read the plan
    for act in (ws.catch_up.seen, lambda who: ws.catch_up.snooze(who, "unused")):
        with pytest.raises(PermissionDenied):
            act(claude)


def test_a_rule_that_reads_like_a_safety_line_is_offered_as_a_must_hold(ws, owner, brain):
    from workspace_core.ports import BrainEntry

    brain.entries["nut-rule"] = BrainEntry(
        id="nut-rule",
        title="No peanuts at school",
        text="Ollie is allergic to peanuts.",
        scope="company",
        kind="rule",
        status="approved",
        revision="r1",
    )
    rows = [
        {
            "type": "note",
            "id": "nut-rule",
            "title": "No peanuts at school",
            "summary": "Ollie is allergic to peanuts: no peanuts in lunches.",
            "kind": "rule",
            "load": "on-demand",
            "live": True,
            "area": "family",
            "area_label": "Family",
            "uses": {"d30": 2},
        },
        {
            "type": "note",
            "id": "posting-days",
            "title": "Posting days",
            "summary": "Post on Tuesdays and Thursdays.",
            "kind": "rule",
            "load": "on-demand",
            "live": True,
            "area": "brand",
            "uses": {"d30": 9},
        },
    ]
    brain.inventory = lambda: rows
    (card,) = [c for c in ws.catch_up.plan(owner)["upkeep"] if c["type"] == "musthold"]
    assert (card["id"], card["area"]) == ("nut-rule", "family")
    assert card["recommend"]["action"] == "make_must_hold"
    assert "peanuts" in card["triggers"] and "the" not in card["triggers"]
    # Making it a must-hold is an owner decision on the entry, counted against this week's dose.
    ws.brain.decide_many(
        owner,
        [
            {
                "action": "update",
                "entry_id": "nut-rule",
                "fields": {"load": "domain", "applies_to": "family", "triggers": "lunch, snack"},
            }
        ],
        source={"catch_up": card["key"]},
    )
    assert brain.batches[-1]["decisions"][0]["fields"]["load"] == "domain"
    assert not [c for c in ws.catch_up.plan(owner)["upkeep"] if c["type"] == "musthold"]


def test_must_hold_fields_are_details_a_person_can_set(ws, owner):
    with pytest.raises(ValidationFailed):
        ws.brain.decide_many(
            owner, [{"action": "update", "entry_id": "voice-guide", "fields": {"weight": "1"}}]
        )
    long = ", ".join(f"word{i}" for i in range(150))
    out = ws.brain.decide_many(
        owner,
        [{"action": "update", "entry_id": "voice-guide", "fields": {"triggers": long}}],
    )
    assert out["results"][0]["ok"]


def test_a_change_to_a_baseline_is_a_card_of_its_own_never_a_quick_yes(ws, owner, brain):
    made = propose(ws, owner, "Headlines in title case", kind="rule", topic="brand/voice")
    brain.analysis[made.proposal_id] = {
        "route_key": "brand/voice",
        "tensions": [
            {
                "id": "voice-guide",
                "title": "Voice guide",
                "body": "Write plainly. No hype.",
                "why": "one rules out what the other allows",
                "baseline": "it is a rule",
                "found_by": "close to it",
                "model": None,
            }
        ],
        "baseline": {
            "id": "voice-guide",
            "title": "Voice guide",
            "body": "Write plainly. No hype.",
            "change": "disagree",
            "why": "it is a rule",
            "tension": "one rules out what the other allows",
            "uses": 0,
            "impact": {"conversations": 0, "recent": [], "domains": []},
        },
        "checks": {"pairs": 1, "read": 0, "model": "waiting"},
    }
    plan = ws.catch_up.plan(owner)
    assert plan["quick"] == []
    (card,) = plan["judgment"]
    assert (card["type"], card["tag"]) == ("baseline", "Changes a baseline")
    assert card["actions"] == ["revise", "keep_mine", "both_hold", "later"]
    assert card["baseline"]["id"] == "voice-guide" and card["check"]["model"] == "waiting"
    assert "a baseline: it is a rule" in card["why"]
    assert card["recommend"]["action"] == "revise"  # the person wrote it, in the app
    assert plan["seconds"] == 60


def test_what_went_in_on_its_own_comes_back_once_as_a_spot_check(ws, owner, brain, clock):
    brain.events.insert(
        0,
        {
            "at": (clock.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": "auto-applied",
            "note": "voice-guide",
        },
    )
    plan = ws.catch_up.plan(owner)
    (spot,) = [c for c in plan["upkeep"] if c["type"] == "spot"]
    assert spot["key"] == "spot:voice-guide" and "went in on its own" in spot["why"]
    ws.brain.decide_many(
        owner,
        [{"action": "verify", "entry_id": "voice-guide"}],
        source={"catch_up": "spot:voice-guide", "seconds": 9},
    )
    for _ in range(QUOTA["spot"] - 1):
        brain.points.insert(0, {"at": brain.points[0]["at"], "source": {"catch_up": "spot:x"}})
    plan = ws.catch_up.plan(owner)
    assert not [c for c in plan["upkeep"] if c["type"] == "spot"]  # this week's dose is used


def test_drift_is_the_share_of_approvals_taken_back_within_a_month():
    now = datetime(2026, 10, 8, tzinfo=UTC)
    points = [
        {
            "at": "2026-10-01T10:00:00Z",
            "decisions": [{"action": "approved"}],
            "undone_at": "2026-10-03T10:00:00Z",
        },
        {"at": "2026-09-20T10:00:00Z", "decisions": [{"action": "approved"}], "undone_at": None},
        {"at": "2026-09-15T10:00:00Z", "decisions": [{"action": "rejected"}]},
        {"at": "2026-10-04T10:00:00Z", "decisions": [], "undoes": "cp-1"},
        {"at": "2026-06-01T10:00:00Z", "decisions": [{"action": "approved"}]},
    ]
    assert drift(points, now) == {"approvals": 2, "undone": 1, "share": 0.5, "days": 30}


def test_a_value_with_a_newer_one_is_offered_for_retirement(ws, owner, brain):
    brain.watch["dated"] = [
        {
            "key": "older:mrr-august|mrr-september",
            "older": {"id": "mrr-august", "title": "MRR, August"},
            "newer": {"id": "mrr-september", "title": "MRR, September"},
            "older_as_of": "2026-08-31",
            "newer_as_of": "2026-09-30",
        }
    ]
    plan = ws.catch_up.plan(owner)
    (card,) = [c for c in plan["upkeep"] if c["type"] == "older"]
    assert (card["older"]["id"], card["newer"]["id"]) == ("mrr-august", "mrr-september")
    assert card["older_as_of"] == "2026-08-31" and card["key"] == "older:mrr-august|mrr-september"
