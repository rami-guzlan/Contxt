"""The earlier workspace: everything it held written out as files, and its context moved into
the Brain once (projects matched or started, memories proposed, transcripts and documents
filed, open to-dos made next steps)."""

import json
import os
from datetime import timedelta

import pytest

from workspace_core.db import schema
from workspace_core.errors import PermissionDenied
from workspace_core.ports import BrainProject, BrainProposal


def _add(ws, who, table, prefix, **values):
    """A row as the earlier workspace wrote it."""
    with ws.rt.write() as tx:
        row = {
            "id": tx.new_id(prefix),
            "workspace_id": ws.rt.workspace_id,
            "created_by": who.actor_id,
            "created_at": tx.now,
            "updated_at": tx.now,
            "version": 1,
            "archived_at": None,
            "provenance": {},
            **values,
        }
        return tx.insert(table, row)


def _item(ws, who, kind, title, body="", *, scope=("workspace", None), **values):
    return _add(
        ws,
        who,
        schema.context_items,
        "ctx",
        scope_kind=scope[0],
        scope_id=scope[1],
        kind=kind,
        title=title,
        body=body,
        shadow_status="none",
        labels=[],
        revision=1,
        **values,
    )


@pytest.fixture
def earlier(ws, owner, brain, clock):
    """A workspace with a bit of everything: a project linked to a Brain project, one named
    like another Brain project, one with no match; memories, a meeting with its transcript,
    an uploaded document, to-dos, a goal, a sheet and a canvas."""
    brain.started += [
        BrainProject(id="brain-kit", title="Brain Kit", topic="projects/brain-kit"),
        BrainProject(
            id="website-relaunch",
            title="Website Relaunch Plan",
            topic="projects/website-relaunch",
            current="Hero in review",
            next="Ship the new hero",
        ),
    ]
    linked = ws.projects.create(owner, title="Brain-Kit", brain_ref="brain-kit")
    named = ws.projects.create(owner, title="Website-Relaunch-Plan")
    fresh = ws.projects.create(owner, title="LinkedIn Campaigns", summary="Paid and organic")
    meeting = _add(
        ws,
        owner,
        schema.meetings,
        "mtg",
        title="Jordan sync",
        held_on="2026-09-30",
        attendees=["Jordan"],
        project_id=None,
        summary="",
    )
    transcript = ws.context.capture(
        owner,
        scope=f"meeting:{meeting['id']}",
        kind="transcript",
        title="Jordan sync transcript",
        body="Jordan: keep LinkedIn video.",
    )
    with ws.rt.write() as tx:
        row = tx.one(schema.meetings, meeting["id"], "meeting")
        tx.update(schema.meetings, row, {"item_id": transcript.id})
    memory = {"kind": "decision", "meeting_id": meeting["id"], "evidence": "Jordan said so."}
    kept = _item(
        ws,
        owner,
        "memory",
        "Video stays",
        "LinkedIn video keeps its budget.",
        scope=("project", fresh.id),
        memory_state="kept",
        provenance={"memory": memory},
    )
    suggested = _item(
        ws,
        owner,
        "memory",
        "Podcasts cut",
        "Podcasts are cut for Q4.",
        scope=("project", linked.id),
        memory_state="suggested",
        provenance={"memory": {"kind": "constraint"}},
    )
    _item(
        ws,
        owner,
        "memory",
        "Old idea",
        "Gone.",
        scope=("project", linked.id),
        memory_state="kept",
        archived_at="2026-09-01T00:00:00Z",
    )
    clock.advance(timedelta(minutes=1))  # added after the meeting
    document = ws.context.capture(
        owner,
        scope="workspace",
        kind="document",
        data=b"# Business\n\nWe sell learning.",
        filename="business.md",
        mime="text/markdown",
    )
    for title, due in (("Book the venue", "2026-10-09"), ("Draft the ad", None)):
        _add(
            ws,
            owner,
            schema.todos,
            "todo",
            project_id=named.id,
            title=title,
            notes="",
            owner="Robin",
            due_on=due,
            status="open",
        )
    _add(ws, owner, schema.todos, "todo", project_id=named.id, title="Done", status="done")
    _add(ws, owner, schema.goals, "goal", title="Grow pipeline", status="active")
    sheet = {
        "columns": [{"id": "c1", "name": "Channel"}, {"id": "c2", "name": "Spend"}],
        "rows": [{"cells": {"c1": "LinkedIn", "c2": 1200}}],
    }
    _item(ws, owner, "sheet", "Budget", json.dumps(sheet), archived_at="2026-09-02T00:00:00Z")
    _item(ws, owner, "canvas", "Map", json.dumps({"elements": [{"id": "e1"}]}))
    return {
        "linked": linked,
        "named": named,
        "fresh": fresh,
        "transcript": transcript,
        "kept": kept,
        "suggested": suggested,
        "document": document,
    }


