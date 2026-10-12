"""The updating loop in the app (brain-logic plan 9): "That's wrong" on a request puts a
"Still true?" card in Catch up, answered in one tap; an output is checked against the
must-holds; the knowledge agent's runs are listed with their steps."""

from __future__ import annotations


def test_thats_wrong_on_a_request_asks_still_true_in_catch_up(owner, runtime):
    engine = runtime.ws.rt.brain.brain
    brief = engine.context("Draft the newsletter intro in our voice")
    noted = brief.data.get("note_ids") or []
    assert noted, brief.text
    note = engine.state().index.note(noted[0])
    request = engine.ledger.requests(limit=1)[0]
    made = owner.ok(
        owner.post(
            "/api/loop/corrections",
            json={
                "text": f"That's wrong: {note.title} {note.body[:80]}",
                "packet_id": request["id"],
            },
        )
    )
    assert made["card"]["id"] == note.id
    looped = owner.ok(owner.get("/api/brain/catch-up"))["loop"]
    card = next(c for c in looped if c["type"] == "still_true")
    assert card["note"] == note.id and "still true" in card["ask"]
    owner.ok(owner.post(f"/api/loop/corrections/{card['correction']}", json={"status": "fixed"}))
    after = owner.ok(owner.get("/api/brain/catch-up"))["loop"]
    assert not [c for c in after if c["type"] == "still_true"]
    refused = owner.post("/api/loop/corrections", json={"text": "Wrong."})
    assert refused.status_code == 422


def test_an_output_is_checked_and_the_agents_runs_are_listed(owner):
    found = owner.ok(owner.post("/api/loop/check", json={"text": "A plain draft."}))
    assert found == {"violations": []}
    assert owner.ok(owner.get("/api/loop/runs")) == []
    status = owner.ok(owner.get("/api/loop"))
    assert {"corrections", "bent_rules", "approval_health", "hand_ups"} <= set(status)
