"""Brain versions through the app: Save version, the list, a diff and restore."""


def test_save_version_diff_and_restore_through_the_api(owner, brain_vault):
    import os
    import subprocess

    top = os.path.dirname(brain_vault)
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A", "--", os.path.basename(brain_vault)],
        ["-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", "start"],
    ):
        subprocess.run(["git", *args], cwd=top, check=True, capture_output=True)
    made = owner.ok(owner.post("/api/brain/versions", json={"note": "before testing"}), 201)
    assert made["version"]["name"] == "v1"
    listed = owner.ok(owner.get("/api/brain/versions"))["versions"]
    assert [v["name"] for v in listed] == ["v1"]
    diff = owner.ok(owner.get("/api/brain/versions/v1/diff/HEAD"))
    assert diff["changed"] == [] and diff["added"] == []
    missing = owner.post("/api/brain/versions/v9/restore", json={})
    assert missing.status_code == 404
