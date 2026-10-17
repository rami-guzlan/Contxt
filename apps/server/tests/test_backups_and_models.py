"""Backups from the app (made, listed, downloaded; the owner's alone), and the model that matches
by meaning: its status, and a download only when the owner asks."""

import time


def test_a_backup_is_made_listed_and_downloaded(owner, model):
    made = owner.ok(owner.post("/api/backups"), 201)
    assert made["name"].startswith("workspace-") and made["name"].endswith(".zip")
    assert made["records"] > 0 and made["brain_files"] > 0
    (listed,) = owner.ok(owner.get("/api/backups"))
    assert (listed["name"], listed["size"]) == (made["name"], made["size"])
    got = owner.get(f"/api/backups/{made['name']}")
    assert got.status_code == 200 and got.content[:2] == b"PK"
    assert "attachment" in got.headers["content-disposition"]
    assert owner.get("/api/backups/nope.zip").status_code == 404
    assert owner.get("/api/backups/..%5Cworkspace.sqlite").status_code == 404
    assert model.post("/api/backups").status_code == 403
    assert model.get("/api/backups").status_code == 403


def test_the_matching_model_is_fetched_only_when_the_owner_asks(owner, model, runtime, monkeypatch):
    # This test replaces the download itself. Do not mutate process-wide SSL state or
    # make its background-job deadline depend on loading the OS certificate store.
    monkeypatch.setattr("truststore.inject_into_ssl", lambda: None)
    state = owner.ok(owner.get("/api/brain/models"))["matching"]
    assert (state["enabled"], state["present"], state["downloading"]) == (True, False, False)
    assert model.post("/api/brain/models/download").status_code == 403
    fetched = []
    embedder = runtime.ws.rt.brain.brain.embedder

    def download():
        fetched.append(True)
        return {"available": True}

    embedder.download = download  # no network in a test
    started = owner.ok(owner.post("/api/brain/models/download"), 202)["matching"]
    assert started["downloading"] or fetched
    for _ in range(50):
        if fetched and not owner.ok(owner.get("/api/brain/models"))["matching"]["downloading"]:
            break
        time.sleep(0.05)
    assert fetched == [True]
    assert owner.ok(owner.get("/api/brain/models"))["matching"]["error"] is None
