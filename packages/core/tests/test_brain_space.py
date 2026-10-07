"""The Brain as a browsable space: its catalog, files, history, uploads and decisions."""

import pytest

from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.workspace import Workspace


def test_the_whole_brain_is_browsable_without_a_search(ws, owner):
    catalog = ws.brain.catalog(owner)
    assert [a.key for a in catalog.areas] == ["brand"]
    assert catalog.areas[0].topics[0].key == "brand/voice"
    (entry,) = catalog.entries
    assert (entry.id, entry.topic, entry.standing) == ("voice-guide", "brand/voice", True)


def test_files_are_listed_and_served(ws, owner):
    files = ws.brain.files(owner)
    assert [f.path for f in files.references] == ["references/voice.md"]
    assert [s.name for s in files.skills] == ["weekly-posts"]
    content = ws.brain.file_content(owner, "references/voice.md")
    assert content.filename == "voice.md" and content.data.startswith(b"# Voice")
    with pytest.raises(NotFound):
        ws.brain.file_content(owner, "references/missing.md")


def test_an_entry_has_a_history(ws, owner):
    assert ws.brain.history(owner, "voice-guide")[0]["action"] == "approved"
    assert ws.brain.history(owner, "unknown") == []


def test_a_person_uploads_a_file_for_review(ws, owner, brain):
    result = ws.brain.add_file(
        owner,
        filename="brand-book.pdf",
        data=b"%PDF-1.7 brand book",
        title="Brand book",
        description="Logo use and colors",
        topic="brand/visuals",
    )
    assert (result.status, result.proposal_id) == ("pending", "file-1")
    (upload,) = brain.uploaded
    assert upload["topic"] == "brand/visuals" and upload["proposer"].startswith("human:Owner")
    (event,) = ws.events.activity(owner, types=["brain.proposed"])
    assert event.data["kind"] == "file" and event.data["filename"] == "brand-book.pdf"


def test_a_file_filed_at_once_is_an_event_with_its_undo_point(ws, owner, brain):
    brain.file_policy = "apply"
    result = ws.brain.add_file(
        owner,
        filename="Q4 proposal v2.pdf",
        data=b"%PDF-1.7 proposal",
        project="q4-campaign",
        status="Sent",
    )
    assert (result.status, result.checkpoint_id) == ("applied", "cp-1")
    (upload,) = brain.uploaded
    assert (upload["project"], upload["status"], upload["origin"]) == ("q4-campaign", "sent", "app")
    (event,) = ws.events.activity(owner, types=["brain.filed"])
    assert event.data["project"] == "q4-campaign" and event.data["checkpoint"] == "cp-1"
    assert not ws.events.activity(owner, types=["brain.proposed"])


def test_a_models_upload_comes_from_a_chat_and_a_status_is_a_word(ws, owner, connect, brain):
    claude = connect()
    ws.brain.add_file(claude, filename="notes.md", data=b"# Notes")
    assert brain.uploaded[-1]["origin"] == "chat"
    with pytest.raises(ValidationFailed):
        ws.brain.add_file(owner, filename="a.md", data=b"x", status="sent; drop table")


def test_a_person_starts_a_project_and_a_model_cannot(ws, owner, connect, brain):
    made = ws.brain.create_project(
        owner,
        name="  Q4 campaign  proposals ",
        summary="Proposals for the Q4 campaign.",
        aliases=["the campaign proposals", "the campaign proposals", " "],
    )
    assert made.title == "Q4 campaign proposals"
    assert made.aliases == ["the campaign proposals"]  # cleaned and not repeated
    assert [p.id for p in ws.brain.projects(owner)] == [made.id]
    (event,) = ws.events.activity(owner, types=["brain.project_started"])
    assert event.subject_id == made.id
    with pytest.raises(PermissionDenied):
        ws.brain.create_project(connect(), name="Model work", summary="x")
    with pytest.raises(ValidationFailed):
        ws.brain.create_project(owner, name="x" * 81, summary="x")
    with pytest.raises(ValidationFailed):
        ws.brain.create_project(owner, name="Ok", summary="")


def test_a_preview_needs_a_request_and_records_nothing_here(ws, owner, brain):
    shown = ws.brain.preview(
        owner, "  What did my manager say about money?  ", project="q4-campaign"
    )
    assert shown["mode"] == "standard"
    assert brain.previewed == [("What did my manager say about money?", "q4-campaign")]
    with pytest.raises(ValidationFailed):
        ws.brain.preview(owner, "   ")
    with pytest.raises(ValidationFailed):
        ws.brain.preview(owner, "x" * 4001)


def test_an_upload_needs_a_name_and_some_bytes(ws, owner):
    with pytest.raises(ValidationFailed):
        ws.brain.add_file(owner, filename="", data=b"x")
    with pytest.raises(ValidationFailed):
        ws.brain.add_file(owner, filename="empty.txt", data=b"")
    with pytest.raises(ValidationFailed):
        ws.brain.add_file(owner, filename="huge.pdf", data=b"x" * (10 * 1024 * 1024 + 1))


def test_only_a_person_decides_proposals(ws, owner, connect):
    claude = connect()
    made = ws.brain.propose(
        claude, title="Posting days", statement="Post Tue and Thu.", evidence="Calendar"
    )
    with pytest.raises(PermissionDenied):
        ws.brain.decide(claude, made.proposal_id, approve=True)
    result = ws.brain.decide(owner, made.proposal_id, approve=False, reason="Not yet settled")
    assert result["status"] == "rejected"
    (event,) = ws.events.activity(owner, types=["brain.rejected"])
    assert event.subject_id == made.proposal_id and event.reason == "Not yet settled"
    with pytest.raises(NotFound):
        ws.brain.decide(owner, made.proposal_id, approve=True)


def test_a_proposal_made_during_a_run_names_its_task(ws, owner, connect, make_task, brain):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    ws.brain.propose(
        claude,
        title="Posting days",
        statement="Post Tue and Thu.",
        evidence="The calendar",
        sources=["context_item:ctx_1"],
        run_id=run.id,
    )
    assert brain.proposed[-1]["sources"] == [
        "context_item:ctx_1",
        f"task:{task.id}",
        f"run:{run.id}",
    ]
    (event,) = ws.events.activity(owner, types=["brain.proposed"])
    assert (event.data["task_id"], event.data["run_id"]) == (task.id, run.id)
    assert event.project_id == task.project_id
    codex = connect(name="Codex", provider="codex")
    with pytest.raises(PermissionDenied):
        ws.brain.propose(codex, title="Other", statement="Something.", evidence="x", run_id=run.id)


def test_without_a_brain_the_space_is_empty_and_uploads_are_refused(tmp_path, clock):
    ws = Workspace.open(str(tmp_path / "bare"), clock=clock)
    try:
        owner = ws.owner()
        assert ws.brain.catalog(owner).entries == []
        assert ws.brain.files(owner).references == []
        with pytest.raises(Conflict):
            ws.brain.add_file(owner, filename="a.md", data=b"# A")
    finally:
        ws.close()