def test_the_summary_counts_what_the_earlier_workspace_holds(ws, owner, earlier):
    summary = ws.legacy.summary(owner)
    counts = summary["counts"]
    assert (counts["goals"], counts["todos_open"], counts["todos_done"]) == (1, 2, 1)
    assert (counts["meetings"], counts["transcripts"], counts["memories"]) == (1, 1, 2)
    assert (counts["documents"], counts["sheets"], counts["canvases"]) == (1, 1, 1)
    assert (counts["projects"], counts["projects_without_brain"]) == (3, 2)
    assert summary["has_any"] and summary["exported_at"] is None and summary["moved"] == {}


def test_the_export_writes_everything_as_files_and_changes_nothing(ws, owner, earlier, tmp_path):
    out = tmp_path / "export"
    made = ws.legacy.export(owner, str(out))
    written = set(made["written"])
    assert {"projects.json", "goals.json", "todos.json", "todos.md", "README.md"} <= written
    assert {"project-memory.json", "project-memory.md", "working-context.json"} <= written
    todos = (out / "todos.md").read_text(encoding="utf-8")
    assert "- [ ] Book the venue (due 2026-10-09), Robin [open]" in todos
    assert "- [x] Done" in todos
    memory = (out / "project-memory.md").read_text(encoding="utf-8")
    assert "### Video stays (decision, kept)" in memory
    assert "### Old idea (fact, removed)" in memory
    (csv_name,) = [w for w in written if w.startswith("sheets/") and w.endswith(".csv")]
    assert (out / csv_name).read_text(encoding="utf-8").splitlines() == [
        "Channel,Spend",
        "LinkedIn,1200",
    ]
    (canvas,) = [w for w in written if w.startswith("canvases/")]
    assert json.loads((out / canvas).read_text(encoding="utf-8"))["elements"] == [{"id": "e1"}]
    (transcript,) = [w for w in written if w.startswith("transcripts/")]
    assert "keep LinkedIn video" in (out / transcript).read_text(encoding="utf-8")
    (original,) = [w for w in written if w.startswith("files/")]
    assert (out / original).read_bytes() == b"# Business\n\nWe sell learning."
    summary = ws.legacy.summary(owner)
    assert summary["exported_at"] and summary["export_dir"] == os.path.abspath(out)
    assert summary["counts"]["todos_open"] == 2  # nothing moved or removed


