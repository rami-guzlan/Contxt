"""The earlier workspace over REST: what it holds, a copy as files, and its context moved into
the Brain once."""

import os

from workspace_core.db import schema


def _memory(runtime, project_id, title, body, state="kept"):
    ws = runtime.ws
    with ws.rt.write() as tx:
        tx.insert(
            schema.context_items,
            {
                "id": tx.new_id("ctx"),
                "workspace_id": ws.rt.workspace_id,
                "scope_kind": "project",
                "scope_id": project_id,
                "kind": "memory",
                "title": title,
                "body": body,
                "shadow_status": "none",
                "labels": [],
                "revision": 1,
                "memory_state": state,
                "provenance": {"memory": {"kind": "decision"}},
                "created_by": ws.owner_id,
                "created_at": tx.now,
                "updated_at": tx.now,
                "version": 1,
                "archived_at": None,
            },
        )


def test_the_earlier_workspace_is_copied_out_then_brought_in_once(owner, model, runtime, project):
    _memory(runtime, project["id"], "Launch on Tuesdays", "Client sites launch on Tuesdays.")
    summary = owner.ok(owner.get("/api/legacy"))
    assert summary["counts"]["memories"] == 1 and summary["counts"]["projects_without_brain"] == 1
    assert summary["has_any"] and summary["exported_at"] is None

    made = owner.ok(owner.post("/api/legacy/export"), 201)
    assert os.path.basename(made["dir"]) == "workspace-export-2026-09-28"
    assert os.path.isfile(os.path.join(made["dir"], "project-memory.md"))
    again = owner.ok(owner.post("/api/legacy/export"), 201)
    assert again["dir"] != made["dir"]  # a second copy the same day gets its own folder

    report = owner.ok(owner.post("/api/legacy/bring-into-brain"))
    # the sample Brain already follows "Website Redesign": matched by name, not started again
    assert (report["projects_started"], report["projects_matched"]) == ([], 1)
    assert (report["notes_proposed"], report["refused"]) == (1, [])
    (waiting,) = owner.ok(owner.get("/api/brain/proposals"))
    assert waiting["summary"] == "Client sites launch on Tuesdays."
    assert waiting["target"]["origin"].startswith("workspace:ctx_")
    linked = runtime.ws.projects.get(runtime.ws.owner(), project["id"])
    assert linked.brain_ref == "state-focus-website-redesign"
    second = owner.ok(owner.post("/api/legacy/bring-into-brain"))
    assert second["notes_proposed"] == 0 and second["projects_started"] == []
    assert len(owner.ok(owner.get("/api/brain/proposals"))) == 1
    after = owner.ok(owner.get("/api/legacy"))
    assert after["counts"]["projects_without_brain"] == 0 and after["moved_at"]
    assert model.get("/api/legacy").status_code == 403


def test_a_kept_memory_is_the_owners_word_and_a_suggested_one_their_ais(owner, runtime, project):
    _memory(runtime, project["id"], "Launch on Tuesdays", "Client sites launch on Tuesdays.")
    _memory(runtime, project["id"], "Retainers", "Retainers renew every month.", state="suggested")
    owner.ok(owner.post("/api/legacy/bring-into-brain"))
    said = {
        p["summary"]: p["target"]["said_by"] for p in owner.ok(owner.get("/api/brain/proposals"))
    }
    assert said == {
        "Client sites launch on Tuesdays.": "owner",
        "Retainers renew every month.": "owner-ai",
    }
