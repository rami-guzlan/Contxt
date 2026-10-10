"""Settings, On this computer, Local models (brain-logic plan 5.11.16): the machine and its
setup, each role's pinned options, the guard rails and the knowledge agent's Claude Code
opt-in, with no model service and no network (each test keeps its own model home)."""

import time

from brainkit import machine

LAPTOP = {
    "machine": {
        "ram_gb": 15.8,
        "gpu": "",
        "gpu_gb": 0.0,
        "apple_silicon": False,
        "system": "Windows",
    },
    "setup": "laptop",
}


def act(owner, **body):
    return owner.post("/api/brain/local-models", json=body)


def test_the_page_shows_the_machine_its_setup_and_each_role(owner, model):
    machine.save(dict(LAPTOP))
    found = owner.ok(owner.get("/api/brain/local-models"))
    assert (found["enabled"], found["setup"], found["setup_label"]) == (True, "laptop", "Laptop")
    roles = {r["role"]: r for r in found["roles"]}
    assert (roles["decide"]["model"], roles["agent"]["model"]) == ("kev-0.8b", "qwen3.5-4b")
    assert found["ram_in_use_gb"] == 5.6
    # The meaning index's model is kept with the Brain, downloaded under Matching by meaning.
    meaning = {o["name"]: o for o in roles["embed"]["options"]}["bge-small-en-v1.5"]
    assert meaning["with_brain"] is True
    assert found["engine"]["ready"] is False  # no model service in a test
    assert len(found["fallbacks"]) == 2  # Kev-0.8B has qualified for neither step here
    # No local agent model here yet: Claude Code stays the agent until the person says no.
    assert (found["agent_claude_code"], found["agent_claude_code_set"]) == (True, False)
    assert act(model, action="check").status_code == 403


def test_the_guard_rails_refuse_with_the_reason(owner):
    machine.save(dict(LAPTOP))
    too_big = act(owner, action="default", name="qwen3.6-35b-a3b")
    assert too_big.status_code == 422 and "will not fit" in too_big.text
    unpinned = act(owner, action="download", name="qwen3-reranker-0.6b")
    assert unpinned.status_code == 422 and "not pinned yet" in unpinned.text
    in_use = act(owner, action="remove", name="qwen3.5-4b")
    assert in_use.status_code == 422 and "in use here" in in_use.text
    untimed = act(owner, action="speed")
    assert untimed.status_code == 422 and "no model service" in untimed.text
    assert act(owner, action="default", name="a-model-nobody-pinned").status_code == 422
    assert act(owner, action="default").status_code == 422  # which model?
    made = owner.ok(act(owner, action="default", name="ms-marco-minilm-l-6-v2"))
    roles = {r["role"]: r for r in made["roles"]}
    assert roles["rerank"]["model"] == "ms-marco-minilm-l-6-v2"


def test_a_download_is_verified_against_the_lock(owner, monkeypatch):
    machine.save(dict(LAPTOP))
    fetched = []
    monkeypatch.setattr(machine, "_fetch", lambda pin, cache: fetched.append(pin.name))
    owner.ok(act(owner, action="download", name="bge-small-en-v1.5"))
    found = owner.ok(owner.get("/api/brain/local-models"))
    for _ in range(100):
        if not found["downloading"]:
            break
        time.sleep(0.05)
        found = owner.ok(owner.get("/api/brain/local-models"))
    assert fetched == ["bge-small-en-v1.5"]
    # Nothing real arrived, so nothing matches the lock's checksums: it is not used.
    assert "does not match the lock" in found["errors"]["bge-small-en-v1.5"]


def test_claude_code_for_the_agent_is_the_persons_choice(owner):
    machine.save(dict(LAPTOP))
    found = owner.ok(act(owner, action="claude_code", on=False))
    assert (found["agent_claude_code"], found["agent_claude_code_set"]) == (False, True)
    page = owner.ok(owner.get("/api/brain/agent"))
    claude = next(m for m in page["models"] if m["id"] == "claude")
    assert claude["available"] is False
    assert claude["detail"].startswith("Off for the knowledge agent")
    found = owner.ok(act(owner, action="claude_code", on=True))
    assert found["agent_claude_code"] is True
