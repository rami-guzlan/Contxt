"""Review over REST: batches with what each proposal would change, bulk decisions, undo and
reconciling a clash, end to end on the sample Brain."""


def propose(model, **fields):
    fields.setdefault("kind", "fact")
    fields.setdefault("evidence", "The rate card")
    reply = model.tool("propose_brain_entry", **fields)
    assert not reply["isError"], reply
    return reply["structuredContent"]["proposal"]


def entry_ids(owner):
    return {e["id"] for e in owner.ok(owner.get("/api/brain/catalog"))["entries"]}


def test_a_proposal_says_what_it_replaces_and_contradicts(owner, model):
    made = propose(
        model,
        title="Web project length",
        statement="Web design projects run eight to ten weeks from kickoff to launch.",
        topic="facts/services",
        replaces=["facts-services-002"],
        contradicts=["facts-services-001"],
        sources=["brain:rules-style-001"],
    )
    assert made["status"] == "pending"
    review = owner.ok(owner.get("/api/brain/review"))
    (batch,) = review["batches"]
    assert batch["proposer"] == "Claude Code" and batch["proposal_ids"] == [made["proposal_id"]]
    assert batch["counts"]["conflicts"] == 1 and batch["counts"]["clear"] == 0
    (row,) = review["proposals"]
    analysis = row["analysis"]
    assert [e["id"] for e in analysis["replaces"]] == ["facts-services-002"]
    assert "six to eight weeks" in analysis["replaces"][0]["body"]
    assert [e["id"] for e in analysis["conflicts"]] == ["facts-services-001"]
    assert analysis["related"] == [
        {"id": "rules-style-001", "title": analysis["related"][0]["title"], "live": True}
    ]


def test_naming_an_entry_that_does_not_exist_is_refused(model):
    reply = model.tool(
        "propose_brain_entry",
        title="Retainers",
        statement="Retainers renew monthly.",
        evidence="Rate card",
        replaces="no-such-entry",
    )
    proposal = reply["structuredContent"]["proposal"]
    assert proposal["status"] == "refused" and "no-such-entry" in proposal["message"]


def test_a_batch_is_decided_at_once_and_undone_as_one(owner, model):
    first = propose(
        model, title="Web project length", statement="Web design projects run eight to ten weeks."
    )
    second = propose(
        model, title="Motion quotes", statement="Motion work is quoted per finished second."
    )
    done = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "label": "Rate card review",
                "decisions": [
                    {
                        "action": "approve",
                        "proposal_id": first["proposal_id"],
                        "replaces": ["facts-services-002"],
                        "title": "How long web projects run",
                    },
                    {
                        "action": "reject",
                        "proposal_id": second["proposal_id"],
                        "reason": "Not settled",
                    },
                    {"action": "archive", "entry_id": "rules-style-002", "reason": "Outdated"},
                ],
            },
        )
    )
    assert [r["ok"] for r in done["results"]] == [True, True, True]
    point = done["checkpoint"]
    assert point["label"] == "Rate card review"
    ids = entry_ids(owner)
    assert first["entry_id"] in ids
    assert not {"facts-services-002", "rules-style-002"} & ids  # replaced and archived
    new = owner.ok(owner.get(f"/api/brain/entries/{first['entry_id']}"))
    assert new["title"] == "How long web projects run"
    (listed, *_) = owner.ok(owner.get("/api/brain/checkpoints"))
    assert listed["id"] == point["id"] and listed["undoable"] is True

    undone = owner.ok(owner.post(f"/api/brain/checkpoints/{point['id']}/undo"))
    assert undone["undone"] == point["id"]
    ids = entry_ids(owner)
    assert first["entry_id"] not in ids
    assert {"facts-services-002", "rules-style-002"} <= ids
    waiting = {p["id"] for p in owner.ok(owner.get("/api/brain/proposals"))}
    assert waiting == {first["proposal_id"], second["proposal_id"]}
    again = owner.post(f"/api/brain/checkpoints/{point['id']}/undo")
    assert again.status_code == 409


def test_undo_is_refused_when_something_changed_since(owner, model):
    made = propose(
        model, title="Retainer revisions", statement="Retainers include two rounds of revisions."
    )
    point = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={"decisions": [{"action": "approve", "proposal_id": made["proposal_id"]}]},
        )
    )["checkpoint"]
    owner.ok(
        owner.post(
            f"/api/brain/entries/{made['entry_id']}/mark",
            json={"state": "stale", "reason": "Rounds changed"},
        )
    )
    refused = owner.post(f"/api/brain/checkpoints/{point['id']}/undo")
    assert refused.status_code == 409
    body = refused.json()["error"]
    assert "changed since" in body["message"] and body["blocked"]
    assert made["entry_id"] in entry_ids(owner)


def test_only_a_person_decides_or_undoes(owner, model):
    made = propose(model, title="Kickoffs", statement="Kickoffs happen on Mondays.")
    denied = model.post(
        "/api/brain/decisions",
        json={"decisions": [{"action": "approve", "proposal_id": made["proposal_id"]}]},
    )
    assert denied.status_code == 403
    point = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={"decisions": [{"action": "approve", "proposal_id": made["proposal_id"]}]},
        )
    )["checkpoint"]
    assert model.post(f"/api/brain/checkpoints/{point['id']}/undo").status_code == 403


