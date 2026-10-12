"""Test the Brain without a Lab: the checks this app runs on its own Brain, written into the
same results contract a Lab uses. Claude Code is faked; nothing leaves the machine."""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from workspace_server import builtin_checks

PREFIX = "/api/test-the-brain"


def wait_for(check, *, timeout=60.0, what="the check"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        found = check()
        if found:
            return found
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {what}")


def settled(owner):
    live = owner.ok(owner.get(f"{PREFIX}/live"))
    active = live["active"]
    return live if active and active["state"] != "running" else None


def run(owner, kind, **body):
    started = owner.ok(owner.post(f"{PREFIX}/runs", json={"kind": kind, **body}), 202)
    live = wait_for(lambda: settled(owner))
    return started, live


def vault_files(vault):
    """Every file of the Brain except its runtime folder, with its size."""
    out = {}
    for base, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in (".brain", ".git")]
        for name in files:
            path = os.path.join(base, name)
            out[os.path.relpath(path, vault)] = os.path.getsize(path)
    return out


def add_eval_cases(vault):
    cases = {
        "cases": [
            {
                "id": "headline",
                "request": "Write a headline for the site",
                "must": [["rules-style-001"]],
                "useful": [],
                "noise": [],
            },
            {
                "id": "headline-held",
                "request": "Write a headline for the homepage",
                "must": [["rules-style-001"]],
                "useful": [],
                "noise": [],
                "holdout": True,
            },
        ],
        "thresholds": {},
    }
    with open(os.path.join(vault, "eval.json"), "w", encoding="utf-8") as handle:
        json.dump(cases, handle)


def test_without_a_lab_the_page_offers_the_checks_this_app_can_run(owner):
    state = owner.ok(owner.get(PREFIX))
    assert state["source"] == "builtin" and state["lab"] is None
    kinds = {k["id"]: k for k in state["status"]["run_kinds"]}
    assert set(kinds) == {"health", "report", "eval", "machine", "difference"}
    assert kinds["difference"]["paid"] and not kinds["health"]["paid"]
    waits = {w["suite"]: w for w in state["builtin"]["waits"]}
    if not builtin_checks.engine_ready():
        for name in ("Scores for each layer and the why view", "The machine check"):
            assert waits[name]["note"] == "Waits for the retrieval engine (build step 3b)"
    assert state["builtin"]["name"] == "Checks on your own Brain"


def test_the_health_check_reads_the_brain_and_changes_nothing_in_it(owner, runtime):
    before = vault_files(runtime.settings.brain_vault)
    started, live = run(owner, "health")
    assert live["active"]["state"] == "done", live
    summary = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}"))
    ids = {m["id"] for m in summary["metrics"]}
    assert {"health.problems", "health.warnings", "health.kernel_tokens"} <= ids
    assert summary["config"]["source"] == "Checks on your own Brain"
    facts = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}/cases/HC-facts"))
    assert facts["kind"] == "table" and facts["view"]["rows"]
    assert vault_files(runtime.settings.brain_vault) == before
    saved = os.path.join(runtime.settings.data_dir, "test-the-brain", "builtin", "results")
    assert os.path.isfile(os.path.join(saved, "runs", started["run"], "summary.json"))


def test_the_report_card_keeps_what_context_cost(owner):
    started, live = run(owner, "report")
    assert live["active"]["state"] == "done", live
    summary = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}"))
    assert "per_day_usd" in summary["card"] and "text" in summary["card"]
    assert any(m["id"] == "report.per_day_usd" for m in summary["metrics"])


def test_the_labeled_requests_check_says_what_to_do_when_there_is_nothing_to_score(owner):
    _started, live = run(owner, "eval")
    assert live["active"]["state"] == "failed"
    assert "Label some of your requests in Activity" in live["active"]["message"]