def test_bringing_it_in_moves_each_kind_of_context_once(ws, owner, earlier, brain):
    report = ws.legacy.bring_into_brain(owner)
    assert report["projects_started"] == ["LinkedIn Campaigns"]
    assert (report["projects_matched"], report["projects_left"]) == (2, [])
    assert (report["notes_proposed"], report["files_filed"], report["next_steps"]) == (2, 2, 2)
    assert (report["refused"], report["skipped"]) == ([], 0)
    named = ws.projects.get(owner, earlier["named"].id)
    assert named.brain_ref == "website-relaunch"  # matched by its name, not started again
    assert ws.projects.get(owner, earlier["fresh"].id).brain_ref == "linkedin-campaigns"

    video, podcasts = sorted(brain.proposed, key=lambda p: p["title"], reverse=True)
    assert (video["title"], video["kind"], video["topic"]) == (
        "Video stays",
        "decision",
        "projects/linkedin-campaigns",
    )
    assert video["origin"] == f"workspace:{earlier['kept']['id']}"
    assert video["evidence"] == "Jordan said so."
    assert (podcasts["kind"], podcasts["topic"]) == ("fact", "projects/brain-kit")
    assert podcasts["evidence"] == "Suggested for the workspace's project memory, not yet kept."

    transcript, document = brain.uploaded
    assert (transcript["title"], transcript["project"]) == (
        "Jordan sync transcript (2026-09-30)",
        "linkedin-campaigns",  # the project the meeting fed
    )
    assert transcript["description"] == "Transcript of a meeting held 2026-09-30."
    assert (document["filename"], document["project"]) == ("business.md", None)
    assert document["title"] == ""  # named by its file only: the Brain titles it
    assert document["data"] == b"# Business\n\nWe sell learning."

    (update,) = brain.updates
    assert update["project"] == "website-relaunch"
    assert update["summary"] == "Open to-dos carried over from the workspace (2)"
    assert update["changes"] == {
        "next": "Ship the new hero; Book the venue (due 2026-10-09), Robin; Draft the ad, Robin",
        "current": "Hero in review",  # where it stands stays as it was
    }
    (note,) = ws.notes.list(owner)
    assert (note.id, note.title) == (report["todo_note"], "Open to-dos from the earlier workspace")
    assert report["todos_noted"] == 2
    body = ws.notes.get(owner, note.id).body
    assert "## Website-Relaunch-Plan" in body
    assert "- [ ] Book the venue (due 2026-10-09), Robin" in body

    again = ws.legacy.bring_into_brain(owner)
    assert (again["notes_proposed"], again["files_filed"], again["next_steps"]) == (0, 0, 0)
    assert again["projects_started"] == [] and again["skipped"] == 4
    assert len(brain.proposed) == 2 and len(brain.uploaded) == 2 and len(brain.updates) == 1
    assert len(ws.notes.list(owner)) == 1 and again["todo_note"] == report["todo_note"]
    moved = ws.legacy.summary(owner)["moved"]
    assert set(moved) == {"memories", "transcripts", "documents", "todos", "todo_note"}
    (event, _) = ws.events.activity(owner, types=["workspace.legacy_moved"])
    assert event.data["notes_proposed"] == 0 and event.data["projects_started"] == 0


def test_what_the_brain_refuses_is_reported_and_tried_again_next_time(ws, owner, earlier, brain):
    taken = brain.add_file

    def picky(**fields):
        if fields["filename"] == "business.md":
            return BrainProposal(status="refused", message="That type is not allowed.")
        return taken(**fields)

    brain.add_file = picky
    report = ws.legacy.bring_into_brain(owner)
    assert report["refused"] == [{"title": "business.md", "why": "That type is not allowed."}]
    assert report["files_filed"] == 1
    brain.add_file = taken
    again = ws.legacy.bring_into_brain(owner)
    assert (again["files_filed"], again["refused"]) == (1, [])


def test_a_long_list_of_to_dos_is_cut_to_fit_the_next_steps(ws, owner, brain):
    brain.started.append(BrainProject(id="events", title="Events", topic="projects/events"))
    project = ws.projects.create(owner, title="Events", brain_ref="events")
    for n in range(40):
        _add(
            ws,
            owner,
            schema.todos,
            "todo",
            project_id=project.id,
            title=f"Confirm the speaker for session number {n:02d}",
            status="open",
        )
    report = ws.legacy.bring_into_brain(owner)
    (update,) = brain.updates
    text = update["changes"]["next"]
    assert len(text) <= 1000 and text.endswith(
        "more in the note “Open to-dos from the earlier workspace”"
    )
    assert report["todos_noted"] == 40  # the note has them all
    assert ws.notes.get(owner, report["todo_note"]).body.count("- [ ] ") == 40


def test_to_dos_with_no_project_are_kept_in_the_note(ws, owner, brain):
    _add(
        ws,
        owner,
        schema.todos,
        "todo",
        title="Send Jordan the sign-off list",
        owner="Robin",
        status="open",
    )
    report = ws.legacy.bring_into_brain(owner)
    assert (report["next_steps"], report["todos_noted"]) == (0, 1)
    body = ws.notes.get(owner, report["todo_note"]).body
    assert "## No project\n\n- [ ] Send Jordan the sign-off list, Robin" in body


def test_only_the_owner_works_with_the_earlier_workspace(ws, connect, tmp_path):
    claude = connect()
    with pytest.raises(PermissionDenied):
        ws.legacy.summary(claude)
    with pytest.raises(PermissionDenied):
        ws.legacy.export(claude, str(tmp_path / "x"))
    with pytest.raises(PermissionDenied):
        ws.legacy.bring_into_brain(claude)
