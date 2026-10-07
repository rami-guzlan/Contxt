"""Sync: sweep chosen folders for new material and propose it, so nothing is added by hand.

Configured in brain.json:

    "sync": {
      "drop":   ["drop"],               files here become file proposals: documents are filed
                                        as references, images, fonts and data files as assets
      "skills": ["~/.claude/skills"]    each sub-folder holding a SKILL.md becomes a skill
                                        proposal; a changed folder becomes a skill change
    }

Paths are relative to the repository root (the vault's parent), absolute, or start with ~.
The session-start hook runs a sweep, and `brain sync` runs one by hand.

IDEMPOTENT. What a sweep proposed, or refused, is remembered by content hash in
`.brain/sync.json`, so the next sweep proposes only what is new or changed, and an unsafe file
is reported once rather than on every session. A swept file is never moved or deleted: the
folder stays the person's own.
"""
from __future__ import annotations

import hashlib
import json
import os

from . import frontmatter as fm
from . import util

STATE_FILE = "sync.json"
SKIP_NAMES = {"readme.md", "readme.txt", ".ds_store", "thumbs.db", "desktop.ini"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def sources(brain) -> dict:
    """{"drop": [absolute folders], "skills": [absolute folders]} from brain.json."""
    spec = brain.state().config.data.get("sync") or {}
    out = {}
    for key in ("drop", "skills"):
        folders = []
        for value in spec.get(key) or []:
            path = os.path.expanduser(str(value))
            if not os.path.isabs(path):
                path = os.path.join(brain.repo_root, path)
            folders.append(os.path.abspath(path))
        out[key] = folders
    return out


def _state_path(brain) -> str:
    return os.path.join(brain.vault.runtime_dir, STATE_FILE)


def _load_state(brain) -> dict:
    try:
        with open(_state_path(brain), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(brain, state) -> None:
    util.atomic_write(_state_path(brain), json.dumps(state, indent=1, sort_keys=True))


def _file_hash(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _folder_files(folder):
    for current, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            yield os.path.join(current, name)


def _folder_hash(folder) -> str:
    digest = hashlib.sha256()
    for path in _folder_files(folder):
        digest.update(util.rel(path, folder).encode("utf-8") + b"\0")
        digest.update(_file_hash(path).encode("ascii"))
    return digest.hexdigest()


def run(brain, *, principal=None, dry_run=False):
    """File (or propose, as the capture policy says) what is new or changed in the
    configured folders. Returns counts and lines."""
    from . import uploads
    folders = sources(brain)
    state = _load_state(brain)
    seen_files = state.setdefault("files", {})
    seen_skills = state.setdefault("skills", {})
    proposed, filed, skipped, lines = 0, 0, 0, []

    for folder in folders["drop"]:
        if not os.path.isdir(folder):
            continue
        for path in _folder_files(folder):
            name = os.path.basename(path)
            if name.lower() in SKIP_NAMES:
                continue
            digest = _file_hash(path)
            if seen_files.get(path) == digest:
                continue
            if dry_run:
                lines.append(f"would propose {util.rel(path, folder)}")
                continue
            res = uploads.add_file(brain, source_path=path, principal=principal,
                                   source=f"sync: {path}", origin="folder",
                                   reason="found in a drop folder by sync")
            seen_files[path] = digest
            status = res.data.get("status")
            if status == "applied":
                filed += 1
                lines.append(f"filed {name}: {res.text.splitlines()[0]}")
            elif status == "pending":
                proposed += 1
                lines.append(f"proposed {name}: {res.text.splitlines()[0]}")
            elif res.is_error:
                skipped += 1
                lines.append(f"skipped {name}: {res.text}")

    for folder in folders["skills"]:
        if not os.path.isdir(folder):
            continue
        for entry in sorted(os.listdir(folder)):
            skill_dir = os.path.join(folder, entry)
            skill_md = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            digest = _folder_hash(skill_dir)
            if seen_skills.get(skill_dir) == digest:
                continue
            if dry_run:
                lines.append(f"would propose skill {entry}")
                continue
            res = _propose_skill_folder(brain, skill_dir, principal=principal)
            seen_skills[skill_dir] = digest
            if res.data.get("status") in ("pending", "applied"):
                proposed += 1
                lines.append(f"proposed skill {entry}: {res.text.splitlines()[0]}")
            elif res.is_error and res.data.get("status") not in ("duplicate",):
                skipped += 1
                lines.append(f"skipped skill {entry}: {res.text}")

    if not dry_run:
        _save_state(brain, state)
    done = [f"filed {filed}"] if filed else []
    if proposed or not filed:
        done.append(f"proposed {proposed} for review")
    if skipped:
        done.append(f"skipped {skipped}")
    summary = "Sync " + ", ".join(done) + " item(s)."
    return _result(summary + ("\n" + "\n".join(lines) if lines else ""),
                   {"proposed": proposed, "filed": filed, "skipped": skipped, "lines": lines,
                    "sources": folders})


def propose_folder(brain, skill_dir, *, category=None, target=None, principal=None):
    """Propose one skill folder by hand (`brain propose-skill`)."""
    skill_dir = os.path.abspath(os.path.expanduser(str(skill_dir)))
    if not os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        return _result(f"No SKILL.md in {skill_dir}.", {"status": "invalid"}, True)
    return _propose_skill_folder(brain, skill_dir, principal=principal, category=category,
                                 target=target)


def _propose_skill_folder(brain, skill_dir, *, principal=None, category=None, target=None):
    """Propose one skill folder: a new skill, or a change when the brain already has it."""
    from . import uploads
    meta, body, _errors = fm.parse(util.read_text(os.path.join(skill_dir, "SKILL.md")))
    name = str(meta.get("name") or os.path.basename(skill_dir)).strip()
    files = []
    for path in _folder_files(skill_dir):
        relpath = util.rel(path, skill_dir)
        if relpath.lower() == "skill.md":
            continue
        files.append({"path": relpath, "source_path": path})
    lists = {key: fm.as_list(meta.get(key)) or None for key in uploads.SKILL_LIST_FIELDS}
    common = dict(description=meta.get("description"), when_to_use=meta.get("when_to_use"),
                  invocation=meta.get("invocation"), body=body, files=files,
                  principal=principal, source=f"sync: {skill_dir}",
                  reason="found in a skills folder by sync",
                  triggers=lists["triggers"], aliases=lists["aliases"],
                  cue_terms=lists["cue_terms"], artifacts=lists["artifacts"],
                  loads=lists["loads"])
    existing = uploads._find_skill(brain.state(), target or name)
    if existing is not None:
        if existing.body.strip() == str(body).strip() and not files:
            return _result(f"{name} is unchanged.", {"status": "unchanged"})
        return uploads.propose_skill(brain, target=existing.name, **common)
    category = str(category or meta.get("category") or "imported").strip().lower()
    return uploads.propose_skill(brain, name=name, category=category,
                                 scope=meta.get("scope"), **common)
