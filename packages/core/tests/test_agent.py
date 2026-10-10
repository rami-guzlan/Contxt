"""The knowledge agent: suggestions made by code, actions whose answers become suggestions in
Catch up and questions for the owner, and a conversation. Nothing changes the Brain on its own."""

import json

import pytest

from workspace_core.errors import NotFound, ValidationFailed

PAIR = {
    "kind": "pair",
    "ids": ["voice-guide", "voice-short"],
    "title": "Voice guide / Voice, short",
    "text": "Note A: `voice-guide` Write plainly.\n\nNote B: `voice-short` Write plainly.",
}
NOTE = {"kind": "note", "ids": ["voice-guide"], "title": "Voice guide", "text": "Stale: ..."}


def answer(*findings, summary=""):
    return "```json\n" + json.dumps({"summary": summary, "findings": list(findings)}) + "\n```"


def test_it_starts_with_claude_and_the_owner_can_choose_another_model(ws, owner):
    seen = ws.agent.overview(owner)
    assert (seen["model"], seen["suggestions"]) == ("claude", True)
    assert [a["id"] for a in seen["actions"]][:2] == ["tidy-repeats", "check-drift"]
    ws.agent.configure(owner, model="ollama:qwen3:1.7b", suggestions=False)
    seen = ws.agent.overview(owner)
    assert (seen["model"], seen["suggestions"]) == ("ollama:qwen3:1.7b", False)
    with pytest.raises(ValidationFailed):
        ws.agent.configure(owner, model="Bad Model!")


def test_suggestions_come_from_the_brain_and_stay_away_once_set_aside(ws, owner, brain):
    brain.watch["recheck"] = [{"id": "voice-guide", "title": "Voice guide", "why": "due"}]
    brain.watch["twins"] = [{"a": "voice-guide", "b": "voice-short", "score": 0.9}]
    found = {s["kind"]: s for s in ws.agent.suggestions(owner)}
    assert found["stale"]["action"] == "freshen-up" and found["stale"]["count"] == 1
    assert found["repeats"]["action"] == "tidy-repeats"
    assert found["gaps"]["action"] == "fill-gaps"  # the fake Brain has one unanswered request
    ws.agent.dismiss(owner, found["stale"]["key"])
    assert "stale" not in {s["kind"] for s in ws.agent.suggestions(owner)}
    # a new stale note changes what it counts, so it comes back
    brain.watch["recheck"].append({"id": "other", "title": "Other", "why": "due"})
    assert "stale" in {s["kind"] for s in ws.agent.suggestions(owner)}
    ws.agent.configure(owner, suggestions=False)
    assert ws.agent.suggestions(owner) == []
    assert ws.agent.suggestions(owner, every=True)


def test_an_action_with_nothing_to_judge_asks_no_model(ws, owner):
    prompt, gathered = ws.agent.action_prompt(owner, "tidy-repeats")
    assert prompt == "" and gathered["candidates"] == []
    with pytest.raises(ValidationFailed):
        ws.agent.action_prompt(owner, "tidy-everything")


def test_the_prompt_carries_the_procedure_the_rules_the_map_and_the_candidates(ws, owner, brain):
    brain.gathered["tidy-repeats"] = [PAIR]
    prompt, gathered = ws.agent.action_prompt(owner, "tidy-repeats")
    assert "# /tidy-repeats" in prompt
    assert "Write plainly." in prompt  # the startup context: the owner's rules
    assert "`voice-guide` Voice guide" in prompt  # the map
    assert "## c1" in prompt and "Note B: `voice-short`" in prompt
    brief, _ = ws.agent.action_prompt(owner, "tidy-repeats", brief=True)
    # The person's rules come with every job, a small model's included (BL 17.2).
    assert "Write plainly." in brief


def test_answers_become_suggestions_in_catch_up_and_questions(ws, owner, brain):
    brain.gathered["tidy-repeats"] = [PAIR]
    brain.gathered["freshen-up"] = [NOTE, {**NOTE, "ids": ["other"], "title": "Other"}]
    _, gathered = ws.agent.action_prompt(owner, "tidy-repeats")
    run = ws.agent.apply_action(
        owner,
        "tidy-repeats",
        gathered,
        answer(
            {"ref": "c1", "verdict": "merge", "keep": "A", "text": "Write plainly.", "why": "Same."}
        ),
        model="claude",
    )
    assert (run["proposed"], run["questions"], run["skipped"]) == (1, 0, 0)
    merged = brain.proposed[-1]
    assert merged["revises"] == "voice-guide" and merged["replaces"] == ["voice-short"]
    assert merged["origin"] == "agent:tidy-repeats"
    assert "knowledge agent" in merged["evidence"]
    _, gathered = ws.agent.action_prompt(owner, "freshen-up")
    run = ws.agent.apply_action(
        owner,
        "freshen-up",
        gathered,
        answer(
            {"ref": "c1", "verdict": "ask", "text": "Is it still plain?", "why": "Due."},
            {"ref": "c2", "verdict": "lasting", "why": "A principle."},
            {"ref": "c9", "verdict": "retire", "why": "Not a candidate."},
            {"ref": "c1", "verdict": "rewrite-everything"},
        ),
        model="ollama:qwen3:1.7b",
    )
    assert (run["questions"], run["fine"], run["skipped"]) == (1, 1, 2)
    (question,) = ws.agent.overview(owner)["questions"]
    assert question["ask"] == "Is it still plain?"
    assert question["target"] == {"type": "note", "id": "voice-guide", "title": "Voice guide"}
    runs = ws.agent.overview(owner)["runs"]
    assert [r["action"] for r in runs] == ["freshen-up", "tidy-repeats"]  # newest first
    assert runs[0]["model"] == "ollama:qwen3:1.7b"


