"""Agents over REST, end to end on the sample Brain: written and saved (the owner's change, kept
as agents/<name>/AGENT.md), checked, assembled from what each pointer is now, given an operating
prompt by the chosen model (a stand-in here; nothing is saved until the owner says), asked for
something as a run like a skill run, archived, and added to Claude Code as a subagent that
always fetches the current version."""

import json
import os
import time

from workspace_server.knowledge_agent import AgentWork
from workspace_server.models import ModelChoice, Models


class StubModels(Models):
    """Answers from a list, and remembers what it was asked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def list(self):
        return [ModelChoice("claude", "Claude Code (your CLI)", "cli", True, "here", False)]

    def ask(self, who, choice, prompt, *, json_only=False, timeout=240.0, job="agent"):
        self.asked.append({"model": choice.id, "prompt": prompt, "json": json_only})
        return self.answers.pop(0)


def stub(runtime, *answers):
    models = StubModels(answers)
    runtime.models = models
    runtime.agent = AgentWork(runtime.ws, models)
    return models


def finish(owner, job_id, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = owner.ok(owner.get(f"/api/brain/agent/jobs/{job_id}"))
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


ROLE = {
    "name": "case-writer",
    "role": "Writes the studio's case studies from finished projects.",
    "responsibilities": ["Draft one case study a month"],
    "skills": ["brand-sheet"],
    "library": ["references/style-guide.md"],
    "context": ["rules/style"],
    "projects": ["state-focus-studio-podcast"],
    "output_shape": "A one-page case study in Markdown.",
    "prompt": "You write case studies the way a senior designer explains their work to a peer.",
}


def make(owner, **changes):
    return owner.ok(owner.post("/api/agents", json=dict(ROLE, **changes)), 201)


def test_an_agent_is_saved_in_the_brain_and_assembled_from_its_pointers(owner, brain_vault):
    made = make(owner)
    assert made["checkpoint"]
    assert made["agent"]["role"] == ROLE["role"]
    assert made["resolved"]["broken"] == []
    prompt = made["prompt"]
    assert "# You are working as case-writer" in prompt and ROLE["prompt"] in prompt
    assert "/brand-sheet" in prompt and "references/style-guide.md" in prompt
    assert os.path.isfile(os.path.join(brain_vault, "agents", "case-writer", "AGENT.md"))
    listed = owner.ok(owner.get("/api/agents"))
    assert [(a["name"], a["last_run"]) for a in listed] == [("case-writer", None)]


def test_a_wrong_role_is_refused_with_the_brains_words(owner):
    assert owner.post("/api/agents", json=dict(ROLE, name="Case Writer")).status_code == 422
    empty = owner.post("/api/agents", json=dict(ROLE, role=""))
    assert empty.status_code == 422 and "role" in empty.text
    runner = owner.post("/api/agents", json=dict(ROLE, runner="gpt"))
    assert runner.status_code == 422 and "runner" in runner.text
    make(owner)
    assert owner.post("/api/agents", json=ROLE).status_code == 409


def test_the_model_writes_its_prompt_and_nothing_is_saved_until_the_owner_says(owner, runtime):
    answer = {
        "prompt": "You plan one case study a month.",
        "questions": ["Which projects count as finished?"],
    }
    models = stub(runtime, json.dumps(answer))
    body = {k: v for k, v in ROLE.items() if k != "prompt"}
    job = owner.ok(owner.post("/api/agents/prompt", json=body), 201)
    done = finish(owner, job["id"])
    assert done["status"] == "done", done
    assert done["result"] == {
        "prompt": "You plan one case study a month.",
        "questions": ["Which projects count as finished?"],
    }
    (asked,) = models.asked
    assert asked["json"] is True
    assert "operating prompt" in asked["prompt"]  # the procedure that ships with the engine
    assert ROLE["role"] in asked["prompt"] and "/brand-sheet: " in asked["prompt"]
    assert owner.ok(owner.get("/api/agents")) == []


def test_asking_an_agent_queues_a_run_that_opens_with_its_role(owner):
    make(owner)
    task = owner.ok(
        owner.post(
            "/api/agents/case-writer/run", json={"ask": "A case study of the podcast project."}
        ),
        201,
    )
    assert task["title"] == "Ask case-writer" and task["template"] == "skill"
    assert "You are working as the agent case-writer" in task["instructions"]
    assert "# You are working as case-writer" in task["instructions"]
    assert "references/style-guide.md" in task["instructions"]
    assert (
        task["instructions"].rstrip().endswith("A case study of the podcast project.")
        or "A case study of the podcast project." in task["instructions"]
    )
    (run,) = owner.ok(owner.get("/api/agents/case-writer/runs"))
    assert (run["agent"], run["ask"], run["skills"]) == (
        "case-writer",
        "A case study of the podcast project.",
        ["brand-sheet"],
    )
    listed = owner.ok(owner.get("/api/agents"))
    assert listed[0]["last_run"]["task_id"] == task["id"]


def test_a_change_is_a_new_version_and_archiving_hides_it(owner):
    make(owner)
    changed = owner.ok(
        owner.put("/api/agents/case-writer", json=dict(ROLE, role="Writes short case studies."))
    )
    assert changed["agent"]["role"] == "Writes short case studies."
    assert owner.ok(owner.get("/api/agents/case-writer/versions"))
    owner.ok(owner.delete("/api/agents/case-writer"))
    assert owner.ok(owner.get("/api/agents")) == []
    assert [a["status"] for a in owner.ok(owner.get("/api/agents?archived=true"))] == ["archived"]
    refused = owner.post("/api/agents/case-writer/run", json={"ask": "Anything."})
    assert refused.status_code == 422 and "archived" in refused.text


def test_claude_code_gets_a_subagent_that_fetches_the_current_version(owner, tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    make(owner)
    written = owner.ok(owner.post("/api/agents/case-writer/claude-code"))
    assert written["path"] == str(tmp_path / ".claude" / "agents" / "case-writer.md")
    text = (tmp_path / ".claude" / "agents" / "case-writer.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: case-writer\n")
    assert 'get_agent tool with name "case-writer"' in text
    assert ROLE["prompt"] not in text  # never a copy: it fetches the current version
