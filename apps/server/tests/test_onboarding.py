"""First-time setup over REST: the checklist follows the Brain, the owner takes their own
name, and finishing or taking the tour is kept."""

import pytest
from fastapi.testclient import TestClient

from workspace_server.app import create_app
from workspace_server.runners import Runners


@pytest.fixture
def client(runtime):
    # no AI command-line tool on this "computer", whatever the machine running the tests has
    runtime.runners = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=lambda spec: None
    )
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


def done(status):
    return {s["id"]: s["done"] for s in status["steps"]}


def test_setup_follows_the_workspace_and_keeps_its_moments(owner, model):
    start = owner.ok(owner.get("/api/onboarding"))
    assert done(start)["ai"] is True  # the model fixture connected one
    assert done(start)["you"] is False and start["owner_name"] == "Owner"
    me = owner.ok(owner.get("/api/me"))
    renamed = owner.ok(
        owner.client.put(
            f"/api/actors/{me['actor_id']}", json={"name": "Sam Lee"}, headers=owner.headers
        )
    )
    assert renamed["name"] == "Sam Lee"
    assert [s["id"] for s in start["steps"]] == ["you", "goals", "ai", "brain", "project", "file"]
    assert done(start)["goals"] is False
    owner.ok(owner.put("/api/brain/goals", json={"answers": {"purpose": "Run the studio."}}))
    assert done(owner.ok(owner.get("/api/onboarding")))["goals"] is True
    made = owner.ok(
        owner.post(
            "/api/brain/projects",
            json={"name": "Webinars", "summary": "Monthly webinars for clients"},
        ),
        201,
    )
    steps = done(owner.ok(owner.get("/api/onboarding")))
    assert [steps[k] for k in ("you", "ai", "project", "file")] == [True, True, True, False]
    filed = owner.client.post(
        "/api/brain/files",
        headers=owner.headers,
        data={"project": made["id"]},
        files={"file": ("agenda.md", b"# Agenda\n\nIntro, demo, questions.", "text/markdown")},
    )
    assert filed.status_code == 201, filed.text
    steps = done(owner.ok(owner.get("/api/onboarding")))
    assert steps["file"] is True
    kept = owner.ok(owner.post("/api/onboarding", json={"completed": True, "tour_seen": True}))
    assert kept["completed_at"] and kept["tour_seen_at"]
    assert owner.ok(owner.get("/api/onboarding"))["tour_seen_at"] == kept["tour_seen_at"]
    refused = model.post("/api/onboarding", json={"completed": False})
    assert refused.status_code == 403