def test_the_brains_own_eval_cases_are_scored_and_drawn_as_retrieval_cases(owner, runtime):
    add_eval_cases(runtime.settings.brain_vault)
    before = vault_files(runtime.settings.brain_vault)
    started, live = run(owner, "eval")
    assert live["active"]["state"] == "done", live
    summary = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}"))
    recall = [m for m in summary["metrics"] if m["id"] == "evalcases.must_recall"]
    assert {m["split"] for m in recall} >= {"all"}
    cases = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}/cases"))
    assert cases["total"] == 2 and cases["kinds"] == ["retrieval"]
    one = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}/cases/evalcases-headline"))
    assert one["request"] == "Write a headline for the site"
    labels = {n["label"] for n in one["view"]["notes"]}
    assert labels & {"needed_delivered", "needed_missed", "useful", "unlabeled", "noise"}
    assert vault_files(runtime.settings.brain_vault) == before


def test_see_the_difference_is_paid_and_asks_for_a_second_press(owner, runtime, monkeypatch):
    answers = iter(
        [
            "Exciting news! Join our webinar!",
            "57% of new supervisors got under 8 hours of training.",
            json.dumps({"differences": [{"what": "Opens with a sourced number", "item": ""}]}),
        ]
    )
    asked = []

    def ask(who, prompt, timeout=180.0, job="ask"):
        asked.append(prompt)
        return next(answers)

    monkeypatch.setattr(runtime.runners, "ask", ask)
    first = owner.post(f"{PREFIX}/runs", json={"kind": "difference", "request": "Write a headline"})
    assert first.status_code == 409 and first.json()["error"]["needs_confirmation"] is True
    assert asked == [], "nothing was asked before the second press"
    started, live = run(owner, "difference", request="Write a headline", confirm=True)
    assert live["active"]["state"] == "done", live
    case = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}/cases/DF-1"))
    assert case["kind"] == "outcome" and case["request"] == "Write a headline"
    assert case["view"]["without"]["text"].startswith("Exciting")
    assert case["view"]["with"]["text"].startswith("57%")
    assert case["view"]["key_points"][0]["text"] == "Opens with a sourced number"


def test_a_check_in_progress_blocks_a_second_and_can_be_cancelled(owner, runtime, monkeypatch):
    release = threading.Event()

    def ask(who, prompt, timeout=180.0, job="ask"):
        release.wait(20)
        return "{}"

    monkeypatch.setattr(runtime.runners, "ask", ask)
    started = owner.ok(
        owner.post(
            f"{PREFIX}/runs", json={"kind": "difference", "request": "x y", "confirm": True}
        ),
        202,
    )
    again = owner.post(f"{PREFIX}/runs", json={"kind": "health"})
    assert again.status_code == 409 and "already running" in again.text
    stopped = owner.ok(owner.post(f"{PREFIX}/runs/{started['run']}/cancel"))
    assert stopped["state"] == "cancelled"
    release.set()
    wait_for(
        lambda: (
            runtime.testing.builtin._thread is None
            or not runtime.testing.builtin._thread.is_alive()
        )
    )
    assert owner.ok(owner.get(f"{PREFIX}/runs"))["runs"] == [], "a cancelled check leaves no result"


def test_a_workspace_with_no_brain_says_so(tmp_path, clock):
    from fastapi.testclient import TestClient

    from workspace_server.app import create_app, open_runtime
    from workspace_server.settings import Settings

    token = "wst_" + "owner-token-for-tests-" + "x" * 20
    settings = Settings(
        data_dir=str(tmp_path / "data"), owner_token=token, web_dist=str(tmp_path / "w")
    )
    opened = open_runtime(settings, clock=clock)
    try:
        with TestClient(create_app(runtime=opened)) as client:
            headers = {"Authorization": f"Bearer {token}"}
            reply = client.post(f"{PREFIX}/runs", json={"kind": "health"}, headers=headers)
            assert reply.status_code == 409 and "no Brain" in reply.text
    finally:
        opened.close()


@pytest.mark.parametrize("bad", ["", "../health", "everything"])
def test_only_the_listed_checks_start(owner, bad):
    assert owner.post(f"{PREFIX}/runs", json={"kind": bad}).status_code == 422


