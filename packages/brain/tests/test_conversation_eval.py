"""Public fixture conversion must not create retrieval gains by losing evidence."""
import copy

import pytest

from brainkit.conversation_eval import convert


def fixture():
    return {
        "haystack_session_ids": ["answer_secret", "answer_secret"],
        "haystack_dates": ["2024/01/02", "2024/02/03 09:00"],
        "haystack_sessions": [
            [{"role": "user", "content": "Where is the crate?"},
             {"role": "assistant", "content": "Background. " * 500 + "Bay seven.",
              "has_answer": True}],
            [{"role": "assistant", "content": "Try Bay eight."},
             {"role": "user", "content": "No, it is now in Bay nine."}],
        ],
        "answer_session_ids": ["answer_secret"],
    }


def test_duplicate_sessions_keep_every_turn_and_long_reply_with_speaker_and_date():
    notes, labels = convert(fixture())
    assert len(notes) == len({n["id"] for n in notes}) == 3
    assert len(notes[0]["body"]) > 5000
    assert "assistant:\n" in notes[0]["body"] and notes[0]["body"].endswith("Bay seven.")
    assert notes[2]["body"].startswith("Conversation time: 2024/02/03 09:00")
    assert "user:\nNo," in notes[2]["body"]
    assert len(labels["session_groups"][0]) == 3


def test_annotation_and_answer_session_names_cannot_change_retrieval_inputs():
    row = fixture()
    notes, _ = convert(row)
    changed = copy.deepcopy(row)
    changed["haystack_session_ids"] = ["neutral", "neutral"]
    changed["answer_session_ids"] = ["neutral"]
    for turns in changed["haystack_sessions"]:
        for turn in turns:
            turn["has_answer"] = not turn.get("has_answer", False)
    assert convert(changed)[0] == notes
    assert "answer_secret" not in str(notes)


def test_absent_turn_annotations_remain_an_explicit_empty_required_group():
    row = fixture()
    for turns in row["haystack_sessions"]:
        for turn in turns:
            turn.pop("has_answer", None)
    _, labels = convert(row)
    assert labels["missing_turn_labels"] == 1
    assert labels["annotated_turn_groups"] == [[]]


@pytest.mark.parametrize("problem", ["date", "alignment", "missing-session", "speaker"])
def test_invalid_history_is_not_silently_repaired(problem):
    row = fixture()
    if problem == "date":
        row["haystack_dates"][0] = "2024/02/31"
    elif problem == "alignment":
        row["haystack_dates"].pop()
    elif problem == "missing-session":
        row["answer_session_ids"].append("absent")
    else:
        row["haystack_sessions"][0][0]["role"] = "unknown"
    with pytest.raises(ValueError):
        convert(row)
