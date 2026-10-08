"""Keeping up, end to end on the sample Brain: the catch-up plan (tiers, recommendations,
paced upkeep, the recap), the Brain's goals, the built-in skills, moving in what an AI app
knew, merging two entries, presets, and dictation."""


def propose(model, **fields):
    fields.setdefault("kind", "fact")
    fields.setdefault("evidence", "The rate card")
    reply = model.tool("propose_brain_entry", **fields)
    assert not reply["isError"], reply
    return reply["structuredContent"]["proposal"]


def test_the_plan_sorts_what_waits_into_tiers(owner, model):
    clear = propose(model, title="Motion quotes", statement="Motion work is quoted per second.")
    clash = propose(
        model,
        title="Web project length",
        statement="Web design projects run eight to ten weeks from kickoff to launch.",
        contradicts=["facts-services-002"],
    )
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    assert [g["proposal_ids"] for g in plan["quick"]] == [[clear["proposal_id"]]]
    (card,) = plan["judgment"]
    assert (card["proposal_id"], card["type"]) == (clash["proposal_id"], "conflict")
    assert card["with"]["id"] == "facts-services-002"
    assert card["recommend"]["action"] in card["actions"]
    assert card["source"] == "Claude Code (AI work)"
    assert plan["minutes"] >= 1 and not plan["caught_up"]
    assert plan["health"]["label"] in ("good", "fair", "low", "new")
    owner.ok(owner.post("/api/brain/catch-up/snooze", json={"key": card["key"]}))
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    assert plan["judgment"] == [] and plan["counts"]["snoozed"] == 1
    owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "decisions": [{"action": "approve", "proposal_id": clear["proposal_id"]}],
                "source": {"catch_up": f"group:fact:{plan['quick'][0]['area']}"},
            },
        )
    )
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    assert plan["caught_up"]
    seen = owner.ok(owner.post("/api/brain/catch-up/seen"))
    assert seen["seen_at"]
    refused = model.post("/api/brain/catch-up/seen")
    assert refused.status_code == 403


def test_what_went_in_on_its_own_is_handled_with_its_undo_point(owner, runtime):
    brain = runtime.ws.rt.brain.brain  # the engine behind the adapter
    owner.ok(owner.put("/api/brain/policies", json={"preset": "personal"}))
    made = brain.propose(
        layer="facts",
        topic="services",
        scope="company",
        text="Motion retainers renew every quarter.",
        session_id="sess-abc123",
        capture_origin="chat",
    )
    assert made.data["status"] == "applied", made.text
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    (item,) = plan["handled"]
    assert item["source"] == "chat" and item["checkpoint"]
    assert plan["counts"]["handled"] == 1
    owner.ok(owner.post(f"/api/brain/checkpoints/{item['checkpoint']}/undo"))
    assert owner.ok(owner.get("/api/brain/catch-up"))["handled"] == []  # taken back


def test_goals_are_set_read_back_and_kept_out_of_every_request(owner, model, runtime):
    empty = owner.ok(owner.get("/api/brain/goals"))
    assert not empty["exists"] and empty["questions"][0]["id"] == "purpose"
    assert empty["questions"][0]["why"] and empty["questions"][0]["example"]
    refused = owner.put("/api/brain/goals", json={"answers": {"work": "Design."}})
    assert refused.status_code == 422, refused.text
    saved = owner.ok(
        owner.put(
            "/api/brain/goals",
            json={
                "answers": {
                    "purpose": "Help me run the studio.",
                    "work": "Brand and web design.",
                    "in_motion": "Website redesign\nStudio podcast",
                }
            },
        )
    )
    assert saved["status"] == "saved" and saved["checkpoint"]
    found = owner.ok(owner.get("/api/brain/goals"))
    assert found["answers"]["work"] == "Brand and web design."
    assert found["projects"] == ["Website redesign", "Studio podcast"]
    kernel = runtime.ws.rt.brain.brain.kernel().text
    assert "Help me run the studio." not in kernel  # goals steer what comes in, not requests
    assert model.put("/api/brain/goals", json={"answers": {"purpose": "x"}}).status_code == 403


def test_built_in_skills_are_added_to_an_older_brain(owner):
    listed = owner.ok(owner.get("/api/brain/builtin-skills"))
    assert "knowledge-check" in listed["missing"]
    added = owner.ok(owner.post("/api/brain/builtin-skills", json={}))
    assert "knowledge-check" in added["added"]
    skills = {s["name"]: s for s in owner.ok(owner.get("/api/skills"))["skills"]}
    assert skills["knowledge-check"]["use"] == "run"
    assert skills["wrap-up"]["use"] == "chat"


