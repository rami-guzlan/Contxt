"""The Test Bench after each distill (Release 1 plan, 15.6): the suites marked "after distill"
run against the new Brain version; an answer whose packet did not change keeps its last score;
at most 20 test runs a day; a drop (the grade falls a point, a criterion goes from met to missed,
or an answer you liked is now graded 2 or under) raises a "Quality dropped" card in Catch up
with the answers before and after and the entries likely behind it, to Roll back or Accept."""

import pytest

from workspace_server import regression

REQUEST = "Draft the case study for the website redesign"
GOOD = (
    '{"criteria": [{"criterion": "Names the client", "result": "met"},'
    ' {"criterion": "Has results", "result": "met"}], "overall": 4, "reason": "Good."}'
)
WORSE = (
    '{"criteria": [{"criterion": "Names the client", "result": "missed"},'
    ' {"criterion": "Has results", "result": "met"}], "overall": 2, "reason": "No client."}'
)


class World:
    """The bench's CLI and the Brain's packet and versions, under the test's control."""

    def __init__(self, runtime, monkeypatch):
        self.grade = GOOD
        self.answer = "A case study for Northwind Studio, with results."
        self.packet = "Northwind Studio redesign: launched in June."
        self.asked = []
        self.diff = {"added": [], "changed": [], "removed": [], "cells": []}
        self.restored = []

        def ask_measured(who, prompt, *, timeout=180.0, job="ask", runner="claude", model=None):
            self.asked.append(job)
            text = self.grade if job == "bench-grade" else self.answer
            return {"answer": text, "model": model, "tokens_in": 10, "tokens_out": 5}

        def contexts(who, request, project, modes, include, exclude):
            return {"none": "", "full": self.packet}, {"full": ["projects"]}, {}

        def restore_version(version, *, ids=None):
            self.restored.append((version, ids))
            return {"status": "restored", "version": {"name": "v9"}}

        monkeypatch.setattr(runtime.runners, "ask_measured", ask_measured)
        monkeypatch.setattr(runtime.bench, "_contexts", contexts)
        monkeypatch.setattr(runtime.ws.rt.brain, "version_diff", lambda a, b: dict(self.diff))
        monkeypatch.setattr(runtime.ws.rt.brain, "restore_version", restore_version)

    def runs(self):
        return self.asked.count("bench")


@pytest.fixture
def world(runtime, monkeypatch):
    return World(runtime, monkeypatch)


def suite(owner, *, after_distill=True, tests=1, name="quality"):
    owner.ok(owner.put(f"/api/bench/suites/{name}", json={"after_distill": after_distill}))
    for n in range(tests):
        body = {
            "name": f"Case study {n}" if n else "Case study",
            "request": REQUEST,
            "rubric": ["Names the client", "Has results"],
        }
        owner.ok(owner.post(f"/api/bench/suites/{name}/tests", json=body), 201)


def regress(runtime, version):
    return runtime.regression.after_distill(runtime.ws.owner(), version)


def cards(owner):
    return owner.ok(owner.get("/api/brain/catch-up"))["quality"]


def test_after_a_distill_the_after_distill_suites_run_and_are_graded(owner, runtime, world):
    suite(owner)
    suite(owner, after_distill=False, name="manual")
    done = regress(runtime, "v1")
    assert (done["ran"], done["reused"], done["skipped"]) == (1, 0, 0)
    assert world.asked == ["bench", "bench-grade"]  # only the suite marked after distill
    history = runtime.regression.history(runtime.ws.owner(), "quality")
    assert [(v["brain_version"], v["average"]) for v in history["versions"]] == [("v1", 4.0)]


def test_an_unchanged_packet_keeps_its_last_score_without_a_run(owner, runtime, world):
    suite(owner)
    regress(runtime, "v1")
    world.asked.clear()
    done = regress(runtime, "v2")
    assert (done["ran"], done["reused"]) == (0, 1) and world.asked == []
    history = runtime.regression.history(runtime.ws.owner(), "quality")
    assert [(v["brain_version"], v["average"]) for v in history["versions"]] == [
        ("v1", 4.0),
        ("v2", 4.0),
    ]