# ------------------------------------------------------------------ watch it work
def ledger_counts(runtime):
    ledger = runtime.brain.brain.ledger
    with ledger._connect() as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("sessions", "packets", "deliveries", "usage_daily")
        }


def test_a_typed_request_is_drawn_stage_by_stage_and_leaves_no_trace(owner, runtime):
    before = ledger_counts(runtime)
    files = vault_files(runtime.settings.brain_vault)
    drawn = owner.ok(
        owner.post(f"{PREFIX}/watch", json={"request": "Write a headline for the site"})
    )
    assert drawn["test"] is True and drawn["client"] == "contxt-test" and drawn["read_only"] is True
    assert [s["id"] for s in drawn["stages"]] == [
        "read",
        "gate",
        "admission",
        "search",
        "cut",
        "second",
        "fit",
    ]
    by_id = {s["id"]: s for s in drawn["stages"]}
    assert by_id["read"]["state"] == "done" and by_id["read"]["in"] == 1
    assert by_id["search"]["in"] == len(runtime.brain.brain.state().index.notes)
    assert by_id["fit"]["out"] >= 1 and drawn["tokens"] > 0 and drawn["ms"] >= 0
    if not builtin_checks.engine_ready():
        for waiting in ("gate", "cut", "second"):
            assert by_id[waiting]["state"] == "waiting"
            assert "Waits for the retrieval engine (build step 3b)" in by_id[waiting]["note"]
    assert drawn["notes"], "the notes the request would get are listed with why"
    assert ledger_counts(runtime) == before, "it counts as no request, in usage or in evals"
    assert vault_files(runtime.settings.brain_vault) == files


def test_a_case_of_the_built_in_checks_is_routed_again_with_its_labels(owner, runtime):
    add_eval_cases(runtime.settings.brain_vault)
    started, _live = run(owner, "eval")
    before = ledger_counts(runtime)
    drawn = owner.ok(
        owner.post(f"{PREFIX}/watch", json={"run": started["run"], "case": "evalcases-headline"})
    )
    assert drawn["request"] == "Write a headline for the site" and not drawn.get("from_record")
    assert drawn["labels"], "the case's labels travel with it so notes can be colored"
    assert ledger_counts(runtime) == before


@pytest.mark.parametrize("body", [{}, {"request": "   "}, {"request": "x" * 2001}])
def test_watch_needs_a_real_request(owner, body):
    assert owner.post(f"{PREFIX}/watch", json=body).status_code == 422


def test_the_engines_own_record_fills_the_stages_that_wait():
    from workspace_server import watch

    # The shape the retrieval engine writes into a brief's data (its Audit.summary).
    engine = {
        "mode": "on",
        "gate": {"yes": 0.91, "cut": 0.5, "passed": True},
        "timings": {"gate": 12.5, "find": 30.0, "cut": 80.0, "second_pass": 41.0, "fit": 2.0},
        "rounds": 2,
        "candidates": 40,
        "outcomes": {"body": 5, "pointer": 2, "out": 31, "held": 2},
    }
    filled = watch.engine_stages(engine)
    assert filled["gate"]["state"] == "done" and filled["gate"]["ms"] == 12.5
    assert "probability 0.91" in filled["gate"]["note"]
    assert (filled["cut"]["in"], filled["cut"]["out"]) == (40, 9)
    assert filled["second"]["note"] == "2 round(s) of the link loop."
    assert filled["search"]["out"] == 40 and filled["fit"]["ms"] == 2.0
    assert watch.engine_stages(None) == {} and watch.engine_stages({"mode": "fallback"}) == {}


