"""After a distill, the world overview is drafted on the ingest model when the map changed
enough, and the draft waits for the owner (v4 backend plan, 13.4); a broken model never fails
the distill."""


def _fake(runtime, monkeypatch, answer="Northwind is a small design studio.", fail=False):
    asked = []

    def ask_measured(who, prompt, *, timeout=180.0, job="ask", runner="claude", model=None):
        asked.append({"job": job, "model": model, "prompt": prompt})
        if fail:
            raise RuntimeError("the CLI is not signed in")
        return {"answer": answer, "tokens_in": 10, "tokens_out": 5, "measured": True}

    monkeypatch.setattr(runtime.runners, "ask_measured", ask_measured)
    return asked


def test_the_overview_is_drafted_once_and_waits(owner, runtime, monkeypatch):
    asked = _fake(runtime, monkeypatch)
    lines = runtime.heartbeat._world_overview(runtime.ws.owner())
    assert lines == ["Drafted a new world overview: it waits for you in Review."]
    assert [a["job"] for a in asked] == ["world-draft"]
    assert "<world>" in asked[0]["prompt"]
    assert runtime.heartbeat._world_overview(runtime.ws.owner()) == []  # same regions
    assert len(asked) == 1


def test_a_failing_model_never_fails_the_distill(owner, runtime, monkeypatch):
    _fake(runtime, monkeypatch, fail=True)
    lines = runtime.heartbeat._world_overview(runtime.ws.owner())
    assert lines and lines[0].startswith("The world overview was not drafted")


def test_the_world_page_reads_the_brain_as_a_world(owner):
    found = owner.ok(owner.get("/api/brain/world"))
    assert {"overview", "regions", "entries", "edges", "timeline", "lore", "apps"} <= set(found)
    assert any(r["kind"] == "project" for r in found["regions"])
