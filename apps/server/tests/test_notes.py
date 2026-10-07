"""Notes over REST: write, version, set aside, download, and add a note to the Brain."""

from datetime import timedelta


def test_a_note_is_written_saved_and_versioned(owner, clock):
    note = owner.ok(owner.post("/api/notes", json={}), 201)
    assert note["title"] == "Untitled note"
    saved = owner.ok(owner.put(f"/api/notes/{note['id']}", json={"body": "# Q4 ideas\n\nVideo."}))
    assert (saved["title"], saved["revision"]) == ("Q4 ideas", 1)
    clock.advance(timedelta(minutes=11))
    later = owner.ok(owner.put(f"/api/notes/{note['id']}", json={"body": "# Q4 ideas\n\nAudio."}))
    assert later["revision"] == 2
    owner.ok(owner.post(f"/api/notes/{note['id']}/name", json={"label": "Sent to Jordan"}))
    versions = owner.ok(owner.get(f"/api/notes/{note['id']}/versions"))
    assert [(v["revision"], v["label"]) for v in versions] == [(2, "Sent to Jordan"), (1, None)]
    assert all(v["body"] is None for v in versions)
    first = owner.ok(owner.get(f"/api/notes/{note['id']}/versions/1"))
    assert first["body"] == "# Q4 ideas\n\nVideo."
    back = owner.ok(owner.post(f"/api/notes/{note['id']}/restore", json={"revision": 1}))
    assert (back["revision"], back["body"]) == (3, "# Q4 ideas\n\nVideo.")
    listed = owner.ok(owner.get("/api/notes"))
    assert [n["id"] for n in listed] == [note["id"]] and listed[0]["body"] is None


def test_a_note_is_set_aside_and_downloaded(owner, note):
    owner.ok(owner.post(f"/api/notes/{note['id']}/archive"))
    assert owner.ok(owner.get("/api/notes")) == []
    assert [n["id"] for n in owner.ok(owner.get("/api/notes?archived=true"))] == [note["id"]]
    assert owner.put(f"/api/notes/{note['id']}", json={"body": "x"}).status_code == 409
    owner.ok(owner.post(f"/api/notes/{note['id']}/unarchive"))
    download = owner.get(f"/api/notes/{note['id']}/download")
    assert download.text == "# Client notes\n\nClients prefer async reviews on Fridays.\n"
    assert 'filename="Client notes.md"' in download.headers["content-disposition"]
    assert owner.get("/api/notes/ctx_missing").status_code == 404


def test_a_note_goes_into_a_brain_project_as_a_file(owner, note):
    project = owner.ok(
        owner.post(
            "/api/brain/projects",
            json={"name": "Client care", "summary": "How we work with clients"},
        ),
        201,
    )
    filed = owner.ok(
        owner.post(
            f"/api/notes/{note['id']}/brain", json={"project": project["id"], "status": "draft"}
        ),
        201,
    )
    assert filed["status"] == "applied" and filed["project"] == project["id"]
    files = owner.ok(owner.get(f"/api/brain/projects/{project['id']}"))["files"]
    assert [f["title"] for f in files] == ["Client notes"]
    preview = owner.ok(
        owner.get(
            "/api/brain/preview",
            params={"request": "When do clients like reviews?", "project": project["id"]},
        )
    )
    assert "Fridays" in preview["text"]
    empty = owner.ok(owner.post("/api/notes", json={"title": "Later"}), 201)
    assert owner.post(f"/api/notes/{empty['id']}/brain", json={}).status_code == 422
