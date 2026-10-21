"""Source excerpts retain speaker/date context under the existing word and token limits."""
from types import SimpleNamespace

from brainkit import packets
from brainkit.api import Brain
from tests import fixture


def note(body):
    return SimpleNamespace(body=body, meta={}, summary="A broad conversation.", title="Work", id="x")


def test_a_matching_sentence_keeps_its_speaker_and_conversation_time():
    item = note("Conversation time: 2024/02/03\n\nuser:\nI finished the mural.\n\n"
                "assistant:\nYou could rent the studio. The studio costs $700.")
    found = packets.key_sentence(item, "What does the studio cost?")
    assert "assistant:" in found
    assert "2024/02/03" in found
    assert "studio costs $700" in found
    assert len(found.split()) <= packets.POINTER_WORDS


def test_a_plain_note_retains_the_existing_closest_sentence_behavior():
    found = packets.key_sentence(note("We rent a cabin. The kiln needs six hours."), "kiln")
    assert found == "The kiln needs six hours."


def test_search_returns_a_matching_passage_and_open_preserves_authority():
    vault = fixture.build()
    brain = Brain(vault, embeddings=False)
    try:
        made = brain.propose(layer="facts", topic="services", scope="person:alex",
                             text="General workshop notes. The ceramic kiln needs six hours.",
                             extra={"said_by": "agent"}, force_pending=True)
        assert not made.is_error, made.text
        assert not brain.approve(made.data["proposal_id"]).is_error
        ident = made.data["id"]
        result = brain.search("ceramic kiln")
        row = next(r for r in result.data["hits"] if r["id"] == ident)
        assert "kiln needs six hours" in row["excerpt"]
        assert row["said_by"] == "agent"
        opened = brain.note(ident)
        assert "Said by: agent" in opened.text
        assert "Said by: owner" not in opened.text
    finally:
        brain.close()
        fixture.remove(vault)

def test_mcp_exposes_historical_reads_and_passes_the_flag():
    from unittest.mock import Mock
    from brainkit import mcp_server
    tools = {t["name"]: t for t in mcp_server.AGENT_TOOLS}
    for name in ("notes_get", "notes_search"):
        assert tools[name]["inputSchema"]["properties"]["include_archived"]["type"] == "boolean"
    brain = Mock()
    mcp_server.HANDLERS["notes_get"](brain, {"id": "old", "include_archived": True})
    brain.note.assert_called_once_with("old", session_id=None, include_archived=True,
                                            full=False)


def test_an_explicit_archived_read_keeps_the_original_instead_of_its_successor():
    vault = fixture.build()
    brain = Brain(vault, embeddings=False)
    try:
        for ident, body, extra in (
            ("original-room", "The pottery room is Bay seven.",
             {"status": "archived", "superseded_by": "current-room"}),
            ("current-room", "The pottery room is now Bay nine.", {}),
        ):
            meta, body = fixture.note(ident, "facts", "services", "person:alex", body, **extra)
            brain.vault.write_note(f"knowledge/test/{ident}.md", meta, body)
        ident = "original-room"
        assert "Bay seven" in brain.note(ident, include_archived=True).text
        assert "Bay nine" in brain.note(ident).text
    finally:
        brain.close()
        fixture.remove(vault)
