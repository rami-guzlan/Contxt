"""The Release 1 routes the redesigned app reads: Taste, learned rules, the Brain map, the
new governance settings, and Scout (Release 1 plan, M03 and M08)."""

import os


def test_taste_is_written_and_read_by_lens(owner):
    made = owner.ok(
        owner.post(
            "/api/brain/taste", json={"text": "Say the thing in the headline.", "lens": "works"}
        ),
        201,
    )
    assert made["status"] in ("pending", "applied")
    bad = owner.post("/api/brain/taste", json={"text": "Bold", "lens": "looks", "kind": "pair"})
    assert bad.status_code == 422
    found = owner.ok(owner.get("/api/brain/taste"))
    assert set(found["lenses"]) == {"looks", "feels", "works"}


def test_the_map_and_learned_rules_are_readable(owner):
    found = owner.ok(owner.get("/api/brain/map"))
    assert found["pages"] >= 1 and isinstance(found["lines"], list)
    assert owner.ok(owner.get("/api/brain/learned")) == []
    assert owner.delete("/api/brain/learned/learned-nope").status_code == 404


def test_the_release_1_governance_settings_change_through_the_policy(owner):
    policy = owner.ok(owner.get("/api/brain/policies"))
    assert policy["retrieval_policy"] == "standard" and policy["auto_daily_cap"] == 50
    changed = owner.ok(
        owner.put(
            "/api/brain/policies",
            json={
                "retrieval_policy": "careful",
                "auto_daily_cap": 20,
                "standing": [{"type": "fact", "origin": "chat", "area": "*"}],
            },
        )
    )
    assert changed["policy"]["retrieval_policy"] == "careful"
    assert changed["policy"]["standing"][0]["type"] == "fact"
    bad = owner.put("/api/brain/policies", json={"retrieval_policy": "loose"})
    assert bad.status_code == 422


def test_scout_finds_new_and_changed_files_and_stays_quiet_on_saves_and_renames(owner, tmp_path):
    folder = tmp_path / "Clients"
    folder.mkdir()
    (folder / "brief.md").write_text("Northwind wants the pilot in March.", encoding="utf-8")
    (folder / "photo.png").write_bytes(b"not a document")
    assert owner.post("/api/scout/scan").status_code == 422  # no folder yet
    owner.ok(owner.put("/api/scout", json={"folders": [{"path": str(folder)}]}))
    first = owner.ok(owner.post("/api/scout/scan"))
    assert [d["kind"] for d in first["differences"]] == ["new"]
    assert first["last_inspection"]
    again = owner.ok(owner.post("/api/scout/scan"))  # nothing changed: nothing new
    assert len(again["differences"]) == 1 and not [d for d in again["found"] if not d.get("quiet")]
    diff = first["differences"][0]
    brought = owner.ok(owner.post(f"/api/scout/differences/{diff['id']}/bring-in"), 201)
    assert brought["capture_id"]
    os.rename(folder / "brief.md", folder / "pilot brief.md")
    renamed = owner.ok(owner.post("/api/scout/scan"))
    assert [d["kind"] for d in renamed["found"]] == ["renamed"] and not renamed["differences"]
    (folder / "pilot brief.md").write_text("Northwind wants the pilot in April.", encoding="utf-8")
    changed = owner.ok(owner.post("/api/scout/scan"))
    assert [d["kind"] for d in changed["differences"]] == ["changed"]
    root = owner.put("/api/scout", json={"folders": [{"path": os.path.abspath(os.sep)}]})
    assert root.status_code == 422


def test_a_proposal_kept_in_another_home_from_the_app_keeps_its_source(owner):
    made = owner.ok(
        owner.post(
            "/api/brain/proposals",
            json={
                "title": "Write plainly",
                "statement": "Headlines say the thing plainly.",
                "kind": "rule",
                "evidence": "the owner said so",
            },
        ),
        201,
    )
    pid = made.get("proposal_id") or made["proposal"]["proposal_id"]
    done = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "decisions": [
                    {
                        "action": "approve",
                        "proposal_id": pid,
                        "destination": {
                            "destination": "taste",
                            "lens": "works",
                            "kind": "principle",
                        },
                    }
                ]
            },
        )
    )
    assert done["results"][0]["ok"], done
    taste = owner.ok(owner.get("/api/brain/taste"))
    assert any("plainly" in e["text"] for e in taste["lenses"]["works"])


def test_governed_or_auto_and_a_manual_pause_are_policy_settings(owner):
    assert owner.ok(owner.get("/api/brain/policies"))["mode"] == "governed"
    changed = owner.ok(owner.put("/api/brain/policies", json={"mode": "auto", "auto_paused": True}))
    assert (changed["policy"]["mode"], changed["policy"]["auto_paused"]) == ("auto", True)
    assert owner.put("/api/brain/policies", json={"mode": "chaos"}).status_code == 422


def test_waiting_proposals_say_what_they_are_and_where_they_came_from(owner):
    owner.ok(
        owner.post(
            "/api/brain/proposals",
            json={
                "title": "Studio hours",
                "statement": "The studio opens at nine.",
                "kind": "fact",
                "evidence": "the owner said so",
            },
        ),
        201,
    )
    (row,) = owner.ok(owner.get("/api/brain/proposals"))
    assert "capture" in row and "origin" in row


def test_signing_in_by_post_keeps_the_key_out_of_the_address(client, owner_token):
    bad = client.post("/auth/login", json={"token": "wst_wrong"}, headers={"X-Workspace-CSRF": "1"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "unauthenticated"
    good = client.post(
        "/auth/login", json={"token": owner_token}, headers={"X-Workspace-CSRF": "1"}
    )
    assert good.status_code == 204 and good.cookies


def test_the_map_view_lore_sections_and_session_search_are_readable(owner):
    view = owner.ok(owner.get("/api/brain/map/view"))
    assert view["text"].startswith("## Brain map · partial")
    assert view["tokens"] <= view["limit"] == 250
    assert isinstance(view["sealed"], int) and "levels" in view
    whole = owner.ok(owner.get("/api/brain/map", params={"tier": "levels"}))
    assert whole["tier"] == "levels" and len(whole["lines"]) == 5
    assert owner.get("/api/brain/map", params={"tier": "nope"}).status_code == 422
    made = owner.ok(
        owner.post(
            "/api/brain/lore",
            json={
                "title": "Two exports, one slide",
                "story": "The slide quoted the older export.",
                "pattern": "A number without the version it came from.",
                "words": ["registrations", "total"],
            },
        ),
        201,
    )
    assert made["status"] in ("pending", "applied")
    assert isinstance(owner.ok(owner.get("/api/brain/lore")), list)
    assert owner.get("/api/brain/open", params={"address": "never-was#x"}).status_code == 404
    assert owner.get("/api/brain/sections/never-was").status_code == 404
    assert owner.ok(owner.get("/api/brain/sessions/search", params={"q": "lighthouse"})) == []


def test_the_owner_sets_the_pull_budget_through_the_policy(owner):
    policy = owner.ok(owner.get("/api/brain/policies"))
    assert (policy["pull_items"], policy["pull_tokens"]) == (2, 1500)
    changed = owner.ok(
        owner.put("/api/brain/policies", json={"pull_items": 3, "pull_tokens": 3000})
    )
    assert (changed["policy"]["pull_items"], changed["policy"]["pull_tokens"]) == (3, 3000)
