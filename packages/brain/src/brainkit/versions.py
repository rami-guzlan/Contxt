"""Brain versions (Release 1 plan, 15.1).

A version is an annotated git tag `gnomon/v<N>` in the Brain's own repository. Its message
holds one line of JSON: the cause (distill, manual, restore), when, by whom, how many entries
were added, changed and removed since the version before, and the context-sheet event count
at that moment. The tags are the record; a `brain_versions` table in the ledger keeps a copy
for quick reads and is rebuilt from the tags. Snapshots are not stored: git keeps every state.

    tag       make a version of the Brain as it is (pending changes committed first)
    label     "v3", or "v3+2" with two commits since; on every packet and receipt
    diff      the entries added, changed and removed between two versions, and sheet cells
    restore   chosen entries (or every changed one) as they were at a version, as a new commit
              and a new version; refused, naming them, when an entry changed since the last
              version, the way undo points refuse

Called by the app's Save version, by the distill when it succeeds (cause="distill"), and by
a heartbeat that applies during the day (once a day).
"""
from __future__ import annotations

import json
import os

from . import frontmatter as fm
from . import gitops, util

PREFIX = "gnomon/v"
CAUSES = ("distill", "manual", "restore", "daily")
SKIP = ("inbox/", "journal/", ".brain/")


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _git(brain, *args):
    return gitops._run(brain.repo_root, *args)


def _out(brain, *args) -> str | None:
    proc = _git(brain, *args)
    return proc.stdout if proc is not None and proc.returncode == 0 else None


def _vault_rel(brain) -> str:
    rel = os.path.relpath(brain.vault.root, brain.repo_root).replace("\\", "/")
    return "" if rel == "." else rel.rstrip("/") + "/"


def _ready(brain):
    if not gitops.is_repo(brain.repo_root) or not gitops.owns_repo(brain.repo_root):
        return _result("Versions need the Brain's own git repository (run git init in it).",
                       {"status": "no_repo"}, True)
    return None


def list_versions(brain) -> list[dict]:
    """Every version, oldest first, read from the tags."""
    out = _out(brain, "for-each-ref", "refs/tags/gnomon/", "--format",
               "%(refname:short)\t%(*objectname)%(objectname)\t%(contents:subject)")
    found = []
    for line in (out or "").splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3 or not parts[0].startswith(PREFIX):
            continue
        number = parts[0][len(PREFIX):]
        if not number.isdigit():
            continue
        try:
            meta = json.loads(parts[2])
        except ValueError:
            meta = {}
        found.append({**meta, "number": int(number), "name": f"v{number}", "tag": parts[0],
                      "commit": parts[1][:40]})
    return sorted(found, key=lambda v: v["number"])


def latest(brain) -> dict | None:
    found = list_versions(brain)
    return found[-1] if found else None


def _ref(brain, version) -> str | None:
    name = str(version or "").strip()
    if name.lower() == "head":
        return "HEAD"
    if name.startswith(PREFIX):
        name = "v" + name[len(PREFIX):]
    if name.startswith("v") and name[1:].isdigit():
        return PREFIX + name[1:]
    return None


def label(brain) -> str:
    """The latest version, and how many commits came after it ("v3+2"); "unversioned" when
    the Brain has none. Kept per state of the vault, since a request asks it every time."""
    key = brain.state().fingerprint
    cached = getattr(brain, "_version_label", None)
    if cached and cached[0] == key:
        return cached[1]
    last = latest(brain)
    if last is None:
        text = "unversioned"
    else:
        count = _out(brain, "rev-list", "--count", f"{last['tag']}..HEAD")
        since = int(count.strip()) if count and count.strip().isdigit() else 0
        text = last["name"] + (f"+{since}" if since else "")
    brain._version_label = (key, text)
    return text