def test_an_answer_that_cannot_be_read_keeps_nothing(ws, owner, brain):
    brain.gathered["check-drift"] = [NOTE]
    _, gathered = ws.agent.action_prompt(owner, "check-drift")
    run = ws.agent.apply_action(owner, "check-drift", gathered, "I think it is fine.", model="x")
    assert (run["proposed"], run["questions"], run["skipped"]) == (0, 0, 1)
    assert "could not be read" in run["notes"][0]
    assert brain.proposed == []


def test_the_owner_acts_on_a_question_in_one_tap(ws, owner, brain):
    brain.gathered["freshen-up"] = [NOTE]
    _, gathered = ws.agent.action_prompt(owner, "freshen-up")
    ws.agent.apply_action(
        owner,
        "freshen-up",
        gathered,
        answer({"ref": "c1", "verdict": "retire", "why": "The event is over."}),
        model="claude",
    )
    (question,) = ws.agent.overview(owner)["questions"]
    assert question["ask"] == "Retire this note?"
    done = ws.agent.answer(owner, question["key"], "retire")
    assert done["checkpoint"]
    (decision,) = brain.batches[-1]["decisions"]
    assert decision["action"] == "archive" and decision["entry_id"] == "voice-guide"
    assert ws.agent.overview(owner)["questions"] == []
    with pytest.raises(NotFound):
        ws.agent.answer(owner, question["key"], "verify")


def test_a_question_answered_in_words_becomes_a_suggested_note(ws, owner, brain):
    brain.gathered["fill-gaps"] = [
        {"kind": "gap", "ids": ["packet:p1"], "title": "Capital?", "text": "Asked: Capital?"}
    ]
    _, gathered = ws.agent.action_prompt(owner, "fill-gaps")
    ws.agent.apply_action(
        owner,
        "fill-gaps",
        gathered,
        answer({"ref": "c1", "verdict": "teach", "text": "What is the capital?", "why": "Asked."}),
        model="claude",
    )
    (question,) = ws.agent.overview(owner)["questions"]
    with pytest.raises(ValidationFailed):
        ws.agent.answer(owner, question["key"], "answer", text=" ")
    with pytest.raises(ValidationFailed):
        ws.agent.answer(owner, question["key"], "retire")  # a gap is not a note
    made = ws.agent.answer(owner, question["key"], "answer", text="Paris. It hosts the office.")
    assert made["proposal_id"] and brain.proposed[-1]["origin"] == "agent:fill-gaps"


def test_a_conversation_reads_the_map_and_what_the_brain_found(ws, owner, brain):
    prompt = ws.agent.chat_prompt(
        owner,
        "What should I tidy first?",
        [{"role": "user", "text": "Hello"}, {"role": "agent", "text": "Hi."}],
    )
    assert "# /knowledge-agent" in prompt
    assert "## Task\n\nWhat should I tidy first?" in prompt  # what the Brain found
    assert "The person: Hello" in prompt and "You: Hi." in prompt
    read = ws.agent.read_chat(
        "Start with the stale notes.\n\n```json\n"
        '{"run": ["freshen-up", "nonsense"], "notes": [{"title": "Plain", "text": '
        '"Write plainly.", "kind": "rule"}, {"text": ""}]}\n```'
    )
    assert read["reply"] == "Start with the stale notes."
    assert read["run"] == ["freshen-up"]
    assert read["notes"] == [{"title": "Plain", "text": "Write plainly.", "kind": "rule"}]
    kept = ws.agent.keep_note(owner, title="Plain", text="Write plainly.", kind="rule", said="x")
    assert kept["proposal_id"] and brain.proposed[-1]["origin"] == "agent:chat"
    with pytest.raises(ValidationFailed):
        ws.agent.chat_prompt(owner, "  ")


def test_words_to_ask_for_a_skill_are_real_phrases_once_each(ws, owner, brain):
    skill = {"kind": "skill", "ids": ["weekly-posts"], "title": "/weekly-posts", "text": "..."}
    brain.gathered["tidy-skills"] = [skill, {**skill, "ids": ["other"], "title": "/other"}]
    _, gathered = ws.agent.action_prompt(owner, "tidy-skills")
    run = ws.agent.apply_action(
        owner,
        "tidy-skills",
        gathered,
        answer(
            {
                "ref": "c1",
                "verdict": "triggers",
                "triggers": ["...", "Draft the week's posts", "draft the week's posts", "ok"],
            },
            {"ref": "c2", "verdict": "triggers", "triggers": ["...", "…"]},
        ),
        model="ollama:qwen3:1.7b",
    )
    assert (run["questions"], run["skipped"]) == (1, 1)  # a small model's placeholder is no answer
    (question,) = ws.agent.overview(owner)["questions"]
    assert question["triggers"] == ["draft the week's posts"]
    assert question["target"] == {"type": "skill", "id": "weekly-posts", "title": "/weekly-posts"}