def test_a_drop_raises_a_quality_dropped_card_with_before_after_and_likely_causes(
    owner, runtime, world
):
    suite(owner)
    regress(runtime, "v1")
    assert cards(owner) == []
    world.packet = "Northwind Studio redesign: paused. Pricing note: discount retired."
    world.answer = "A case study, with results."
    world.grade = WORSE
    world.diff = {
        "added": [{"id": "n-pricing", "title": "Pricing note", "path": "notes/p.md"}],
        "changed": [{"id": "n-far", "title": "Office plants", "path": "notes/o.md"}],
        "removed": [],
        "cells": [],
    }
    done = regress(runtime, "v2")
    assert done["drops"] == 1
    [card] = cards(owner)
    assert card["title"] == "Quality dropped: Case study"
    assert (card["from_version"], card["version"]) == ("v1", "v2")
    assert card["before"]["output"].startswith("A case study for Northwind")
    assert card["after"]["output"] == "A case study, with results."
    assert (card["before"]["overall"], card["after"]["overall"]) == (4, 2)
    assert any("4 to 2" in r for r in card["reasons"])
    assert any("Names the client" in r for r in card["reasons"])
    # Changed in that distill and in the answer's packet: the pricing note, not the plants.
    assert [c["id"] for c in card["causes"]] == ["n-pricing"]


def test_an_answer_you_liked_now_graded_two_or_under_is_a_drop(owner, runtime, world):
    suite(owner)
    regress(runtime, "v1")
    [row] = runtime.regression.history(runtime.ws.owner(), "quality")["results"]
    owner.ok(owner.post(f"/api/bench/results/{row['id']}/score", json={"thumbs": "up"}))
    world.packet = "Something else entirely."
    world.grade = (
        '{"criteria": [{"criterion": "Names the client", "result": "part"}],'
        ' "overall": 2, "reason": "Thin."}'
    )
    regress(runtime, "v2")
    [card] = cards(owner)
    assert any("thumbs up" in r for r in card["reasons"])


def test_no_drop_no_card(owner, runtime, world):
    suite(owner)
    regress(runtime, "v1")
    world.packet = "Northwind Studio redesign: launched in June, on budget."
    assert regress(runtime, "v2")["drops"] == 0
    assert cards(owner) == []


def test_roll_back_restores_the_likely_causes_and_closes_the_card(owner, runtime, world):
    suite(owner)
    regress(runtime, "v1")
    world.packet, world.grade = "Pricing note: discount retired.", WORSE
    world.diff = dict(world.diff, added=[{"id": "n-pricing", "title": "Pricing note"}])
    regress(runtime, "v2")
    [card] = cards(owner)
    done = owner.ok(owner.post(f"/api/bench/drops/{card['id']}/roll-back"))
    assert world.restored == [("v1", ["n-pricing"])]
    assert done["status"] == "rolled_back" and cards(owner) == []


def test_accept_makes_the_new_answer_the_baseline(owner, runtime, world):
    suite(owner)
    regress(runtime, "v1")
    world.packet, world.grade = "Pricing note: discount retired.", WORSE
    regress(runtime, "v2")
    [card] = cards(owner)
    owner.ok(owner.post(f"/api/bench/drops/{card['id']}/accept"))
    assert cards(owner) == []
    world.packet = "Pricing note: discount retired. Plants watered."
    assert regress(runtime, "v3")["drops"] == 0  # compared with the accepted answer (2), not 4


def test_without_accepting_a_drop_the_next_run_compares_with_the_answer_before_it(
    owner, runtime, world
):
    suite(owner)
    regress(runtime, "v1")
    world.packet, world.grade = "Pricing note: discount retired.", WORSE
    regress(runtime, "v2")
    world.packet = "Pricing note: discount retired. Plants watered."
    regress(runtime, "v3")
    assert {c["version"] for c in cards(owner)} == {"v2", "v3"}
    assert {c["from_version"] for c in cards(owner)} == {"v1"}


def test_at_most_twenty_test_runs_a_day(owner, runtime, world, monkeypatch):
    monkeypatch.setattr(regression, "CAP", 2)
    suite(owner, tests=3)
    done = regress(runtime, "v1")
    assert (done["ran"], done["skipped"]) == (2, 1) and world.runs() == 2
    world.packet = "Something new."
    assert regress(runtime, "v2")["ran"] == 0  # the day's runs are spent
