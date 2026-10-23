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
