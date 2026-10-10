"""One statement model (brain-logic plan 6) between the workspace and the Brain: the same
vocabulary on both sides, and a preference proposed from the workspace kept as what it is, a
rule of that subtype, waiting like every rule (it used to be filed as a fact)."""

from brainkit import statements as brain_words
from brainkit.model import LEGACY_KINDS
from workspace_core.domain import statements as workspace_words


def kind_of(target):
    """A proposal's kind as the Brain reads it (an older vault's folder implies it)."""
    return brain_words.kind(target.get("kind") or LEGACY_KINDS.get(target.get("layer") or ""))


def test_the_workspace_speaks_the_brains_vocabulary():
    assert workspace_words.PROPOSAL_KINDS == brain_words.PROPOSAL_KINDS
    assert set(workspace_words.DISTILL_KINDS) <= set(brain_words.PROPOSAL_KINDS)
    assert set(workspace_words.AGENT_KINDS) <= set(brain_words.PROPOSAL_KINDS)
    assert workspace_words.words(("fact", "rule", "decision")) == "fact, rule or decision"


def test_a_preference_from_the_workspace_is_a_rule_of_that_subtype(owner):
    made = owner.ok(
        owner.post(
            "/api/brain/proposals",
            json={
                "title": "Short subject lines",
                "statement": "I prefer subject lines under eight words.",
                "kind": "preference",
                "evidence": "Said in the weekly review.",
            },
        ),
        201,
    )
    assert made["status"] == "pending", made
    waiting = {p["id"]: p for p in owner.ok(owner.get("/api/brain/proposals"))}
    target = waiting[made["proposal_id"]]["target"]
    assert (kind_of(target), target["subtype"]) == ("rule", "preference")
    decided = owner.post(
        "/api/brain/proposals",
        json={
            "title": "Webinars on Tuesdays",
            "statement": "We decided to hold every webinar on a Tuesday.",
            "kind": "decision",
            "evidence": "The team call on Monday.",
        },
    )
    target = {p["id"]: p for p in owner.ok(owner.get("/api/brain/proposals"))}[
        owner.ok(decided, 201)["proposal_id"]
    ]["target"]
    assert target["type"] == "decision"
