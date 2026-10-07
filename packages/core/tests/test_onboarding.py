"""First-time setup: each step is done when its thing exists, so the checklist follows the
Brain; only finishing, putting it aside, the tour and steps said done are stored."""

from dataclasses import replace

import pytest

from workspace_core.errors import PermissionDenied, ValidationFailed
from workspace_core.ports import BrainCatalog


def empty(brain):
    """A new Brain: none of the person's own entries yet."""
    brain.catalog = lambda: BrainCatalog()


def steps(status):
    return {s["id"]: s["done"] for s in status["steps"]}


def test_a_new_workspace_starts_with_nothing_done(ws, owner, brain):
    empty(brain)
    status = ws.onboarding.status(owner)
    assert [s["id"] for s in status["steps"]] == ["you", "goals", "ai", "brain", "project", "file"]
    assert (status["done"], status["total"], status["owner_name"]) == (0, 6, "Owner")
    assert status["completed_at"] is None and status["tour_seen_at"] is None


def test_steps_follow_what_the_brain_holds(ws, owner, connect, brain):
    empty(brain)
    ws.actors.rename(owner, owner.actor_id, "  Sam   Lee ")
    ws.brain.create_project(owner, name="Webinars", summary="Monthly webinars for CLOs")
    connect()
    done = steps(ws.onboarding.status(owner))
    assert done == {
        "you": True,
        "goals": False,
        "ai": True,
        "brain": False,
        "project": True,
        "file": False,
    }
    (started,) = brain.started
    brain.started[0] = replace(started, files=2)
    status = ws.onboarding.status(owner)
    assert steps(status)["file"] is True
    assert {s["id"]: s["count"] for s in status["steps"]}["file"] == 2
    assert ws.onboarding.status(owner)["owner_name"] == "Sam Lee"
    # a CLI on this computer that can run tasks counts as a connected model
    assert steps(ws.onboarding.status(owner, local_model=True))["ai"] is True


def test_a_proposal_waiting_for_review_counts_as_a_start_on_the_brain(ws, owner, brain):
    empty(brain)
    assert steps(ws.onboarding.status(owner))["brain"] is False
    ws.brain.propose(
        owner,
        title="About me",
        statement="I run marketing alone.",
        kind="identity",
        evidence="Said during first-time setup.",
    )
    status = ws.onboarding.status(owner)
    assert steps(status)["brain"] is True and status["brain"]["waiting"] == 1


def test_finishing_putting_aside_and_the_tour_are_kept(ws, owner, connect):
    ws.onboarding.mark(owner, dismissed=True, step="you")
    status = ws.onboarding.status(owner)
    assert status["dismissed_at"] and steps(status)["you"] is True
    ws.onboarding.mark(owner, dismissed=False, completed=True, tour_seen=True)
    status = ws.onboarding.status(owner)
    assert status["dismissed_at"] is None and status["completed_at"] and status["tour_seen_at"]
    with pytest.raises(ValidationFailed):
        ws.onboarding.mark(owner, step="everything")
    with pytest.raises(PermissionDenied):
        ws.onboarding.mark(connect(), completed=True)


def test_names_are_checked_and_only_the_admin_renames_others(ws, owner, connect):
    claude = connect()
    with pytest.raises(ValidationFailed):
        ws.actors.rename(owner, owner.actor_id, "   ")
    with pytest.raises(PermissionDenied):
        ws.actors.rename(claude, owner.actor_id, "Not you")
    assert ws.actors.rename(owner, claude.actor_id, "Claude (laptop)").name == "Claude (laptop)"
