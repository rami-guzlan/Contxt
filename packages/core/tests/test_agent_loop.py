"""The knowledge agent's code-run loop (brain-logic plan 17.3), with stand-in models: one
bounded question a step, code checks each answer and runs the tool it names, one retry, at most
six steps, and a hand-up when the answer stays invalid or the steps run out."""

import json

from workspace_core.services import agent_loop


def tools(log):
    def call(name, args):
        log.append((name, args))
        if name == "get_note" and args.get("id") == "voice-guide":
            return "Voice guide: write plainly.", []
        if name == "get_note":
            return None, [f"no note {args.get('id')!r}"]
        return None, [f"no tool {name!r}"]

    return call


def answers(*items):
    queue = [json.dumps(i) if isinstance(i, dict) else i for i in items]
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return queue.pop(0)

    return ask, asked


def test_a_tool_call_then_findings():
    log = []
    ask, asked = answers(
        {"tool": "get_note", "args": {"id": "voice-guide"}},
        {"findings": [{"ref": "c1", "verdict": "merge"}], "summary": "1 merge."},
    )
    job = agent_loop.run("PROMPT", ask, tools(log), action="tidy-repeats")
    assert job.ending == "findings" and job.findings["summary"] == "1 merge."
    assert log == [("get_note", {"id": "voice-guide"})]
    assert "Voice guide: write plainly." in asked[1]
    assert len(job.steps) == 2


def test_an_invalid_answer_is_retried_once_then_handed_up():
    ask, asked = answers("not json", {"tool": "get_note", "args": {"id": "nope"}})
    job = agent_loop.run("PROMPT", ask, tools([]), action="tidy-repeats")
    assert job.ending == "hand-up" and "no note 'nope'" in job.why
    assert "could not be used" in asked[1]


def test_a_retry_that_works_goes_on():
    ask, _ = answers("{}", {"findings": [], "summary": "Nothing."})
    job = agent_loop.run("PROMPT", ask, tools([]), action="tidy-repeats")
    assert job.ending == "findings"


def test_six_steps_and_no_more():
    ask, asked = answers(*[{"tool": "get_note", "args": {"id": "voice-guide"}}] * 7)
    job = agent_loop.run("PROMPT", ask, tools([]), action="tidy-repeats")
    assert job.ending == "hand-up" and "more than 6 steps" in job.why
    assert len(asked) == agent_loop.MAX_STEPS


def test_the_run_record_masks_and_keeps_every_step():
    ask, _ = answers({"tool": "get_note", "args": {"id": "voice-guide"}}, {"findings": []})
    job = agent_loop.run(
        "PROMPT", ask, tools([]), action="x", mask=lambda s: s.replace("plainly", "[x]")
    )
    record = job.record()
    assert record["prompt_version"] == agent_loop.PROMPT_VERSION
    assert [s["tool"] for s in record["steps"]] == ["get_note", None]


def test_the_core_prompt_is_short():
    text = agent_loop.core("- get_note(id): Open one note by id.")
    assert len(text.split()) < 450  # about 600 tokens at most
    assert "never write" in text and "Never invent" in text
