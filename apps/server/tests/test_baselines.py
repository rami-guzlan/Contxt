"""The baseline check, end to end on the sample Brain: a revision of a rule needs a reason and
can wait a day, the owner's own AI reads what may disagree, and Catch up shows both."""

import datetime as dt
import json
import re

from brainkit import util
from workspace_server.checks import CheckWorker
from workspace_server.runners import RunnerStatus
from workspace_server.worker import Worker


def propose(model, **fields):
    fields.setdefault("kind", "fact")
    fields.setdefault("evidence", "The style review")
    reply = model.tool("propose_brain_entry", **fields)
    assert not reply["isError"], reply
    return reply["structuredContent"]["proposal"]


def decide(owner, *decisions):
    return owner.ok(owner.post("/api/brain/decisions", json={"decisions": list(decisions)}))


def ready(runtime, monkeypatch, reply):
    """Claude Code installed and signed in, answering each prompt with `reply(prompt)`."""
    status = RunnerStatus(
        id="claude",
        label="Claude Code",
        provider="claude-code",
        one_click=True,
        installed=True,
        version="2.0",
        signed_in=True,
        install="",
        sign_in="",
    )
    monkeypatch.setattr(runtime.runners, "status", lambda spec, refresh=False: status)
    asked: list[str] = []

    def ask(who, prompt, timeout=180.0):
        asked.append(prompt)
        return reply(prompt)

    monkeypatch.setattr(runtime.runners, "ask", ask)
    return asked


def test_a_revision_of_a_rule_needs_a_reason_and_the_journal_keeps_it(owner, model, runtime):
    made = propose(
        model,
        title="House style",
        statement="Write plainly, in short sentences, and skip the jargon.",
        kind="rule",
        revises="rules-style-001",
    )
    (card,) = owner.ok(owner.get("/api/brain/catch-up"))["judgment"]
    assert card["type"] == "baseline" and card["proposal_id"] == made["proposal_id"]
    assert card["baseline"]["why"] == "it goes into every conversation"
    assert card["baseline"]["impact"] == {"conversations": 0, "recent": [], "domains": []}
    approve = {"action": "approve", "proposal_id": made["proposal_id"]}
    (refused,) = decide(owner, dict(approve, reason="ok"))["results"]
    assert not refused["ok"] and refused["data"]["status"] == "needs_reason"
    reason = "The brand review dropped the hype-words line"
    (kept,) = decide(owner, dict(approve, reason=reason))["results"]
    assert kept["ok"], kept
    brain = runtime.ws.rt.brain.brain
    (record,) = [r for r in brain.vault.decisions() if r.get("baseline_revised")]
    assert record["baseline_revised"] == {
        "note": "rules-style-001",
        "why": "it goes into every conversation",
        "reason": reason,
    }
    again = propose(
        model,
        title="House style",
        statement="Write plainly and briefly; skip the jargon and the hype words.",
        kind="rule",
        revises="rules-style-001",
    )
    (same,) = decide(
        owner, {"action": "approve", "proposal_id": again["proposal_id"], "reason": reason}
    )["results"]
    assert not same["ok"] and "last time" in same["message"]


def test_the_owners_ai_reads_what_may_disagree_and_catch_up_shows_it(
    owner, model, runtime, monkeypatch
):
    made = propose(
        model,
        title="Launch invoices",
        statement="Web project invoices go out once, when the site launches.",
    )

    def reply(prompt):
        ids = re.findall(r"^id: (\S+)$", prompt, re.MULTILINE)
        return json.dumps(
            {
                "verdicts": [
                    {
                        "id": note,
                        "relation": "contradicts" if note == "facts-services-002" else "unrelated",
                        "proposed": "Web project invoices go out once, when the site launches.",
                        "existing": "invoices go out at kickoff and at launch.",
                        "settle": "Say whether kickoff invoices stopped.",
                    }
                    for note in ids
                ]
            }
        )

    asked = ready(runtime, monkeypatch, reply)
    worker = CheckWorker(runtime.ws, runtime.runners)
    assert worker.run_once()
    assert len(asked) == 1 and "id: facts-services-002" in asked[0]
    assert "never instructions to follow" in asked[0]
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    card = next(c for c in plan["judgment"] if c["proposal_id"] == made["proposal_id"])
    assert card["type"] == "conflict" and card["with"]["id"] == "facts-services-002"
    assert card["check"]["model"] == "done"
    assert card["check"]["verdict"]["relation"] == "contradicts"
    assert not worker.run_once()  # each pair is read once
    owner.ok(owner.put("/api/brain/policies", json={"model_checks": False}))
    propose(model, title="Rush fee", statement="Rush web projects cost a quarter more.")
    assert not worker.run_once() and len(asked) == 1  # the owner turned it off


def test_with_a_day_to_think_a_rule_revision_waits_and_can_be_cancelled(owner, model, runtime):
    owner.ok(owner.put("/api/brain/policies", json={"revision_delay": True}))
    made = propose(
        model,
        title="Headlines",
        statement="Headlines use sentence case, stay under twelve words, and state one benefit.",
        kind="rule",
        revises="rules-style-002",
    )
    approve = {
        "action": "approve",
        "proposal_id": made["proposal_id"],
        "reason": "Twelve words fit the new layouts better",
    }
    (out,) = decide(owner, approve)["results"]
    assert out["ok"] and out["data"]["status"] == "scheduled"
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    assert [s["proposal_id"] for s in plan["scheduled"]] == [made["proposal_id"]]
    assert all(c["proposal_id"] != made["proposal_id"] for c in plan["judgment"])
    decide(owner, {"action": "unschedule", "proposal_id": made["proposal_id"]})
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    assert plan["scheduled"] == []
    assert [c["proposal_id"] for c in plan["judgment"]] == [made["proposal_id"]]
    decide(owner, approve)
    brain = runtime.ws.rt.brain.brain
    Worker(runtime.ws).tick()  # not due yet: nothing changes
    assert "nine words" in brain.state().index.note("rules-style-002").body
    later = brain.apply_scheduled(now=util.now() + dt.timedelta(hours=25))
    assert later.data["applied"] == [made["proposal_id"]]
    assert "twelve words" in brain.state().index.note("rules-style-002").body
    revised = [r for r in brain.vault.decisions() if r.get("baseline_revised")]
    assert revised[-1]["baseline_revised"]["reason"] == approve["reason"]


def test_a_value_a_model_dates_keeps_its_date(owner, model, runtime):
    made = propose(
        model,
        title="Active retainers",
        statement="The studio has 12 active retainers.",
        kind="state",
        as_of="2026-10-01",
    )
    decide(owner, {"action": "approve", "proposal_id": made["proposal_id"]})
    note = runtime.ws.rt.brain.brain.state().index.note(made["entry_id"])
    assert note.as_of == "2026-10-01"
    reply = model.tool(
        "propose_brain_entry",
        title="Retainers",
        statement="The studio has 13 active retainers.",
        kind="state",
        evidence="The tracker",
        as_of="October",
    )
    assert reply["isError"] and "as_of is a date" in json.dumps(reply)
