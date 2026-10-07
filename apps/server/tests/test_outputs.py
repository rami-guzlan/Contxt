"""The outputs folder over REST: listed, downloaded, organized without deleting anything, and
each file with what it was made from when the app can know."""

import os


def put(root, rel, text="x"):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def test_the_folder_is_listed_without_its_hidden_files(owner, runtime):
    root = runtime.outputs.root
    put(root, "brief.md", "# Brief")
    put(root, "webinars/deck.pptx")
    put(root, ".secret")
    put(root, "skill-runs/2026-09-28-brand-sheet/.run.json", "{}")
    found = owner.ok(owner.get("/api/outputs"))
    files = {f["path"]: f for f in found["files"]}
    assert set(files) == {"brief.md", "webinars/deck.pptx"}
    assert files["webinars/deck.pptx"]["kind"] == "slides"
    assert files["brief.md"]["kind"] == "document" and files["brief.md"]["folder"] == ""
    assert set(found["folders"]) >= {"webinars", "skill-runs"}


def test_a_file_downloads_and_nothing_outside_is_reachable(owner, runtime, tmp_path):
    put(runtime.outputs.root, "brief.md", "# Brief")
    got = owner.get("/api/outputs/file?path=brief.md")
    assert got.status_code == 200 and got.text == "# Brief"
    assert "attachment" in got.headers["content-disposition"]
    shown = owner.get("/api/outputs/file?path=brief.md&download=false")
    assert "content-disposition" not in shown.headers
    for bad in ("../secret.txt", "..\\\\secret.txt", "/etc/passwd", ".hidden/x"):
        assert owner.get(f"/api/outputs/file?path={bad}").status_code in (404, 422), bad
    assert owner.get("/api/outputs/file?path=none.md").status_code == 404


def test_organizing_makes_folders_and_moves_but_never_overwrites(owner, model, runtime):
    root = runtime.outputs.root
    put(root, "brief.md", "one")
    put(root, "other.md", "two")
    made = owner.ok(owner.post("/api/outputs/folders", json={"path": "Q4/webinars"}), 201)
    assert made["path"] == "Q4/webinars"
    moved = owner.ok(
        owner.post("/api/outputs/move", json={"source": "brief.md", "target": "Q4/webinars"})
    )
    assert moved["path"] == "Q4/webinars/brief.md"
    renamed = owner.ok(
        owner.post(
            "/api/outputs/move",
            json={"source": "Q4/webinars/brief.md", "target": "Q4/webinars/final.md"},
        )
    )
    assert renamed["path"] == "Q4/webinars/final.md"
    clash = owner.post(
        "/api/outputs/move", json={"source": "other.md", "target": "Q4/webinars/final.md"}
    )
    assert clash.status_code == 409
    with open(os.path.join(root, "Q4", "webinars", "final.md"), encoding="utf-8") as handle:
        assert handle.read() == "one"
    bad = owner.post("/api/outputs/folders", json={"path": "a:b"})
    assert bad.status_code == 422
    refused = model.post("/api/outputs/folders", json={"path": "theirs"})
    assert refused.status_code == 403


def test_a_file_a_conversation_saved_shows_what_it_was_given(owner, runtime):
    engine = runtime.ws.rt.brain.brain
    engine.client = "claude-code 2.1.0"
    reply = engine.context("Write the launch email for the web redesign")
    session = reply.data["session_id"]
    path = put(runtime.outputs.root, "launch-email.md", "Hello")
    saved = engine.record_output(path, title="Launch email", session_id=session)
    assert not saved.is_error, saved.text
    found = owner.ok(owner.get("/api/outputs/made-from?path=launch-email.md"))
    assert found["how"] == "chat"
    chat = found["chat"]
    assert chat["app"] == "Claude Code" and chat["title"] == "Launch email"
    (request,) = chat["requests"]
    assert request["request"] == "Write the launch email for the web redesign"
    assert request["got"]
    unknown = put(runtime.outputs.root, "mine.txt")
    assert unknown and owner.ok(owner.get("/api/outputs/made-from?path=mine.txt"))["how"] == (
        "unknown"
    )