def test_the_stages_use_the_engines_record_and_say_why_it_did_not_run():
    from workspace_server import watch

    data = {
        "mode": "lean",
        "topics": ["a"],
        "scope_chain": ["root"],
        "note_ids": ["n1"],
        "token_count": 100,
        "trace": {"note_scores": [{"id": "n1"}], "decisions": []},
    }
    on = watch.from_trace(
        dict(
            data,
            engine={
                "mode": "on",
                "gate": {"passed": True},
                "timings": {"gate": 5.0, "cut": 9.0},
                "candidates": 3,
                "outcomes": {"body": 1, "out": 2},
            },
        ),
        titles={"n1": "Note one"},
        live_notes=10,
        ms=1.0,
    )
    by_id = {s["id"]: s for s in on["stages"]}
    assert on["engine"] is True and by_id["gate"]["state"] == "done" and by_id["cut"]["out"] == 1
    assert by_id["second"]["state"] == "waiting", "a layer the engine gave no time for still waits"
    off = watch.from_trace(
        dict(data, engine={"mode": "fallback", "reason": "no verified model service is running"}),
        titles={},
        live_notes=10,
        ms=1.0,
    )
    gate = {s["id"]: s for s in off["stages"]}["gate"]
    assert (
        gate["state"] == "waiting" and "not running here: no verified model service" in gate["note"]
    )


def test_the_machine_check_says_which_engine_steps_run_here_or_what_runs_instead(owner, runtime):
    if not builtin_checks.machine_ready():
        pytest.skip("this install has no machine check yet")
    before = owner.ok(owner.get(PREFIX))["status"]["qualification"]
    assert {s["step"] for s in before} == {
        "Matching by meaning",
        "The relevance cut",
        "The gate",
        "The second pass",
        "The knowledge agent",
    }
    started, live = run(owner, "machine")
    assert live["active"]["state"] == "done", live
    summary = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}"))
    named = next(m for m in summary["metrics"] if m["id"] == "machine.steps_named")
    # In a test no model service runs, so every step that does not run names what does instead.
    assert named["value"] == 1.0 and named["met"] is True and named["gate"] == "machine.steps_named"
    after = owner.ok(owner.get(PREFIX))["status"]["qualification"]
    for step in after:
        assert step["state"] in ("on", "fallback")
        assert step["state"] == "on" or step["fallback"], step
    computer = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}/cases/MC-computer"))
    assert {r["label"] for r in computer["view"]["rows"]} >= {"Memory", "Setup it gets"}
    behind = owner.ok(
        owner.get(f"{PREFIX}/runs/{started['run']}/cases", params={"gate": "machine.steps_named"})
    )
    assert behind["total"] == 5, "each step is a case behind its gate"
    assert owner.ok(owner.get(PREFIX))["builtin"]["computer"]["machine"]["setup"]


def test_the_qualification_table_reads_the_engines_machine_overview():
    over = {
        "roles": [
            {
                "role": "decide",
                "model": "kev-0.8b",
                "options": [
                    {
                        "name": "kev-0.8b",
                        "ram_gb": 1.5,
                        "measured": {"speed_ms": 90.0},
                        "downloaded": True,
                    }
                ],
            },
            {"role": "rerank", "model": "qwen3-reranker-0.6b", "options": []},
            {
                "role": "embed",
                "model": "bge-small",
                "options": [{"name": "bge-small", "downloaded": True}],
            },
            {"role": "agent", "model": "qwen3.5-4b", "options": []},
        ],
        "engine": {"ready": True, "reason": "", "agent": False},
        "budget_ms": {"gate": 60, "cut": 300, "second_pass": 150},
        "fallbacks": [
            "kev-0.8b has not qualified for the second pass here: it is skipped",
        ],
        "agent_claude_code": True,
    }
    rows = {r["step"]: r for r in builtin_checks.qualification(over)}
    assert rows["The gate"]["state"] == "on" and rows["The gate"]["speed_ms"] == 90.0
    assert rows["The gate"]["budget_ms"] == 60 and rows["The gate"]["peak_ram_mb"] == 1500
    assert rows["The second pass"]["state"] == "fallback"
    assert "it is skipped" in rows["The second pass"]["fallback"]
    assert rows["The knowledge agent"]["fallback"] == "Claude Code on this computer does its work."
    assert rows["Matching by meaning"]["state"] == "on"
    assert builtin_checks.qualification(None) == []
