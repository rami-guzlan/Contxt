import pytest

from workspace_core.domain.artifact_types import TYPES, check_content
from workspace_core.domain.policy import HUMAN_ONLY, MODEL_DEFAULTS, Grant, Principal
from workspace_core.domain.scope import ScopeRef
from workspace_core.errors import PermissionDenied, ValidationFailed


def model(actions=MODEL_DEFAULTS, projects=None):
    return Principal(
        actor_id="act_model",
        kind="model",
        name="Claude",
        grant=Grant.of(actions, projects, kind="model"),
    )


def test_owner_can_do_everything():
    owner = Principal(
        actor_id="act_owner", kind="human", name="Owner", grant=Grant.of({"*"}, None, kind="human")
    )
    for action in ("approvals.decide", "artifacts.export", "brain.govern", "tasks.claim"):
        owner.require(action, project_id="proj_x")


def test_models_never_hold_human_release_gates():
    grant = Grant.of({"*", "approvals.decide"}, None, kind="model")
    assert not (grant.actions & HUMAN_ONLY)
    principal = Principal(actor_id="act_m", kind="model", name="m", grant=grant)
    for action in HUMAN_ONLY:
        with pytest.raises(PermissionDenied):
            principal.require(action)
    principal.require("tasks.claim")


def test_project_restriction():
    scoped = model(projects={"proj_a"})
    scoped.require("tasks.claim", project_id="proj_a")
    with pytest.raises(PermissionDenied) as info:
        scoped.require("tasks.claim", project_id="proj_b")
    assert "proj_b" in str(info.value)
    # Workspace-wide reads outside any project are still allowed.
    scoped.require("context.read")


def test_unknown_action_is_a_programming_error():
    with pytest.raises(ValueError):
        model().require("tasks.teleport")


def test_scope_refs():
    assert str(ScopeRef.parse("project:proj_01")) == "project:proj_01"
    assert ScopeRef.parse("workspace") == ScopeRef("workspace", None)
    assert ScopeRef.parse("inbox:act_owner").kind == "inbox"
    for bad in ("", "project", "galaxy:1", "project:"):
        with pytest.raises(ValidationFailed):
            ScopeRef.parse(bad)


def test_artifact_types_declare_what_they_accept():
    assert {"document", "social_post", "image", "data_file", "file"} <= set(TYPES)
    check_content("document", "text/markdown")
    check_content("image", "image/png")
    check_content("file", "application/zip")
    with pytest.raises(ValidationFailed):
        check_content("image", "text/plain")
    with pytest.raises(ValidationFailed):
        check_content("hologram", "text/plain")