def test_a_bad_decision_changes_nothing(owner, model):
    made = propose(model, title="Kickoffs", statement="Kickoffs happen on Mondays.")
    for body in (
        {"decisions": []},
        {"decisions": [{"action": "publish", "proposal_id": made["proposal_id"]}]},
        {
            "decisions": [
                {"action": "approve", "proposal_id": made["proposal_id"], "topic": "not a topic"}
            ]
        },
    ):
        assert owner.post("/api/brain/decisions", json=body).status_code in (400, 422), body
    assert owner.ok(owner.get("/api/brain/checkpoints")) == []


def test_the_propose_tool_takes_relations_and_a_topic(model):
    tools = {t["name"]: t for t in model.mcp("tools/list")["result"]["tools"]}
    properties = tools["propose_brain_entry"]["inputSchema"]["properties"]
    assert {"replaces", "contradicts", "topic", "revises"} <= set(properties)


def test_a_clash_is_reconciled_by_a_model_and_approved_as_a_pair(owner, model):
    made = propose(
        model,
        title="Web project length",
        statement="Web design projects run eight to ten weeks from kickoff to launch.",
        contradicts=["facts-services-002"],
    )
    task = owner.ok(
        owner.post(
            "/api/brain/reconcile",
            json={
                "proposal_id": made["proposal_id"],
                "entry_id": "facts-services-002",
                "current": "proposal",
                "assignee_id": model.actor_id,
            },
        ),
        201,
    )
    assert (task["template"], task["status"]) == ("reconcile", "ready")
    claimed = model.tool("claim_task", task_id=task["id"])
    brief = claimed["content"][0]["text"]
    assert "eight to ten weeks" in brief  # the proposal, quoted in the instructions
    assert "six to eight weeks" in brief  # the entry, pinned with its text
    assert 'revises="facts-services-002"' in brief
    run_id = claimed["structuredContent"]["run"]["id"]
    suggestion = propose(
        model,
        title="Web design invoicing",
        statement="Web design projects invoice at kickoff and at launch.",
        evidence="Reconciled with the new project length",
        revises="facts-services-002",
        run_id=run_id,
    )
    assert suggestion["entry_id"] == "facts-services-002"
    model.tool("complete_task", run_id=run_id, summary="Kept the invoicing, dropped the length")

    review = owner.ok(owner.get("/api/brain/review"))
    rows = {r["id"]: r for r in review["proposals"]}
    (reconciling,) = rows[made["proposal_id"]]["reconciliations"]
    assert reconciling["suggestion_ids"] == [suggestion["proposal_id"]]
    assert reconciling["current"] == "proposal" and reconciling["status"] == "done"
    assert rows[suggestion["proposal_id"]]["analysis"]["change"] == "update"
    batch = next(b for b in review["batches"] if b["task_id"] == task["id"])
    assert batch["reconciles"]["proposal_id"] == made["proposal_id"]

    done = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "decisions": [
                    {"action": "approve", "proposal_id": made["proposal_id"]},
                    {"action": "approve", "proposal_id": suggestion["proposal_id"]},
                ]
            },
        )
    )
    assert [r["ok"] for r in done["results"]] == [True, True]
    entry = owner.ok(owner.get("/api/brain/entries/facts-services-002"))
    assert "invoice at kickoff" in entry["text"] and "weeks" not in entry["text"]
    assert made["entry_id"] in entry_ids(owner)  # both stand


def test_both_pieces_are_edited_by_hand_and_kept_in_one_undo_point(owner, model):
    made = propose(
        model,
        title="Web project length",
        statement="Web design projects run eight to ten weeks.",
        contradicts=["facts-services-002"],
    )
    before = owner.ok(owner.get("/api/brain/entries/facts-services-002"))["text"]
    mine = "Web design projects run eight to ten weeks, content sprint included."
    done = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "decisions": [
                    {"action": "approve", "proposal_id": made["proposal_id"], "body": mine},
                    {
                        "action": "edit",
                        "entry_id": "facts-services-002",
                        "body": "Web design projects invoice at kickoff and at launch.",
                        "reason": "Project length now has its own entry",
                    },
                ]
            },
        )
    )
    assert [r["ok"] for r in done["results"]] == [True, True]
    new = owner.ok(owner.get(f"/api/brain/entries/{made['entry_id']}"))
    assert new["text"] == mine
    old = owner.ok(owner.get("/api/brain/entries/facts-services-002"))
    assert old["text"] == "Web design projects invoice at kickoff and at launch."
    history = owner.ok(owner.get("/api/brain/entries/facts-services-002/history"))
    assert history[0]["action"] == "edited"
    assert history[0]["reason"] == "Project length now has its own entry"

    owner.ok(owner.post(f"/api/brain/checkpoints/{done['checkpoint']['id']}/undo"))
    assert owner.ok(owner.get("/api/brain/entries/facts-services-002"))["text"] == before
    assert made["entry_id"] not in entry_ids(owner)


def test_a_person_removes_an_entry_and_can_bring_it_back(owner):
    done = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "decisions": [
                    {"action": "archive", "entry_id": "rules-style-002", "reason": "Outdated"}
                ]
            },
        )
    )
    assert "rules-style-002" not in entry_ids(owner)
    assert owner.get("/api/brain/entries/rules-style-002").status_code == 404
    owner.ok(owner.post(f"/api/brain/checkpoints/{done['checkpoint']['id']}/undo"))
    assert "rules-style-002" in entry_ids(owner)


def test_a_change_to_an_unknown_entry_is_refused(model):
    reply = model.tool(
        "propose_brain_entry",
        title="Nothing",
        statement="A change to nothing.",
        evidence="x",
        revises="no-such-entry",
    )
    assert reply["structuredContent"]["proposal"]["status"] == "refused"
