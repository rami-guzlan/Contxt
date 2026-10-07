"""Backup and restore preserve records, files and references (V1 acceptance)."""

import json
import os
import zipfile

import pytest

from workspace_core.backup import backup, restore
from workspace_core.errors import Conflict
from workspace_core.workspace import Workspace


def _populate(ws, owner, connect, make_task, project):
    claude = connect()
    item = ws.context.capture(
        owner,
        scope=f"project:{project.id}",
        kind="document",
        data=b"Calendar: Oct 14 webinar",
        filename="calendar.txt",
    )
    task = make_task(claude, ready=False)
    ws.tasks.pin(owner, task.id, ref_type="context_item", ref_id=item.id)
    ws.tasks.mark_ready(owner, task.id)
    run = ws.bus.claim(claude, task.id).run
    made = ws.artifacts.create(
        claude, run_id=run.id, type="social_post", title="Post", content="Join us Oct 14"
    )
    ws.bus.complete(claude, run.id, summary="ok")
    return item, task, made


def test_round_trip(tmp_path, ws, owner, connect, make_task, project, clock, brain):
    item, task, made = _populate(ws, owner, connect, make_task, project)
    vault = tmp_path / "vault"
    (vault / "knowledge").mkdir(parents=True)
    (vault / "knowledge" / "voice.md").write_text("Write plainly.", encoding="utf-8")
    (vault / ".brain").mkdir()
    (vault / ".brain" / "cache.bin").write_bytes(b"runtime state")

    archive = tmp_path / "backup.zip"
    manifest = backup(ws, str(archive), brain_vault=str(vault))
    assert manifest["tables"]["tasks"] == 1 and manifest["objects"]["count"] == 2
    assert manifest["brain"]["files"] == 1  # runtime state is left out

    target = tmp_path / "restored"
    report = restore(str(archive), str(target), brain_dir=str(tmp_path / "vault-restored"))
    assert report["tables"] == manifest["tables"]
    again = Workspace.open(str(target), clock=clock, brain=brain)
    try:
        restored_owner = again.owner()
        assert restored_owner.actor_id == owner.actor_id
        assert again.tasks.get(restored_owner, task.id).status == "review"
        pins = again.tasks.pins(restored_owner, task.id)
        assert [p.ref_id for p in pins] == [item.id]
        version, data = again.artifacts.content(restored_owner, made.artifact.id)
        assert data == b"Join us Oct 14" and version.inputs[0]["ref"] == f"context_item:{item.id}"
        _item, raw = again.context.content(restored_owner, item.id)
        assert raw == b"Calendar: Oct 14 webinar"
        assert (
            len(again.events.activity(restored_owner, include_noise=True, limit=500))
            == manifest["tables"]["events"]
        )
    finally:
        again.close()
    assert (tmp_path / "vault-restored" / "knowledge" / "voice.md").read_text() == "Write plainly."


def test_a_brain_backup_keeps_original_files(tmp_path, ws, owner):
    vault = tmp_path / "vault"
    (vault / "references").mkdir(parents=True)
    (vault / "references" / "deck.md").write_text("Converted text.", encoding="utf-8")
    runtime = vault / ".brain"
    (runtime / "library").mkdir(parents=True)
    (runtime / "library" / "abc123.pdf").write_bytes(b"%PDF original bytes")
    (runtime / "staging" / "prop-1").mkdir(parents=True)
    (runtime / "staging" / "prop-1" / "original.docx").write_bytes(b"waiting for review")
    (runtime / "staging" / ".probe-abc.pdf").write_bytes(b"a check in progress")
    (runtime / "models").mkdir()
    (runtime / "models" / "weights.bin").write_bytes(b"downloaded again")
    (runtime / "embeddings.sqlite").write_bytes(b"rebuilt")
    (runtime / "sessions.sqlite").write_bytes(b"local history")

    archive = tmp_path / "backup.zip"
    manifest = backup(ws, str(archive), brain_vault=str(vault))
    assert (manifest["brain"]["files"], manifest["brain"]["originals"]) == (3, 1)
    names = set(zipfile.ZipFile(archive).namelist())
    assert "brain/.brain/library/abc123.pdf" in names
    assert "brain/.brain/staging/prop-1/original.docx" in names
    assert not any("models" in n or n.endswith(".sqlite") or "probe" in n for n in names)

    restored = tmp_path / "vault-restored"
    report = restore(str(archive), str(tmp_path / "data-restored"), brain_dir=str(restored))
    assert report["brain_files"] == 3
    assert (restored / ".brain" / "library" / "abc123.pdf").read_bytes() == b"%PDF original bytes"
    assert (restored / ".brain" / "staging" / "prop-1" / "original.docx").exists()


def test_restore_refuses_to_overwrite(tmp_path, ws, owner, connect, make_task, project):
    _populate(ws, owner, connect, make_task, project)
    archive = tmp_path / "backup.zip"
    backup(ws, str(archive))
    restore(str(archive), str(tmp_path / "restored"))
    with pytest.raises(Conflict):
        restore(str(archive), str(tmp_path / "restored"))


def test_a_tampered_archive_is_refused(tmp_path, ws, owner, connect, make_task, project):
    _populate(ws, owner, connect, make_task, project)
    archive = tmp_path / "backup.zip"
    manifest = backup(ws, str(archive))
    key = manifest["objects"]["keys"][0]
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(tampered, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith(key):
                data = b"changed"
            dst.writestr(info, data)
    with pytest.raises(Conflict):
        restore(str(tampered), str(tmp_path / "restored"))


def test_the_manifest_is_readable_without_the_app(tmp_path, ws, owner):
    archive = tmp_path / "backup.zip"
    backup(ws, str(archive))
    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format"] == 1 and manifest["workspace"]["name"] == "Test workspace"
        assert "tables/workspaces.jsonl" in zf.namelist()
    assert os.path.getsize(archive) > 0