def test_moving_in_reads_then_proposes_what_is_worth_keeping(owner):
    memory = (
        "## About me\n- Is a designer at Northwind.\n\n## How I like work done\n"
        "- Prefers short answers with the conclusion first.\n"
        "- Write in plain language with short sentences. No jargon, no hype words.\n\n"
        "## Facts\n- Web design projects take twelve weeks from kickoff to launch.\n"
        "- The wifi password is hunter2.\n"
    )
    sources = [{"kind": "chatgpt", "text": memory, "label": "ChatGPT memory"}]
    preview = owner.ok(owner.post("/api/brain/move-in/preview", json={"sources": sources}))
    statuses = {i["original"]: i["status"] for i in preview["ideas"]}
    assert statuses["Write in plain language with short sentences. No jargon, no hype words."] == (
        "known"
    )
    assert statuses["Web design projects take twelve weeks from kickoff to launch."] == "disagree"
    assert statuses["The wifi password is hunter2."] == "private"
    assert owner.ok(owner.get("/api/brain/review"))["proposals"] == []  # nothing written
    kept = owner.ok(owner.post("/api/brain/move-in", json={"sources": sources}), 201)
    assert kept["secrets_left_out"] == 1 and len(kept["proposed"]) == 3
    plan = owner.ok(owner.get("/api/brain/catch-up"))
    sources_seen = {c["source"] for c in plan["judgment"]} | {
        s for g in plan["quick"] for s in g["sources"]
    }
    assert sources_seen == {"Moved in"}
    assert any(c["type"] == "conflict" for c in plan["judgment"])


def test_two_entries_are_merged_by_a_model_and_compared_before_anything_changes(owner, model):
    task = owner.ok(
        owner.post(
            "/api/brain/merge",
            json={"keep_id": "rules-style-001", "other_id": "rules-style-002"},
        ),
        201,
    )
    assert task["template"] == "merge"
    reply = model.tool(
        "propose_brain_entry",
        title="House style",
        statement="Write plainly in short sentences. Headlines use sentence case.",
        kind="rule",
        evidence="Merging the two style entries",
        revises="rules-style-001",
        replaces=["rules-style-002"],
    )
    assert not reply["isError"], reply
    (card,) = owner.ok(owner.get("/api/brain/catch-up"))["judgment"]
    # A rule is a baseline: its new version is compared side by side and needs a reason.
    assert card["type"] == "baseline" and card["with"]["id"] == "rules-style-001"
    assert card["baseline"]["change"] == "revise" and "both_hold" not in card["actions"]


def test_a_preset_is_chosen_over_rest(owner):
    policy = owner.ok(owner.put("/api/brain/policies", json={"preset": "regulated"}))["policy"]
    assert policy["preset"] == "regulated" and policy["auto_apply_own_scope"] is False
    bad = owner.put("/api/brain/policies", json={"preset": "reckless"})
    assert bad.status_code == 422


def test_dictation_says_when_speech_to_text_is_not_set_up(owner, model):
    audio = {"audio": ("talk.webm", b"not really audio", "audio/webm")}
    refused = owner.client.post("/api/speech/transcribe", headers=owner.headers, files=audio)
    assert refused.status_code == 409 and "speech model" in refused.json()["error"]["message"]
    by_model = model.client.post("/api/speech/transcribe", headers=model.headers, files=audio)
    assert by_model.status_code == 403


def test_a_model_can_suggest_a_must_hold_and_it_waits_for_the_owner(owner, model, runtime):
    made = propose(
        model,
        title="Rush jobs",
        statement="Never promise a rush job without asking the studio lead first.",
        kind="rule",
        must_hold={
            "applies_to": "facts",
            "triggers": "rush, asap, deadline",
            "must_text": "Never promise a rush job without asking the studio lead.",
        },
    )
    brain = runtime.ws.rt.brain.brain
    proposal = brain.state().snapshot.proposals[made["proposal_id"]]
    assert proposal.target["load"] == "domain"
    assert proposal.target["triggers"] == ["rush", "asap", "deadline"]
    assert "critical" not in proposal.target  # only the owner makes one critical
    owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={"decisions": [{"action": "approve", "proposal_id": made["proposal_id"]}]},
        )
    )
    packet = brain.context("Can we turn the brochure around asap?", record=False)
    assert made["entry_id"] in packet.data["must_hold_ids"]
    assert "## Must-hold domains" in packet.text
