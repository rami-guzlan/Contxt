"""Ask the Brain first over REST: install needs the person's yes, says where it wrote, and
removing leaves the rest of the file (Release 1 plan, M08)."""

import os


def test_ask_the_brain_first_is_installed_with_a_yes_and_removed(owner, runtime):
    listed = owner.ok(owner.get("/api/connections/instructions"))
    assert {r["app"] for r in listed} == {"claude-code", "codex", "gemini"}
    assert not any(r["installed"] for r in listed)
    refused = owner.post("/api/connections/instructions/claude-code", json={})
    assert refused.status_code == 422
    done = owner.ok(
        owner.post("/api/connections/instructions/claude-code", json={"confirmed": True})
    )
    assert done["installed"] and done["path"].startswith(runtime.home)
    assert os.path.isfile(os.path.join(runtime.home, ".claude", "CLAUDE.md"))
    gone = owner.ok(owner.delete("/api/connections/instructions/claude-code"))
    assert gone["installed"] is False
