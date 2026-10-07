import pytest

from workspace_core.domain.states import (
    APPROVAL,
    ARTIFACT,
    IDEA,
    RUN,
    TASK,
)
from workspace_core.errors import InvalidTransition


def test_task_happy_path_follows_the_spec():
    path = ["draft", "ready", "claimed", "in_progress", "review", "done"]
    for current, target in zip(path, path[1:], strict=False):
        TASK.check(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "claimed"),  # nothing is claimed before it is ready
        ("draft", "done"),
        ("ready", "done"),  # work is not done without a run
        ("review", "claimed"),
        ("cancelled", "ready"),
        ("archived", "ready"),
    ],
)
def test_task_rejects_transitions_the_spec_does_not_list(current, target):
    with pytest.raises(InvalidTransition) as info:
        TASK.check(current, target)
    assert current in str(info.value) and target in str(info.value)


def test_task_branches():
    for current in ("claimed", "in_progress"):
        for target in ("blocked", "failed", "ready", "cancelled"):
            TASK.check(current, target)
    TASK.check("blocked", "ready")
    TASK.check("failed", "ready")
    TASK.check("review", "ready")  # changes requested: another pass
    TASK.check("done", "ready")  # a recurring task comes due again
    TASK.check("done", "archived")
    TASK.check("archived", "draft")  # restore


def test_unknown_states_are_refused():
    with pytest.raises(InvalidTransition):
        TASK.check("draft", "published")
    with pytest.raises(InvalidTransition):
        TASK.check("nonsense", "ready")


def test_runs_end_once():
    assert RUN.is_active("claimed") and RUN.is_active("in_progress")
    for end in ("completed", "failed", "blocked", "expired", "released", "cancelled"):
        RUN.check("in_progress", end)
        assert RUN.is_terminal(end)
        with pytest.raises(InvalidTransition):
            RUN.check(end, "in_progress")


def test_artifact_lifecycle():
    for current, target in [
        ("draft", "in_review"),
        ("in_review", "approved"),
        ("approved", "exported"),
        ("in_review", "rejected"),
        ("in_review", "draft"),
        ("approved", "draft"),  # a new version needs a new decision
    ]:
        ARTIFACT.check(current, target)
    with pytest.raises(InvalidTransition):
        ARTIFACT.check("draft", "exported")  # never exported unapproved
    with pytest.raises(InvalidTransition):
        ARTIFACT.check("rejected", "exported")


def test_approvals_are_decided_once():
    for decision in ("approved", "rejected", "changes_requested", "cancelled"):
        APPROVAL.check("pending", decision)
        with pytest.raises(InvalidTransition):
            APPROVAL.check(decision, "approved")


def test_idea_lifecycle():
    IDEA.check("captured", "developing")
    IDEA.check("developing", "promoted")
    IDEA.check("captured", "archived")
    IDEA.check("archived", "captured")
    with pytest.raises(InvalidTransition):
        IDEA.check("promoted", "captured")
