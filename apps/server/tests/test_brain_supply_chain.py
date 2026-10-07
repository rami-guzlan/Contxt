"""The context supply chain over REST, end to end on the sample Brain: the inventory, an
entry's versions and putting one back, its details, policy, where entries went (AI work
included), and gaps."""

ENTRY = "facts-services-002"


def decide(owner, *decisions, label=None):
    body = {"decisions": list(decisions)}
    if label:
        body["label"] = label
    result = owner.ok(owner.post("/api/brain/decisions", json=body))
    assert all(r["ok"] for r in result["results"]), result
    return result


def test_the_inventory_lists_what_the_owner_may_see_with_its_details(owner):
    rows = {r["id"]: r for r in owner.ok(owner.get("/api/brain/inventory"))}
    row = rows[ENTRY]
    assert (row["owner"], row["owner_set"], row["live"]) == ("person:alex", False, True)
    assert row["uses"] == {"total": 0, "d7": 0, "d30": 0, "last": None}
    assert rows["facts-services-000"]["live"] is False  # archived entries are listed too
    assert "facts-clients-acme-001" in rows  # a partition the owner owns
    assert "facts-sam-001" not in rows  # someone else's own scope
    assert {rows["brand-sheet"]["type"], rows["references/style-guide.md"]["type"]} == {
        "skill",
        "reference",
    }
    assert owner.get("/api/brain/entries/facts-sam-001/details").status_code == 404


def test_an_entry_goes_back_to_an_earlier_version(owner):
    original = owner.ok(owner.get(f"/api/brain/entries/{ENTRY}"))["text"]
    decide(owner, {"action": "edit", "entry_id": ENTRY, "body": "Projects take a while."})
    versions = owner.ok(owner.get(f"/api/brain/entries/{ENTRY}/versions?text=true"))
    assert [v["body"] for v in versions] == ["Projects take a while.", original]
    done = decide(
        owner,
        {"action": "restore", "entry_id": ENTRY, "ref": versions[1]["ref"], "reason": "lost"},
    )
    assert done["checkpoint"]["label"] == "Restored 1"
    assert owner.ok(owner.get(f"/api/brain/entries/{ENTRY}"))["text"] == original
    events = owner.ok(owner.get(f"/api/brain/activity?entry={ENTRY}"))
    assert [e["action"] for e in events[:2]] == ["restored", "edited"]
    assert events[0]["title"] and "previous" not in events[0]
    owner.ok(owner.post(f"/api/brain/checkpoints/{done['checkpoint']['id']}/undo"))
    assert owner.ok(owner.get(f"/api/brain/entries/{ENTRY}"))["text"] == "Projects take a while."


def test_details_change_without_the_text_and_wrong_ones_are_refused(owner):
    decide(
        owner,
        {
            "action": "update",
            "entry_id": ENTRY,
            "fields": {"owner": "person:sam", "review_days": "60", "classification": "public"},
        },
    )
    row = owner.ok(owner.get(f"/api/brain/entries/{ENTRY}/details"))
    assert (row["owner"], row["review_days"], row["classification"]) == ("person:sam", 60, "public")
    refused = owner.post(
        "/api/brain/decisions",
        json={"decisions": [{"action": "update", "entry_id": ENTRY, "fields": {"kind": "rule"}}]},
    )
    assert refused.status_code == 422
    bad = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "decisions": [
                    {"action": "update", "entry_id": ENTRY, "fields": {"review_days": "soon"}}
                ]
            },
        )
    )
    assert bad["results"][0]["ok"] is False and "number of days" in bad["results"][0]["message"]


def test_an_archived_entry_comes_back(owner):
    decide(owner, {"action": "unarchive", "entry_id": "facts-services-000", "reason": "true"})
    rows = {r["id"]: r for r in owner.ok(owner.get("/api/brain/inventory"))}
    assert rows["facts-services-000"]["live"] is True


def test_policy_is_read_changed_and_checked(owner, model):
    policy = owner.ok(owner.get("/api/brain/policies"))
    assert (policy["review_days"], policy["retention_days"]) == ({}, 90)
    changed = owner.ok(
        owner.client.put(
            "/api/brain/policies",
            json={"review_days": {"facts": 180}, "retention_days": 60},
            headers=owner.headers,
        )
    )
    assert changed["policy"]["review_days"] == {"facts": 180}
    assert owner.ok(owner.get(f"/api/brain/entries/{ENTRY}/details"))["review_days"] == 180
    refused = owner.client.put(
        "/api/brain/policies", json={"retention_days": 0}, headers=owner.headers
    )
    assert refused.status_code == 422
    denied = model.client.put(
        "/api/brain/policies", json={"retention_days": 30}, headers=model.headers
    )
    assert denied.status_code == 403


def test_ai_work_counts_as_use(owner, model, make_task):
    task = make_task(
        model.actor_id,
        title="Write the services page",
        purpose="Say what the studio offers and how long web design projects run",
        instructions="Draft the services page from what the studio offers.",
    )
    claim = model.tool("claim_task", task_id=task["id"])["structuredContent"]
    entries = claim["packet"]["brain"]["entries"]
    assert entries, claim["packet"]["brain"]
    entry = entries[0]["id"]
    use = owner.ok(owner.get(f"/api/brain/entries/{entry}/use"))
    (handout,) = [r for r in use["recent"] if r["via"] == "work"]
    assert handout["work"]["title"] == "Write the services page"
    assert use["totals"]["in_work"] == 1
    row = next(r for r in owner.ok(owner.get("/api/brain/inventory")) if r["id"] == entry)
    assert row["uses"]["d7"] == 1
    assert owner.get(f"/api/brain/entries/{entry}/recall").status_code == 404  # outputs went


def test_the_flow_and_the_gaps_of_the_week(owner, model):
    model.tool(
        "propose_brain_entry",
        title="Retainers",
        statement="Retainers renew monthly.",
        kind="fact",
        evidence="Rate card",
    )
    flow = owner.ok(owner.get("/api/brain/flow"))
    assert (flow["came_in"], flow["waiting"]) == (1, 1)
    assert flow["stock"]["live"] > 0
    assert owner.ok(owner.get("/api/brain/gaps")) == []
    assert (
        owner.client.post(
            "/api/brain/gaps/dismiss", json={"key": "packet:x"}, headers=owner.headers
        ).status_code
        == 204
    )
