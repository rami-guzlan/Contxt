"""Triage (brain-logic plan 7.2, step 2): a cheaper model's answer, read strictly; one that
cannot run, or answers badly, leaves distillation reading everything."""

from workspace_server.models import ModelChoice
from workspace_server.triage import Triage, read_answer

TEXT = "\n".join(
    [
        "Jordan: Morning all.",
        "Maya: Hi. Send it to maya@example.com.",
        "Jordan: We decided the webinar moves to Tuesdays.",
        "Maya: Sign-ups close two days before.",
    ]
)


class Stub:
    """Answers one triage prompt, and keeps what it was asked."""

    def __init__(self, answer):
        self.answer = answer
        self.asked = []
        self.runners = None

    def choose(self, wanted):
        return ModelChoice(wanted, wanted, "cli", True, "here", False)

    def ask(self, who, choice, prompt, *, json_only=False, timeout=240.0, job="agent"):
        self.asked.append((choice.id, prompt, json_only, job))
        return self.answer


def test_an_answer_is_read_strictly():
    assert read_answer('{"keep": [0, 2, 9, "x"]}', 4) == [0, 2]
    assert read_answer('Sure! Here: {"keep": [1]}', 4) == [1]
    assert read_answer("no JSON at all", 4) is None
    assert read_answer('{"parts": [1]}', 4) is None


def test_the_triage_model_reads_numbered_parts_redacted_when_asked():
    stub = Stub('{"keep": [2, 3]}')
    kept = Triage(stub, who=object()).keep("claude", TEXT, redacting=True)
    assert kept == [2, 3]
    (model, prompt, json_only, job) = stub.asked[0]
    assert (model, json_only, job) == ("claude", True, "triage")
    assert "[2] Jordan: We decided the webinar moves to Tuesdays." in prompt
    assert "maya@example.com" not in prompt and "[email]" in prompt


def test_a_short_text_or_a_bad_answer_reads_everything():
    assert Triage(Stub('{"keep": []}'), who=object()).keep("claude", "Just one line.") is None
    assert Triage(Stub("I cannot do that."), who=object()).keep("claude", TEXT) is None