def _sheet_events(brain) -> int:
    from . import state
    folder = brain.vault.path(state.FOLDER)
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if name.endswith(".jsonl"):
                with open(os.path.join(root, name), encoding="utf-8") as handle:
                    total += sum(1 for line in handle if line.strip())
    return total


def tag(brain, *, cause="manual", note="", by=None):
    """Make a version of the Brain as it is now. Pending changes are committed first; a Brain
    unchanged since its last version keeps that version."""
    refusal = _ready(brain)
    if refusal:
        return refusal
    cause = str(cause or "manual").strip().lower()
    if cause not in CAUSES:
        return _result(f"A version's cause is one of {', '.join(CAUSES)}.",
                       {"status": "invalid"}, True)
    pending = gitops.uncommitted(brain.repo_root, brain.governed_folders())
    if pending:
        gitops.commit(brain.repo_root, [os.path.join(brain.repo_root, p) for p in pending],
                      f"Changes before a version ({cause})")
    head = (_out(brain, "rev-parse", "HEAD") or "").strip()
    last = latest(brain)
    if last is not None and last["commit"] == head:
        return _result(f"Nothing changed since {last['name']}.",
                       {"status": "unchanged", "version": last})
    changes = diff(brain, last["name"], "HEAD") if last else {"added": [], "changed": [],
                                                                "removed": []}
    number = (last["number"] + 1) if last else 1
    meta = {"cause": cause, "at": util.now_iso(), "by": brain.principal(by),
            "added": len(changes["added"]), "changed": len(changes["changed"]),
            "removed": len(changes["removed"]), "sheet_events": _sheet_events(brain)}
    if note:
        meta["note"] = " ".join(str(note).split())[:200]
    proc = _git(brain, *gitops._identity(brain.repo_root), "tag", "-a", f"{PREFIX}{number}",
                "-m", json.dumps(meta, sort_keys=True))
    if proc is None or proc.returncode != 0:
        return _result("Could not make the version: "
                       + ((proc.stderr or proc.stdout).strip() if proc else "git unavailable"),
                       {"status": "failed"}, True)
    brain._version_label = None
    made = {**meta, "number": number, "name": f"v{number}", "tag": f"{PREFIX}{number}",
            "commit": head}
    _record(brain, made)
    return _result(f"Saved version v{number} ({cause}).", {"status": "made", "version": made})


def _record(brain, version: dict) -> None:
    """The ledger's copy of a version, for quick reads; the tag is the record."""
    with brain.ledger._connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS brain_versions (number INTEGER PRIMARY KEY, "
                     "name TEXT, tag TEXT, commit_sha TEXT, cause TEXT, at TEXT, by TEXT, "
                     "added INTEGER, changed INTEGER, removed INTEGER, sheet_events INTEGER)")
        conn.execute("INSERT OR REPLACE INTO brain_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (version["number"], version["name"], version["tag"], version["commit"],
                      version["cause"], version["at"], version.get("by") or "",
                      version["added"], version["changed"], version["removed"],
                      version["sheet_events"]))


def _show(brain, ref: str, path: str) -> str | None:
    return _out(brain, "show", f"{ref}:{path}")


def _entry(text: str | None, path: str) -> dict:
    if text is None:
        return {}
    meta, body, _errors = fm.parse(text)
    return {"id": str(meta.get("id") or os.path.splitext(os.path.basename(path))[0]),
            "title": str(meta.get("title") or ""), "body": body.strip()}


