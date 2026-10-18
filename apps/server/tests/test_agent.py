"""The knowledge agent end to end, with a stand-in model: an action's answer becomes a
suggestion in Catch up and a question with buttons; the conversation offers actions and notes;
the model is the owner's choice among the ones that can answer here."""

import json
import os
import sys
import time

import pytest

from workspace_core.errors import Conflict, ValidationFailed
from workspace_server.knowledge_agent import AgentWork
from workspace_server.models import ModelChoice, Models
from workspace_server.runners import Runners

FAKE_OTHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_other_cli.py")

BRAIN_PACKAGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "brain")
)
if BRAIN_PACKAGE not in sys.path:
    sys.path.insert(0, BRAIN_PACKAGE)

from tests import fixture as brain_fixture  # noqa: E402

CHOICES = [
    ModelChoice("claude", "Claude Code (your CLI)", "cli", True, "here", False),
    ModelChoice("ollama:tiny", "tiny (local)", "local", True, "local", True),
]


class StubModels(Models):
    """Answers from a list, and remembers what it was asked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def list(self):
        return list(CHOICES)

    def ask(self, who, choice, prompt, *, json_only=False, timeout=240.0, job="agent"):
        self.asked.append({"model": choice.id, "prompt": prompt, "json": json_only})
        return self.answers.pop(0)


def stub(runtime, *answers):
    models = StubModels(answers)
    runtime.models = models
    runtime.agent = AgentWork(runtime.ws, models)
    return models


def add_note(vault, note_id, body, **extra):
    from brainkit.vault import Vault

    meta, text = brain_fixture.note(note_id, "rules", "style", "company", body, **extra)
    v = Vault(vault)
    levels = brain_fixture.BRAIN["structure"]["scope_levels"]
    kinds = brain_fixture.BRAIN["structure"]["partition_kinds"]
    v.write_note(v.note_path(meta, levels, kinds), dict(meta), text)


def finish(owner, job_id, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = owner.ok(owner.get(f"/api/brain/agent/jobs/{job_id}"))
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def test_the_page_names_the_model_the_map_and_the_procedures(owner, runtime):
    stub(runtime)
    page = owner.ok(owner.get("/api/brain/agent"))
    assert page["model"] == "claude" and [m["id"] for m in page["models"]] == [
        "claude",
        "ollama:tiny",
    ]
    assert page["actions"][0]["id"] == "tidy-repeats"
    outline = owner.ok(owner.get("/api/brain/agent/map"))
    assert "`rules-style-002`" in outline["text"]
    assert "facts-sam-001" not in outline["text"]  # someone else's private note stays out
    skills = owner.ok(owner.get("/api/brain/agent/skills"))
    assert [s["name"] for s in skills][:2] == ["knowledge-agent", "tidy-repeats"]
    page = owner.ok(owner.put("/api/brain/agent/settings", json={"model": "ollama:tiny"}))
    assert page["model"] == "ollama:tiny"
    missing = owner.put("/api/brain/agent/settings", json={"model": "ollama:gone"})
    assert missing.status_code == 409


def test_an_action_merges_repeats_into_a_suggestion_that_waits_in_catch_up(
    owner, runtime, brain_vault
):
    add_note(
        brain_vault,
        "rules-style-009",
        "Headlines use sentence case, stay under nine words, and state one benefit.",
    )
    answer = {
        "summary": "One pair says the same thing.",
        "findings": [
            {
                "ref": "c1",
                "verdict": "merge",
                "keep": "A",
                "text": "Headlines use sentence case, stay under nine words, state one benefit.",
                "why": "Both say the same.",
            }
        ],
    }
    models = stub(runtime, json.dumps(answer))
    job = owner.ok(owner.post("/api/brain/agent/actions/tidy-repeats", json={}), 201)
    done = finish(owner, job["id"])
    assert done["status"] == "done", done
    assert done["result"]["proposed"] == 1 and done["result"]["model"] == "claude"
    (asked,) = models.asked
    assert asked["json"] and "rules-style-009" in asked["prompt"]
    waiting = owner.ok(owner.get("/api/brain/proposals"))
    merged = next(p for p in waiting if p["id"] == done["result"]["proposals"][0])
    assert "sentence case" in merged["body"]
    runs = owner.ok(owner.get("/api/brain/agent"))["runs"]
    assert runs[0]["summary"] == "One pair says the same thing."


def test_a_question_retires_a_note_in_one_tap(owner, runtime, brain_vault):
    add_note(
        brain_vault,
        "rules-style-008",
        "The 2025 holiday card is due December 1.",
        valid_until="2025-12-01",
    )
    stub(
        runtime,
        json.dumps({"findings": [{"ref": "c1", "verdict": "retire", "why": "It is over."}]}),
    )
    job = owner.ok(owner.post("/api/brain/agent/actions/freshen-up", json={}), 201)
    done = finish(owner, job["id"])
    assert done["result"]["questions"] == 1, done
    (question,) = owner.ok(owner.get("/api/brain/agent"))["questions"]
    assert question["target"]["id"] == "rules-style-008"
    owner.ok(
        owner.post(
            "/api/brain/agent/questions/answer", json={"key": question["key"], "do": "retire"}
        )
    )
    assert owner.get("/api/brain/entries/rules-style-008").status_code == 404  # retired
    rows = {r["id"]: r for r in owner.ok(owner.get("/api/brain/inventory"))}
    assert rows["rules-style-008"]["live"] is False
    assert owner.ok(owner.get("/api/brain/agent"))["questions"] == []


def test_nothing_to_judge_asks_no_model(owner, runtime):
    models = stub(runtime)
    job = owner.ok(owner.post("/api/brain/agent/actions/tidy-repeats", json={}), 201)
    done = finish(owner, job["id"])
    assert done["result"]["summary"] == "Nothing to check right now."
    assert models.asked == []
    unknown = owner.post("/api/brain/agent/actions/tidy-everything", json={})
    assert unknown.status_code == 422


def test_a_conversation_offers_actions_and_notes_to_keep(owner, runtime):
    reply = (
        "Start with the stale notes.\n\n```json\n"
        '{"run": ["freshen-up"], "notes": [{"title": "Reviews on Fridays", '
        '"text": "Client reviews happen on Fridays.", "kind": "fact"}]}\n```'
    )
    models = stub(runtime, reply)
    job = owner.ok(
        owner.post(
            "/api/brain/agent/chat",
            json={
                "message": "What should I tidy first?",
                "history": [{"role": "user", "text": "Hi"}, {"role": "agent", "text": "Hello."}],
                "model": "ollama:tiny",
            },
        ),
        201,
    )
    done = finish(owner, job["id"])
    assert done["result"]["reply"] == "Start with the stale notes."
    assert done["result"]["run"] == ["freshen-up"]
    (asked,) = models.asked
    assert asked["model"] == "ollama:tiny" and not asked["json"]
    assert "The person: Hi" in asked["prompt"]
    note = done["result"]["notes"][0]
    kept = owner.ok(owner.post("/api/brain/agent/notes", json={**note, "said": "tidy"}), 201)
    assert kept["status"] == "pending" and kept["proposal_id"]


def test_local_models_come_from_ollama_and_their_thinking_is_left_out(runtime):
    calls = []

    def fetch(url, body=None, *, timeout=2.0):
        calls.append((url, body))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen3:1.7b", "size": 1_400_000_000}]}
        return {"message": {"content": '<think>hmm</think>{"findings": []}'}}

    models = Models(runtime.runners, ollama_url="http://local", fetch=fetch)
    local = next(m for m in models.list() if m.kind == "local")
    assert (local.id, local.brief) == ("ollama:qwen3:1.7b", True)
    owner = runtime.ws.owner()
    assert models.ask(owner, local, "Judge.", json_only=True) == '{"findings": []}'
    assert calls[-1][0] == "http://local/api/chat" and calls[-1][1]["format"] == "json"

    def down(url, body=None, *, timeout=2.0):
        raise OSError("refused")

    assert [m.kind for m in Models(runtime.runners, fetch=down).list()] == ["cli"] * 3


def test_the_agent_runs_on_any_cli_here_and_starts_on_the_first_one_signed_in(runtime):
    """Claude Code, Codex and Gemini CLI are all choices; with none chosen, the agent uses the
    first one here that can answer, and any model the CLI offers can be named."""
    from brainkit import models_client

    def none(url, body=None, *, timeout=2.0):
        raise OSError("no Ollama here")

    gemini_only = Runners(
        runtime.ws,
        runtime.templates,
        base_url="http://127.0.0.1:8787",
        resolve=lambda spec: [sys.executable, FAKE_OTHER, spec.id] if spec.id == "gemini" else None,
    )
    models = Models(gemini_only, fetch=none, service=models_client.Status, settings=lambda: {})
    assert [m.id for m in models.list()] == ["claude", "codex", "gemini"]
    assert [m.available for m in models.list()] == [False, False, True]
    assert models.default() == "gemini"
    named = models.choose("gemini:gemini-2.5-flash")
    assert (named.id, named.kind) == ("gemini:gemini-2.5-flash", "cli")
    assert "gemini-2.5-flash" in named.label
    seen = json.loads(models.ask(runtime.ws.owner(), named, "Judge.", json_only=True))
    assert seen["argv"][seen["argv"].index("--model") + 1] == "gemini-2.5-flash"
    assert seen["prompt"].endswith("Judge.")
    with pytest.raises(Conflict, match="Not installed"):
        models.choose("codex")
    with pytest.raises(ValidationFailed):
        models.choose("gemini:two words")
    nothing = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=lambda s: None
    )
    alone = Models(nothing, fetch=none, service=models_client.Status, settings=lambda: {})
    assert alone.default() == "claude"  # nothing can answer here: the usual first choice


def test_the_pinned_local_model_is_the_default_when_it_is_here(runtime):
    from brainkit import models_client

    service = models_client.Status(
        url="http://127.0.0.1:1",
        ready=True,
        roles={"agent": {"model": "qwen3.5-4b", "verified": True, "loaded": True}},
    )
    asked = []

    class Agent:
        def __init__(self, found):
            self.found = found

        def generate(self, prompt, *, schema=None, max_tokens=800, timeout=240.0):
            asked.append((prompt, schema))
            return {
                "text": '<think>hmm</think>{"findings": []}',
                "usage": {"tokens_in": 120, "tokens_out": 9},
                "latency_ms": 40,
            }

    def none(url, body=None, *, timeout=2.0):
        raise OSError("no Ollama here")

    models = Models(
        runtime.runners, fetch=none, service=lambda: service, agent=Agent, settings=lambda: {}
    )
    assert models.default() == "local:qwen3.5-4b"
    pinned = models.list()[0]
    assert (pinned.id, pinned.kind, pinned.brief) == ("local:qwen3.5-4b", "pinned", True)
    claude = next(m for m in models.list() if m.id == "claude")
    # With a local model here, Claude Code is the person's opt-in.
    assert not claude.available and claude.detail.startswith("Off for the knowledge agent")
    owner = runtime.ws.owner()
    assert models.ask(owner, pinned, "Judge.", json_only=True) == '{"findings": []}'
    assert asked == [("Judge.", {"type": "object"})]
    opted = Models(
        runtime.runners,
        fetch=none,
        service=lambda: service,
        agent=Agent,
        settings=lambda: {"agent_claude_code": True},
    )
    claude = next(m for m in opted.list() if m.id == "claude")
    assert not claude.detail.startswith("Off for the knowledge agent")
    no_cli = Runners(
        runtime.ws, runtime.templates, base_url="http://127.0.0.1:8787", resolve=lambda s: None
    )
    gone = Models(no_cli, fetch=none, service=models_client.Status, settings=lambda: {})
    assert gone.default() == "claude"  # no local model here: Claude Code, as before
    assert [m.kind for m in gone.list()] == ["cli"] * 3


def test_suggestions_and_setting_one_aside(owner, runtime, brain_vault):
    stub(runtime)
    add_note(
        brain_vault,
        "rules-style-008",
        "The 2025 holiday card is due December 1.",
        valid_until="2025-12-01",
    )
    found = {s["kind"]: s for s in owner.ok(owner.get("/api/brain/agent/suggestions"))}
    assert found["stale"]["action"] == "freshen-up"
    owner.ok(
        owner.post("/api/brain/agent/suggestions/dismiss", json={"key": found["stale"]["key"]}),
        204,
    )
    kinds = {s["kind"] for s in owner.ok(owner.get("/api/brain/agent/suggestions"))}
    assert "stale" not in kinds


ASKED = json.dumps(
    {
        "asked_as": [
            "how should this sound",
            "what tone do we use here",
            "rules for writing this up",
        ],
        "applies_when": "writing anything for a client",
        "not_when": "internal notes",
        "role": "style",
    }
)


def test_the_agent_writes_how_waiting_entries_are_asked_for(owner, runtime):
    waiting = owner.ok(owner.get("/api/brain/agent/enrich"))["waiting"]
    assert waiting >= 3
    models = stub(runtime, ASKED, ASKED)
    job = owner.ok(owner.post("/api/brain/agent/enrich", json={"limit": 2}), 201)
    done = finish(owner, job["id"])
    assert done["status"] == "done", done
    assert done["result"]["enriched"] == 2 and done["result"]["left"] == waiting - 2
    assert all(a["json"] for a in models.asked) and len(models.asked) == 2
    rows = owner.ok(owner.get("/api/brain/inventory"))
    found = [r for r in rows if r.get("asked_as")]
    assert len(found) == 2
    assert found[0]["applies_when"] == "writing anything for a client"
    assert found[0]["enriched"]


def test_an_inflight_model_answer_cannot_overwrite_the_owners_new_retrieval_lines(
    owner, runtime, monkeypatch
):
    brain = runtime.ws.rt.brain.brain
    item = brain.enrichment_pending(1)[0]
    models = stub(runtime, ASKED)
    lines = ["the owner's new way of asking for this entry"]

    def edit_then_answer(*args, **kwargs):
        result = brain.set_asked_as(item["id"], lines, actor=brain.state().config.owner)
        assert not result.is_error
        return ASKED

    monkeypatch.setattr(models, "ask", edit_then_answer)
    job = owner.ok(owner.post("/api/brain/agent/enrich", json={"limit": 1}), 201)
    done = finish(owner, job["id"])
    assert done["result"]["enriched"] == 0
    assert "changed" in done["result"]["failed"][0]["why"]
    assert brain.state().index.note(item["id"]).asked_as == lines


def test_unusable_answers_stop_the_job_and_say_why(owner, runtime):
    models = stub(runtime, "No JSON here.", "Still none.", "Nope.", ASKED)
    job = owner.ok(owner.post("/api/brain/agent/enrich", json={"limit": 5}), 201)
    done = finish(owner, job["id"])
    assert done["status"] == "failed"
    assert len(done["result"]["failed"]) == 3 and len(models.asked) == 3
    assert "could not be used" in done["error"]


def test_the_owner_rewords_how_an_entry_is_asked_for(owner, runtime):
    entry = owner.ok(owner.get("/api/brain/inventory"))[0]["id"]
    lines = ["who signs off on a client post", "approval before publishing"]
    owner.ok(owner.put(f"/api/brain/entries/{entry}/asked-as", json={"lines": lines}))
    details = owner.ok(owner.get(f"/api/brain/entries/{entry}/details"))
    assert details["asked_as"] == lines
    missing = owner.post(f"/api/brain/entries/{entry}/accept-triggers")
    assert missing.status_code == 404


class _Agent:
    def __init__(self):
        self.started = []

    def start_enrich(self, who, *, limit=None):
        self.started.append(limit)

        class Job:
            status = "running"

        return Job()


def test_the_worker_enriches_new_entries_only_with_a_chosen_model(runtime, monkeypatch):
    from workspace_server.worker import Worker

    agent = _Agent()
    worker = Worker(runtime.ws, agent=agent)
    monkeypatch.setattr(runtime.ws.agent, "chosen_model", lambda: "")
    worker.tick()
    assert agent.started == []  # no model chosen: nothing spent
    monkeypatch.setattr(runtime.ws.agent, "chosen_model", lambda: "claude")
    worker._enrich_at = None
    worker.tick()
    assert agent.started == [10]
    worker._enrich_at = None
    worker.tick()  # the batch is still running: not a second one
    assert agent.started == [10]


def test_the_worker_learns_from_use_without_a_model(runtime, monkeypatch):
    from workspace_server.worker import Worker

    calls = []
    monkeypatch.setattr(runtime.ws.rt.brain, "learn_from_use", lambda: calls.append(1) or {})
    worker = Worker(runtime.ws)
    worker.tick()
    worker.tick()  # not an hour yet
    assert calls == [1]


def test_worker_cadences_start_at_zero_uptime_and_wait_for_each_interval(runtime, monkeypatch):
    from types import SimpleNamespace
    from workspace_server import worker as module

    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock.now))
    calls = {"goals": 0, "learn": 0}

    def goals(who):
        calls["goals"] += 1
        return []

    def learn():
        calls["learn"] += 1
        return {}

    monkeypatch.setattr(runtime.ws.goals, "run_checks", goals)
    monkeypatch.setattr(runtime.ws.rt.brain, "learn_from_use", learn)
    monkeypatch.setattr(runtime.ws.agent, "chosen_model", lambda: "claude")
    agent = _Agent()
    worker = module.Worker(runtime.ws, agent=agent)
    worker.tick()
    assert calls == {"goals": 1, "learn": 1}
    assert agent.started == [10]
    worker.tick()
    assert calls == {"goals": 1, "learn": 1}
    assert agent.started == [10]
    worker._enrich_job.status = "done"
    clock.now = module.ENRICH_SECONDS - 1
    worker.tick()
    assert agent.started == [10]
    clock.now = module.ENRICH_SECONDS
    worker.tick()
    assert agent.started == [10, 10]
    assert calls == {"goals": 1, "learn": 1}
    clock.now = module.GOAL_CHECK_SECONDS
    worker.tick()
    assert calls == {"goals": 2, "learn": 1}
    clock.now = module.LEARN_SECONDS
    worker.tick()
    assert calls == {"goals": 3, "learn": 2}
    assert agent.started == [10, 10]  # active batch still prevents duplicate work
