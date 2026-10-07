"""Notes: a person's private scratchpad, with versions, until they add a note to the Brain."""

from datetime import timedelta

import pytest

from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.services.notes import first_line


def test_a_new_note_is_named_by_its_first_line_until_someone_names_it(ws, owner):
    note = ws.notes.create(owner)
    assert (note.title, note.body, note.revision) == ("Untitled note", "", 1)
    saved = ws.notes.save(owner, note.id, body="## Q4 *campaign* ideas\n\nLinkedIn video first.")
    assert saved.title == "Q4 campaign ideas"
    renamed = ws.notes.save(owner, note.id, title="Campaign ideas")
    assert renamed.title == "Campaign ideas"
    assert ws.notes.save(owner, note.id, body="Something else.").title == "Campaign ideas"
    assert first_line("- [x] [Brief](http://x) **due**\n") == "Brief due"


def test_saves_join_the_version_until_a_pause_or_another_hand(ws, owner, clock):
    note = ws.notes.create(owner, title="Plan", body="One.")
    ws.notes.save(owner, note.id, body="One. Two.")
    assert ws.notes.get(owner, note.id).revision == 1  # still the version being written
    clock.advance(timedelta(minutes=11))
    later = ws.notes.save(owner, note.id, body="One. Two. Three.")
    assert later.revision == 2
    versions = ws.notes.versions(owner, note.id)
    assert [(v.revision, v.current, v.body) for v in versions] == [
        (2, True, None),
        (1, False, None),
    ]
    assert ws.notes.version(owner, note.id, 1).body == "One. Two."
    with pytest.raises(NotFound):
        ws.notes.version(owner, note.id, 9)
    unchanged = ws.notes.save(owner, note.id, body="One. Two. Three.")
    assert unchanged.revision == 2


def test_naming_a_version_seals_it_and_restoring_is_a_new_version(ws, owner):
    note = ws.notes.create(owner, title="Plan", body="Draft one.")
    ws.notes.name_version(owner, note.id, "  Sent to Jordan ")
    (named,) = ws.notes.versions(owner, note.id)
    assert (named.label, named.sealed) == ("Sent to Jordan", True)
    after = ws.notes.save(owner, note.id, body="Draft two.")
    assert after.revision == 2  # a sealed version is never written into
    restored = ws.notes.restore(owner, note.id, 1)
    assert (restored.revision, restored.body) == (3, "Draft one.")
    assert ws.notes.versions(owner, note.id)[0].label == "Restored version 1"
    with pytest.raises(ValidationFailed):
        ws.notes.name_version(owner, note.id, "   ")
    with pytest.raises(NotFound):
        ws.notes.restore(owner, note.id, 42)


def test_archived_notes_are_set_aside_and_cannot_be_written(ws, owner):
    note = ws.notes.create(owner, title="Old plan", body="x")
    ws.notes.archive(owner, note.id)
    assert ws.notes.list(owner) == []
    assert [n.id for n in ws.notes.list(owner, archived=True)] == [note.id]
    with pytest.raises(Conflict):
        ws.notes.save(owner, note.id, body="y")
    ws.notes.archive(owner, note.id, archived=False)
    assert ws.notes.save(owner, note.id, body="y").body == "y"


def test_search_finds_notes_by_every_word_titles_first(ws, owner):
    ws.notes.create(owner, title="Budget", body="LinkedIn video keeps its money.")
    ws.notes.create(owner, title="LinkedIn video plan", body="Two cuts.")
    found = ws.notes.search(owner, "linkedin video")
    assert [n.title for n in found] == ["LinkedIn video plan", "Budget"]
    assert ws.notes.search(owner, "podcast") == []
    assert ws.notes.search(owner, " ") == []


def test_notes_are_private_from_models_until_work_pins_them(ws, owner, connect):
    claude = connect()
    note = ws.notes.create(owner, title="Salary thoughts", body="Ask for a raise in March.")
    assert ws.notes.list(claude) == []
    with pytest.raises(NotFound):
        ws.notes.get(claude, note.id)
    with pytest.raises(PermissionDenied):
        ws.context.get(claude, note.id)
    assert ws.context.search(claude, "raise") == []
    assert ws.context.search(owner, "raise") == []  # notes are searched through Notes
    ws.distill.request(owner, item_ids=[note.id], assignee_id=claude.actor_id)
    assert ws.notes.get(claude, note.id).body == "Ask for a raise in March."
    assert ws.context.get(claude, note.id).id == note.id
    other = connect(name="Codex", provider="codex")
    with pytest.raises(PermissionDenied):
        ws.context.get(other, note.id)  # pinned for Claude's work, not Codex's


def test_only_people_write_notes(ws, owner, connect):
    claude = connect()
    note = ws.notes.create(owner, title="Plan", body="x")
    with pytest.raises(PermissionDenied):
        ws.notes.create(claude, title="Mine")
    ws.distill.request(owner, item_ids=[note.id], assignee_id=claude.actor_id)
    with pytest.raises(PermissionDenied):
        ws.notes.save(claude, note.id, body="Changed by a model")


def test_adding_a_note_to_the_brain_files_it_as_a_document(ws, owner, brain):
    note = ws.notes.create(owner, title="Q4 Campaign: proposal", body="Lead with outcomes.")
    brain.file_policy = "apply"
    filed = ws.notes.to_brain(owner, note.id, project="q4-campaigns", status=" Draft ")
    assert filed.status == "applied"
    (sent,) = brain.uploaded
    assert sent["filename"] == "q4-campaign-proposal.md"
    assert sent["data"] == b"# Q4 Campaign: proposal\n\nLead with outcomes.\n"
    assert (sent["project"], sent["status"], sent["origin"]) == ("q4-campaigns", "draft", "app")
    (event,) = ws.events.activity(owner, subject_id=note.id, types=["note.filed"])
    assert (event.data["status"], event.data["project"]) == ("applied", "q4-campaigns")


def test_a_note_goes_to_the_brain_only_with_something_in_it(ws, owner, connect):
    empty = ws.notes.create(owner, title="Later")
    with pytest.raises(ValidationFailed):
        ws.notes.to_brain(owner, empty.id)
    note = ws.notes.create(owner, title="Plan", body="x")
    with pytest.raises(ValidationFailed):
        ws.notes.to_brain(owner, note.id, status="not a status!")
    with pytest.raises(PermissionDenied):
        ws.notes.to_brain(connect(), note.id)
