"""Where a file in the outputs folder came from: the export that wrote it, and the skill run
that worked in its folder."""

import os

from workspace_connectors.destinations import FolderDestination
from workspace_core.services.skills import RUN


def _approved_post(ws, owner, connect, make_task):
    claude = connect()
    task = make_task(claude)
    run = ws.bus.claim(claude, task.id).run
    made = ws.artifacts.create(
        claude, run_id=run.id, type="social_post", title="Launch post", content="We are live."
    )
    ws.bus.complete(claude, run.id, summary="One post")
    approval = ws.approvals.list(owner)[0]
    ws.approvals.decide(owner, approval.id, decision="approved")
    return run, made


def test_an_exported_file_names_its_artifact_and_the_run_that_made_it(
    ws, owner, connect, make_task, tmp_path
):
    ws.add_destination(FolderDestination(str(tmp_path / "outputs")))
    run, made = _approved_post(ws, owner, connect, make_task)
    record = ws.artifacts.export(owner, made.artifact.id, "folder")
    location = record.result["location"]
    found = ws.artifacts.exported_to(owner, location)
    assert found["artifact_id"] == made.artifact.id and found["run_id"] == run.id
    assert found["title"] == "Launch post" and found["version"] == 1
    assert ws.artifacts.exported_to(owner, str(tmp_path / "elsewhere.md")) is None


def test_a_skill_runs_folder_names_its_task_and_runs(ws, owner, project, tmp_path):
    folder = str(tmp_path / "outputs" / "skill-runs" / "2026-09-28-brand-sheet")
    task = ws.tasks.create(
        owner,
        project_id=project.id,
        title="Run brand-sheet",
        purpose="Make a brand sheet",
        instructions="Follow the skill.",
        template=RUN,
        provenance={"skill": {"name": "brand-sheet", "ask": "For Acme", "folder": folder}},
    )
    found = ws.skills.made_in(owner, folder)
    assert (found["task_id"], found["skill"], found["ask"]) == (task.id, "brand-sheet", "For Acme")
    assert found["runs"] == []
    assert ws.skills.made_in(owner, os.path.join(str(tmp_path), "other")) is None
