"""The Test Bench's three panels (Release 1 plan, 15.3): the same runner and model for every
panel, no tools, the packet in the prompt; no brain means no Brain text; custom leaves out
what was unchecked; each panel keeps its tokens, cost and time; an estimate runs nothing."""

import time

REQUEST = "Draft the case study for the website redesign"


def _fake(runtime):
    asked = []

    def ask_measured(who, prompt, *, timeout=180.0, job="ask", runner="claude", model=None):
        asked.append({"prompt": prompt, "runner": runner, "model": model, "job": job})
        return {
            "answer": f"answer {len(asked)}",
            "model": "claude-haiku-5-5",
            "tokens_in": len(prompt) // 4,
            "tokens_out": 12,
            "cost": 0.0004,
            "ms": 900,
            "measured": True,
        }

    runtime.runners.ask_measured = ask_measured
    return asked


def _finished(owner, run_id):
    for _ in range(100):
        found = owner.ok(owner.get(f"/api/bench/runs/{run_id}"))
        if found["status"] != "running":
            return found
        time.sleep(0.05)
    raise AssertionError("the bench run did not finish")


def test_three_panels_run_with_the_same_model_and_only_the_context_differs(owner, runtime):
    asked = _fake(runtime)
    started = owner.ok(
        owner.post(
            "/api/bench/runs",
            json={"request": REQUEST, "runner": "claude", "model": "claude-haiku-5-5"},
        ),
        202,
    )
    found = _finished(owner, started["id"])
    assert [p["mode"] for p in found["panels"]] == ["none", "full", "custom"]
    assert {(a["runner"], a["model"]) for a in asked} == {("claude", "claude-haiku-5-5")}
    assert asked[0]["prompt"] == REQUEST  # no brain: the request alone
    assert found["panels"][0]["packet"] == ""
    assert "website" in asked[1]["prompt"].lower() and len(asked[1]["prompt"]) > len(REQUEST)
    for panel in found["panels"]:
        assert panel["status"] == "done"
        assert panel["tokens_in"] and panel["tokens_out"] == 12
        assert (panel["cost"], panel["ms"]) == (0.0004, 900)
    assert found["provider"] == "Anthropic"
    assert found["brain_version"]


def test_custom_leaves_out_what_was_unchecked(owner, runtime):
    _fake(runtime)
    preview = owner.ok(owner.post("/api/brain/preview", json={"request": REQUEST}))
    notes = next(s for s in preview["packet_sections"] if s["name"] == "notes")
    gone = notes["items"][0]
    started = owner.ok(
        owner.post(
            "/api/bench/runs",
            json={
                "request": REQUEST,
                "modes": ["full", "custom"],
                "exclude": {"sections": [], "ids": [gone["id"]]},
            },
        ),
        202,
    )
    full, custom = _finished(owner, started["id"])["panels"]
    assert gone["title"] in full["packet"]
    assert gone["title"] not in custom["packet"]
    assert custom["packet_hash"] != full["packet_hash"]
    assert custom["included"]["exclude"]["ids"] == [gone["id"]]


def test_an_estimate_names_the_provider_and_runs_nothing(owner, runtime):
    asked = _fake(runtime)
    found = owner.ok(owner.post("/api/bench/estimate", json={"request": REQUEST}))
    assert found["provider"] == "Anthropic" and found["estimated"] is True
    assert [p["mode"] for p in found["panels"]] == ["none", "full", "custom"]
    assert found["panels"][0]["tokens_in"] < found["panels"][1]["tokens_in"]
    assert asked == []


def test_an_unknown_runner_is_refused(owner, runtime):
    _fake(runtime)
    refused = owner.post("/api/bench/runs", json={"request": REQUEST, "runner": "nope"})
    assert refused.status_code == 422
