"""The answer grader sees only evidence the reader actually received."""
import json

import pytest

from brainkit import answer_eval as ae


def case():
    return {
        "question": "Where did the crate start?",
        "as_of": "2024-02-10",
        "reference": "Bay seven",
        "kind": "knowledge-update",
        "answer": "It started in Bay seven; it is now in Bay nine.",
        "citations": [{"id": "origin", "quote": "The crate is in Bay seven."}],
        "evidence": [
            {"id": "origin", "text": "Recorded 2024-01-02\nuser: The crate is in Bay seven."},
            {"id": "later", "text": "Recorded 2024-02-09\nuser: It is now in Bay nine."},
        ],
        "method": "must not influence judging",
        "previous_grade": False,
        "hidden_notes": {"secret": "Never shown to the reader"},
    }


def test_judge_receives_the_question_time_and_cited_speaker_context():
    prepared = ae.prepare(case())
    assert prepared["as_of"] == "2024-02-10"
    assert prepared["cited_evidence"][0]["text"].startswith("Recorded 2024-01-02\nuser:")
    assert prepared["cited_evidence"][0]["quotes"] == ["The crate is in Bay seven."]


def test_a_judge_never_receives_method_previous_verdict_or_hidden_evidence():
    prepared = ae.prepare(case())
    encoded = json.dumps(prepared)
    assert "must not influence" not in encoded
    assert "previous_grade" not in encoded
    assert "Never shown" not in encoded
    assert "Bay nine." not in json.dumps(prepared["cited_evidence"])


def test_a_quote_cannot_borrow_identical_text_from_another_note():
    row = case()
    row["evidence"][0]["text"] = "An excerpt that omits the location."
    row["evidence"][1]["text"] = "The crate is in Bay seven."
    with pytest.raises(ValueError, match="visible"):
        ae.prepare(row)


def test_hidden_text_is_not_made_visible_just_because_the_id_was_named():
    row = case()
    row["evidence"][0]["text"] = "origin: Open the location record to read it."
    row["hidden_notes"]["origin"] = "The crate is in Bay seven."
    with pytest.raises(ValueError, match="visible"):
        ae.prepare(row)


def test_citation_whitespace_may_differ_but_words_cannot():
    row = case()
    row["citations"][0]["quote"] = "The crate\nis in   Bay seven."
    ae.prepare(row)
    row["citations"][0]["quote"] = "The crate is in Bay eight."
    with pytest.raises(ValueError):
        ae.prepare(row)


def test_visible_context_is_not_truncated_before_the_decisive_sentence():
    row = case()
    row["evidence"][0]["text"] = "Background. " * 500 + row["evidence"][0]["text"]
    assert len(ae.prepare(row)["cited_evidence"][0]["text"]) > 5000


def test_duplicate_source_ids_and_empty_quotes_are_rejected():
    row = case()
    row["evidence"].append(dict(row["evidence"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        ae.prepare(row)
    row = case()
    row["citations"][0]["quote"] = " "
    with pytest.raises(ValueError, match="quote"):
        ae.prepare(row)


def test_no_citation_abstention_is_sent_to_the_grader_without_auto_credit():
    row = case()
    row.update(answer="The supplied evidence does not establish that.", citations=[], kind="abstention")
    prepared = ae.prepare(row)
    assert prepared["cited_evidence"] == []
    assert "correct" not in prepared
    assert "optional" in prepared["rubric"]


def test_historical_question_wording_has_priority_over_a_category_name():
    assert "initial" in ae.prepare(case())["rubric"]
    assert "question" in ae.prepare(case())["rubric"]


def test_personalization_does_not_require_every_optional_reference_detail():
    row = case()
    row["kind"] = "single-session-preference"
    assert "not every" in ae.prepare(row)["rubric"]


def test_uncertainty_and_partial_totals_are_scored_separately():
    row = case()
    row["kind"] = "temporal-reasoning"
    prepared = ae.prepare(row)
    assert "intermediate steps" in prepared["rubric"]
    assert "incomplete total" in ae.INSTRUCTIONS
    assert "uncertainty" in ae.INSTRUCTIONS


@pytest.mark.parametrize("verdict", [
    {"correct": "false", "grounded": True, "reason": "Not a boolean"},
    {"correct": True, "grounded": 1, "reason": "Not a boolean"},
    {"correct": True, "grounded": True, "reason": ""},
    {"correct": True, "grounded": True, "reason": "x", "method": "extra"},
])
def test_malformed_verdicts_cannot_be_coerced_into_passes(verdict):
    with pytest.raises(ValueError):
        ae.verdict(verdict)


def test_correctness_and_support_are_independent_and_invalid_rows_stay_in_denominator():
    summary = ae.summarize([
        {"correct": True, "grounded": False, "reason": "Unsupported guess"},
        {"correct": False, "grounded": True, "reason": "Safe but incomplete"},
        None,
    ])
    assert summary == {"total": 3, "valid": 2, "correct": 1, "grounded": 1, "correct_and_grounded": 0}


def test_preparing_a_case_never_changes_the_stored_record():
    row = case()
    before = json.dumps(row, sort_keys=True)
    ae.prepare(row)
    assert json.dumps(row, sort_keys=True) == before
