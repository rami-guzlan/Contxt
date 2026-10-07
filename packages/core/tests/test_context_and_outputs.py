"""Working context, artifacts, exports, bundles, and distilling into the Brain."""

import io
import json
import zipfile

import pytest

from workspace_core.errors import (
    Conflict,
    InvalidTransition,
    PermissionDenied,
    ValidationFailed,
)


def test_capture_text_links_and_files(ws, owner, project):
    scope = f"project:{project.id}"
    note = ws.context.capture(owner, scope=scope, body="# Event notes\nKeynote went well")
    assert note.title == "Event notes" and note.revision == 1
    link = ws.context.capture(owner, scope=scope, kind="link", url="https://example.com/a")
    assert link.title == "https://example.com/a"
    upload = ws.context.capture(
        owner, scope=scope, kind="document", data=b"Brand voice: warm", filename="voice.txt"
    )
    assert upload.mime == "text/plain" and upload.text_shadow == "Brand voice: warm"
    again = ws.context.capture(
        owner,
        scope=f"project:{project.id}",
        kind="document",
        data=b"Brand voice: warm",
        filename="copy.txt",
    )
    assert again.object_key == upload.object_key  # the bytes are stored once
    with pytest.raises(ValidationFailed):
        ws.context.capture(owner, scope=scope)
    with pytest.raises(ValidationFailed):
        ws.context.capture(owner, scope="galaxy:far", body="x")


def test_audio_waits_for_a_transcript_and_binaries_for_an_extractor(ws, owner, project):
    memo = ws.context.capture(
        owner, scope=f"project:{project.id}", kind="audio", data=b"RIFF....", filename="memo.wav"
    )
    assert memo.shadow_status == "pending"
    image = ws.context.capture(
        owner, scope=f"project:{project.id}", kind="image", data=b"\x89PNG", filename="logo.png"
    )
    assert image.shadow_status == "unavailable"


def test_items_keep_their_revisions(ws, owner, project):
    item = ws.context.capture(owner, scope=f"project:{project.id}", title="Calendar", body="Oct 14")
    ws.context.update(owner, item.id, body="Oct 21")
    ws.context.update(owner, item.id, labels=["events"])  # labels are not a new revision
    history = ws.context.revisions(owner, item.id)
    assert [(h["revision"], h["body"]) for h in history] == [(1, "Oct 14"), (2, "Oct 21")]


def test_search_covers_active_and_archived_items(ws, owner, project):
    item = ws.context.capture(
        owner, scope=f"project:{project.id}", title="Webinar recap", body="Attendance was strong"
    )
    ws.context.archive(owner, item.id)
    assert ws.context.search(owner, "webinar") == []
    found = ws.context.search(owner, "webinar attendance", include_archived=True)
    assert [i.id for i in found] == [item.id]


def test_ideas_have_a_light_lifecycle_and_promote_into_tasks(ws, owner, project, connect):
    claude = connect()
    idea = ws.context.capture(
        owner, scope=f"project:{project.id}", kind="idea", body="A carousel on AI myths"
    )
    assert idea.idea_state == "captured"
    ws.context.set_idea_state(owner, idea.id, "developing")
    task = ws.context.promote(
        owner, idea.id, ws.tasks, assignee_id=claude.actor_id, instructions="Draft the carousel"
    )
    assert task.status == "draft" and task.project_id == project.id
    assert [p.ref_id for p in ws.tasks.pins(owner, task.id)] == [idea.id]
    assert ws.context.get(owner, idea.id).idea_state == "promoted"
    with pytest.raises(InvalidTransition):
        ws.context.set_idea_state(owner, idea.id, "captured")


def test_a_model_captures_only_into_its_own_inbox(ws, owner, connect):
    claude = connect()
    other = ws.owner()
    with pytest.raises(PermissionDenied):
        ws.context.capture(claude, scope=f"inbox:{other.actor_id}", body="x")