def diff(brain, a, b) -> dict:
    """What changed from version `a` to `b` (a version name or HEAD): entries added, changed
    and removed, each with its id, title, path and old and new text; and the sheet cell events
    written in between."""
    ref_a, ref_b = _ref(brain, a), _ref(brain, b)
    if ref_a is None or ref_b is None:
        raise ValueError(f"Name versions as v<N> or HEAD, not {a!r} and {b!r}.")
    rel = _vault_rel(brain)
    out = _out(brain, "diff", "--name-status", "--no-renames", ref_a, ref_b, "--", rel or ".")
    found: dict = {"from": a, "to": b, "added": [], "changed": [], "removed": [], "cells": []}
    from . import state
    sheets = f"{rel}{state.FOLDER}/"
    for line in (out or "").splitlines():
        status, _, path = line.partition("\t")
        inner = path[len(rel):] if path.startswith(rel) else path
        if path.startswith(sheets) and path.endswith(".jsonl"):
            found["cells"] += _cells(brain, ref_a, ref_b, path, sheets)
            continue
        if not path.endswith(".md") or inner.startswith(SKIP):
            continue
        old = _entry(_show(brain, ref_a, path), path) if status != "A" else {}
        new = _entry(_show(brain, ref_b, path), path) if status != "D" else {}
        if not (old or new).get("id"):
            continue
        row = {"id": (new or old)["id"], "title": (new or old).get("title", ""), "path": inner,
               "old": old.get("body", ""), "new": new.get("body", "")}
        key = {"A": "added", "D": "removed"}.get(status[:1], "changed")
        found[key].append(row)
    return found


def _cells(brain, ref_a, ref_b, path, sheets) -> list[dict]:
    before = (_show(brain, ref_a, path) or "").splitlines()
    after = (_show(brain, ref_b, path) or "").splitlines()
    sheet, row = path[len(sheets):].rsplit("/", 1) if "/" in path[len(sheets):] else ("", path)
    out = []
    for line in after[len(before):]:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("kind") == "cell":
            out.append({"sheet": sheet, "row": os.path.splitext(row)[0],
                        "column": event.get("column"), "value": event.get("value"),
                        "at": event.get("at")})
    return out


def restore(brain, version, *, ids=None, by=None):
    """Put chosen entries (or every entry changed since `version`) back as they were then, as
    a new commit and a new version. Refused, naming them, when an entry changed after the
    latest version: a restore never overwrites work no version holds."""
    refusal = _ready(brain)
    if refusal:
        return refusal
    last = latest(brain)
    ref = _ref(brain, version)
    if last is None or ref is None or ref not in {v["tag"] for v in list_versions(brain)}:
        return _result(f"No version {version!r}.", {"status": "missing"}, True)
    changes = diff(brain, version, last["name"])
    rows = changes["added"] + changes["changed"] + changes["removed"]
    wanted = set(ids or [r["id"] for r in rows])
    chosen = [r for r in rows if r["id"] in wanted]
    if not chosen:
        return _result(f"Nothing to restore: those entries are the same as in {version}.",
                       {"status": "unchanged"})
    rel = _vault_rel(brain)
    since = []
    for row in chosen:
        current = os.path.join(brain.vault.root, row["path"])
        at_last = _show(brain, last["tag"], rel + row["path"])
        now = open(current, encoding="utf-8").read() if os.path.exists(current) else None
        if now != at_last:
            since.append(row["id"])
    if since:
        return _result(f"Cannot restore: {', '.join(since)} changed since {last['name']}. "
                       "Save a version first, or change it by hand.",
                       {"status": "conflict", "changed_since": since}, True)
    touched = []
    for row in chosen:
        full = os.path.join(brain.vault.root, row["path"])
        old = _show(brain, ref, rel + row["path"])
        if old is None:
            if os.path.exists(full):
                os.remove(full)
        else:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            util.atomic_write(full, old)
        touched.append(full)
    gitops.commit(brain.repo_root, touched,
                  f"Restore {len(chosen)} entr{'y' if len(chosen) == 1 else 'ies'} from {version}")
    made = tag(brain, cause="restore", by=by,
               note=f"restored {', '.join(r['id'] for r in chosen)} from {version}")
    if made.is_error:
        return made
    return _result(f"Restored {len(chosen)} from {version} as {made.data['version']['name']}.",
                   {"status": "restored", "restored": [r["id"] for r in chosen],
                    "version": made.data["version"]})
