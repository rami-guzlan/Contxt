"""The pre-pass (brain-logic plan 7.2, step 1): what code finds before any model reads."""

from workspace_core.services import prepass

CALL = """This meeting is being recorded.
[00:01] Jordan Lee: We hit 4,200 subscribers on Oct 3, 2026, up 12%.
[00:02] Maya Chen: Send the deck to maya@example.com or call 555-201-8890 by 2026-10-12.
Maya Chen: The card on file is 4111 1111 1111 1111 and her ID is 123-45-6789.
Sent from my iPhone"""


def test_a_transcript_splits_by_speaker_and_its_boilerplate_goes():
    found = prepass.run(CALL)
    assert found.dropped == 2
    assert [(c.kind, c.speaker) for c in found.chunks] == [
        ("turn", "Jordan Lee"),
        ("turn", "Maya Chen"),
        ("turn", "Maya Chen"),
    ]
    assert found.dates == ["Oct 3, 2026", "2026-10-12"]
    assert {"4,200", "12%"} <= set(found.figures)
    assert {"Jordan Lee", "Maya Chen"} <= set(found.names)
    assert found.sensitive == {"email": 1, "phone": 1, "account": 1, "id": 1}
    assert found.summary().startswith("speakers: Jordan Lee, Maya Chen; dates: Oct 3, 2026")


def test_documents_split_by_headings_and_plain_text_by_paragraphs():
    doc = prepass.split("# Pricing\nTwo tiers.\n# Support\nEmail only.")
    assert [c.text.splitlines()[0] for c in doc] == ["# Pricing", "# Support"]
    plain = prepass.split("One.\n\nTwo.\n\n" + "x" * 1600)
    assert [c.kind for c in plain] == ["paragraph", "paragraph"]


def test_what_a_model_reads_is_redacted_only_when_the_preset_says_so():
    shown = prepass.for_model(CALL, redacting=True)
    assert "[email]" in shown and "[phone]" in shown and "[account number]" in shown
    assert "[ID number]" in shown and "maya@example.com" not in shown
    assert "being recorded" not in shown and "iPhone" not in shown
    plain = prepass.for_model(CALL, redacting=False)
    assert "maya@example.com" in plain and "being recorded" not in plain