def _approved_post(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    made = ws.artifacts.create(
        claude, run_id=run.id, type="social_post", title="Launch post", content="We are live."
    )
    ws.bus.complete(claude, run.id, summary="One post")
    approval = ws.approvals.list(owner)[0]
    assert approval.subject_id == made.artifact.id  # completion opened the review
    ws.approvals.decide(owner, approval.id, decision="approved")
    return claude, made


def test_export_needs_an_approved_version(ws, owner, connect, make_task, destination):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    draft = ws.artifacts.create(
        claude, run_id=run.id, type="social_post", title="Draft", content="not yet"
    )
    with pytest.raises(Conflict):
        ws.artifacts.export(owner, draft.artifact.id, "fake-drive")
    with pytest.raises(PermissionDenied):
        ws.artifacts.export(claude, draft.artifact.id, "fake-drive")


def test_approved_artifacts_export_and_record_it(ws, owner, connect, make_task, destination):
    _claude, made = _approved_post(ws, owner, connect, make_task)
    record = ws.artifacts.export(owner, made.artifact.id, "fake-drive")
    assert record.destination == "fake-drive" and record.artifact_version == 1
    assert destination.delivered == [(made.version.filename, b"We are live.")]
    assert ws.artifacts.get(owner, made.artifact.id).status == "exported"
    types = [e.type for e in ws.events.activity(owner, subject_id=made.artifact.id)]
    assert "artifact.exported" in types and "artifact.approved" in types


def test_a_new_version_needs_a_new_decision(ws, owner, connect, make_task):
    _claude, made = _approved_post(ws, owner, connect, make_task)
    revised = ws.artifacts.create(
        owner,
        artifact_id=made.artifact.id,
        type="social_post",
        title="Launch post",
        content="We are live today.",
    )
    assert revised.version.number == 2 and revised.artifact.status == "draft"
    assert revised.version.run_id is None and revised.version.created_by == owner.actor_id


def test_no_model_overwrites_another_models_work(ws, owner, connect, make_task):
    _claude, made = _approved_post(ws, owner, connect, make_task)
    codex = connect("Codex", provider="codex")
    task = make_task(codex, title="Rewrite")
    run = ws.bus.claim(codex, task.id).run
    with pytest.raises(PermissionDenied):
        ws.artifacts.create(
            codex,
            run_id=run.id,
            artifact_id=made.artifact.id,
            type="social_post",
            title="Mine now",
            content="x",
        )


def test_a_model_writes_artifacts_only_through_a_run(ws, connect):
    with pytest.raises(ValidationFailed):
        ws.artifacts.create(connect(), type="document", title="Loose", content="x")


def test_artifact_types_are_enforced(ws, owner, project):
    with pytest.raises(ValidationFailed):
        ws.artifacts.create(
            owner, project_id=project.id, type="image", title="Not an image", content="plain text"
        )


def test_project_bundle_is_human_readable(ws, owner, connect, make_task, project):
    _claude, made = _approved_post(ws, owner, connect, make_task)
    data = ws.artifacts.bundle(owner, project_id=project.id)
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = set(archive.namelist())
    assert {"README.md", "lineage.json", f"artifacts/{made.version.filename}"} <= names
    readme = archive.read("README.md").decode()
    assert "Content creation" in readme and "Launch post" in readme
    lineage = json.loads(archive.read("lineage.json"))
    assert lineage[0]["version"]["run_id"] == made.version.run_id


def test_direct_review_by_the_owner(ws, owner, project):
    made = ws.artifacts.create(
        owner, project_id=project.id, type="document", title="Brief", content="# Brief"
    )
    ws.approvals.review_artifact(owner, made.artifact.id, decision="approved")
    assert ws.artifacts.get(owner, made.artifact.id).status == "approved"
    with pytest.raises(ValidationFailed):
        ws.approvals.review_artifact(owner, made.artifact.id, decision="maybe")


def test_changes_requested_needs_a_note(ws, owner, project):
    made = ws.artifacts.create(
        owner, project_id=project.id, type="document", title="Brief", content="# Brief"
    )
    with pytest.raises(ValidationFailed):
        ws.approvals.review_artifact(owner, made.artifact.id, decision="changes_requested")


def test_models_propose_long_term_context_but_never_write_it(ws, owner, connect, brain, project):
    claude = connect()
    with pytest.raises(ValidationFailed):
        ws.brain.propose(claude, title="Posting days", statement="Post Tue and Thu.")
    result = ws.brain.propose(
        claude,
        title="Posting days",
        statement="Post Tue and Thu.",
        evidence="Owner in chat: 'we post Tuesdays and Thursdays'",
        idempotency_key="p1",
    )
    assert result.status == "pending"
    assert brain.proposed[0]["proposer"].startswith("model:Claude Code")
    again = ws.brain.propose(
        claude,
        title="Posting days",
        statement="Post Tue and Thu.",
        evidence="Owner in chat: 'we post Tuesdays and Thursdays'",
        idempotency_key="p1",
    )
    assert again.status == "duplicate" and len(brain.proposed) == 1
    event = next(e for e in ws.events.activity(owner) if e.type == "brain.proposed")
    assert event.actor_id == claude.actor_id


def test_counts_for_the_home_screen(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    ws.artifacts.create(claude, run_id=run.id, type="social_post", title="P", content="x")
    ws.bus.complete(claude, run.id, summary="done")
    counts = ws.counts(owner)
    assert counts["ai_work"]["review"] == 1 and counts["brain_proposals"] == 0


def test_models_open_the_brains_procedures_and_references(ws, connect):
    claude = connect()
    skill = ws.brain.skill(claude, "/weekly-posts")
    assert skill is not None and skill.text.startswith("1. Read the calendar")
    assert ws.brain.skill(claude, "missing") is None
    reference = ws.brain.reference(claude, "references/voice.md")
    assert reference is not None and "Warm and plain" in reference.text


def test_people_verify_and_mark_brain_entries_models_cannot(ws, owner, connect, brain):
    claude = connect()
    with pytest.raises(PermissionDenied):
        ws.brain.verify(claude, "voice-guide")
    with pytest.raises(ValidationFailed):
        ws.brain.mark(owner, "voice-guide", "stale", reason=" ")
    marked = ws.brain.mark(owner, "voice-guide", "stale", reason="Tone changed in September")
    assert marked.stale and marked.stale_reason == "marked stale"
    verified = ws.brain.verify(owner, "voice-guide", confidence="confirmed")
    assert not verified.stale and verified.confidence == "confirmed"
    kinds = [e.type for e in ws.events.activity(owner, subject_id="voice-guide")]
    assert kinds == ["brain.verified", "brain.marked"]
