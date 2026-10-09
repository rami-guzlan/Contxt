"""An entry's history: every version of what it said, and every governed event about it.

VERSIONS come from git, the vault's own history: each commit that changed the entry's file,
following the file through renames, so an entry moved to another topic keeps its past. When
the file on disk differs from its last commit (a vault with `git.auto_commit` off, or a hand
edit), that working copy is the newest version. Without git, the versions are the file on
disk and the earlier texts the decision journal kept (an edit records what it replaced).

EVENTS come from the decision journal (`journal/decisions.jsonl`): every proposal approved or
rejected, edit, verification, mark, restore, archive and undo, with who, when and why. Each
version lists the changes recorded between it and the version before, so a version says who
made it and why, not only what the commit message says.

Nothing here writes. Putting a version back is a governed change: `governance.restore`.
"""
from __future__ import annotations

import datetime as dt
import os

from . import frontmatter as fm
from . import gitops, util

# Journal actions that change an entry's file: what it says, its details, or whether it is
# live.
CHANGES = frozenset({"approved", "auto-applied", "edited", "restored", "unarchived",
                     "archived", "reverted", "redone", "updated", "verified", "marked"})
HEAVY = ("body", "previous", "target")  # full texts the journal keeps, left out of listings


def mentions(record: dict, note_id: str) -> bool:
    """Is a journal record about this entry (made, changed, checked, retired, or replaced)?"""
    target = record.get("target")
    if note_id in (record.get("note"), record.get("pointer"),
                   target.get("id") if isinstance(target, dict) else None):
        return True
    return note_id in (record.get("superseded") or [])


def public(record: dict) -> dict:
    """A journal record as a listing shows it: without the full texts it keeps."""
    out = {k: v for k, v in record.items() if k not in HEAVY}
    target = record.get("target")
    if isinstance(target, dict):
        out["target_id"] = target.get("id") or target.get("name")
        out["target_title"] = target.get("title") or target.get("name")
    if record.get("previous"):
        out["has_previous"] = True
    return out


def events(brain, note_id=None, *, since=None, until=None, actions=None, by=None,
           limit=500) -> list[dict]:
    """Journal records, newest first: about one entry (`note_id`), between `since` and
    `until` (ISO), of some `actions`, by one person or model (`by`, the decider or the
    proposer). Full texts stay out (`public`)."""
    wanted = set(actions or ())
    rows = []
    for record in reversed(brain.vault.decisions()):
        at = str(record.get("at") or "")
        if since and at < since:
            continue
        if until and at > until:
            continue
        if note_id and not mentions(record, note_id):
            continue
        if wanted and str(record.get("action") or "") not in wanted:
            continue
        if by and by not in (record.get("by"), record.get("proposer")):
            continue
        rows.append(public(record))
        if len(rows) >= int(limit or 500):
            break
    return rows


def change_counts(brain) -> dict[str, int]:
    """{entry id: how many governed changes the journal records for it}, in one pass."""
    counts: dict[str, int] = {}
    for record in brain.vault.decisions():
        if str(record.get("action") or "") not in CHANGES:
            continue
        for key in {record.get("note"), record.get("pointer"), *(record.get("superseded") or [])}:
            if key:
                counts[str(key)] = counts.get(str(key), 0) + 1
    return counts


# ------------------------------------------------------------------ versions

def _when(text) -> dt.datetime | None:
    try:
        moment = dt.datetime.fromisoformat(str(text or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(data) -> str:
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data or "")
    return text.replace("\r\n", "\n")


def _version(ref, at, text, *, with_text, **extra) -> dict:
    meta, body, _errors = fm.parse(text)
    body = body.strip("\n")
    row = {"ref": ref, "at": at, "title": str(meta.get("title") or ""),
           "summary": str(meta.get("summary") or meta.get("index_line") or ""),
           "status": str(meta.get("status") or "approved").strip().lower(),
           "hash": util.sha256(body.strip()), "chars": len(body.strip()),
           "file_hash": util.sha256(text), **extra}
    if with_text:
        row["body"] = body
        row["meta"] = meta
    return row


def versions(brain, note_id, *, limit=50, with_text=False) -> list[dict] | None:
    """Every version of one entry, newest first, or None when there is no such entry.

    Each: `ref` (a commit, or "current" for a working copy not committed yet), `at`,
    `title`, `summary`, `status`, `hash` and `chars` of its text, `text_changed` (False when
    only its details changed), the commit's `author` and `message`, and `changes`: the
    journal records that made it. With `with_text`, also its `body` and `meta`."""
    note = brain.state().index.note(note_id, include_archived=True)
    if note is None:
        return None
    full = brain.vault.path(*note.path.split("/"))
    try:
        with open(full, "rb") as handle:
            on_disk = _text(handle.read())
        changed_at = _iso(dt.datetime.fromtimestamp(os.path.getmtime(full), dt.timezone.utc))
    except OSError:
        on_disk, changed_at = None, util.now_iso()
    rows: list[dict] = []
    newest = None
    located = gitops.locate_own(brain.vault.root, brain.repo_root)
    if located:
        top, prefix = located
        commits = [c for c in gitops.file_log(top, prefix + note.path, limit)
                   if c["status"] != "D"]
        blobs = gitops.read_objects(top, [f"{c['commit']}:{c['path']}" for c in commits])
        for commit in commits:
            data = blobs.get(f"{commit['commit']}:{commit['path']}")
            if data is None:
                continue
            text = _text(data)
            newest = text if newest is None else newest
            path = commit["path"]
            rows.append(_version(commit["commit"][:12], _iso(_when(commit["at"]) or util.now()),
                                 text, with_text=with_text, commit=commit["commit"],
                                 author=commit["author"], message=commit["subject"],
                                 path=path[len(prefix):] if path.startswith(prefix) else path,
                                 committed=True))
    if on_disk is not None and (newest is None or on_disk != newest):
        rows.insert(0, _version("current", changed_at, on_disk, with_text=with_text,
                                path=note.path, committed=False,
                                message="Not committed yet" if rows else ""))
    if rows:
        rows[0]["current"] = True
    journal = events(brain, note_id, limit=1000)
    if not located:
        for record in brain.vault.decisions():
            if record.get("note") == note_id and record.get("previous"):
                rows.append(_version(f"journal:{record.get('at')}", str(record.get("at")),
                                     f"---\nid: {note_id}\n---\n{record['previous']}",
                                     with_text=with_text, committed=False,
                                     message=f"Before the {record.get('action')} on "
                                             f"{str(record.get('at'))[:10]}"))
        rows[1:] = sorted(rows[1:], key=lambda r: r["at"], reverse=True)
    for index, row in enumerate(rows):
        older = rows[index + 1] if index + 1 < len(rows) else None
        row["text_changed"] = older is None or older["hash"] != row["hash"]
        row["changes"] = []
    _attach(rows, [e for e in journal if str(e.get("action") or "") in CHANGES])
    return rows[:max(1, int(limit or 50))]


def _attach(rows: list[dict], changes: list[dict]) -> None:
    """Give each version the journal changes that made it.

    A change records the hash of the file it left (`file_hash`), so it belongs to the version
    holding exactly that file: the earliest one at or after the change (an undo can bring the
    same file back later). A change with no such version (an older record, or the first of
    two changes one commit holds) goes by time: to the first version at or after it."""
    if not rows:
        return
    times = [_when(r["at"]) for r in rows]
    slack = dt.timedelta(seconds=2)

    def by_time(moment) -> int:
        for index in range(len(rows) - 1, -1, -1):  # oldest first
            if times[index] is not None and times[index] + slack >= moment:
                return index
        return 0

    for change in changes:
        moment = _when(change.get("at"))
        if moment is None:
            continue
        home = None
        if change.get("file_hash"):
            matches = [i for i, r in enumerate(rows) if r.get("file_hash") == change["file_hash"]]
            later = [i for i in matches if times[i] is None or times[i] + slack >= moment]
            if later or matches:
                home = max(later) if later else max(matches)  # the earliest such version
        rows[by_time(moment) if home is None else home]["changes"].append(change)


def skill_versions(brain, name, *, limit=30, with_text=False) -> list[dict] | None:
    """Every version of one skill's procedure (its SKILL.md), newest first, or None when there
    is no such skill. Each as `versions` gives an entry's: `ref`, `at`, `hash` and `chars` of
    its text, `text_changed`, the commit's `author` and `message`; with `with_text`, also its
    `body` and `meta` (its description, triggers and the rest)."""
    skill = brain.state().index.skills.get(str(name or "").strip().lstrip("/"))
    if skill is None:
        return None
    return file_versions(brain, skill.path, limit=limit, with_text=with_text)


def file_versions(brain, relpath, *, limit=30, with_text=False) -> list[dict]:
    """Every version of one vault file (a skill's SKILL.md, an agent's AGENT.md), newest first,
    from git, with what is on disk now first when it is not committed yet."""
    full = brain.vault.path(*relpath.split("/"))
    try:
        with open(full, "rb") as handle:
            on_disk = _text(handle.read())
        changed_at = _iso(dt.datetime.fromtimestamp(os.path.getmtime(full), dt.timezone.utc))
    except OSError:
        on_disk, changed_at = None, util.now_iso()
    rows: list[dict] = []
    newest = None
    located = gitops.locate_own(brain.vault.root, brain.repo_root)
    if located:
        top, prefix = located
        commits = [c for c in gitops.file_log(top, prefix + relpath, limit)
                   if c["status"] != "D"]
        blobs = gitops.read_objects(top, [f"{c['commit']}:{c['path']}" for c in commits])
        for commit in commits:
            data = blobs.get(f"{commit['commit']}:{commit['path']}")
            if data is None:
                continue
            text = _text(data)
            newest = text if newest is None else newest
            rows.append(_version(commit["commit"][:12], _iso(_when(commit["at"]) or util.now()),
                                 text, with_text=with_text, commit=commit["commit"],
                                 author=commit["author"], message=commit["subject"],
                                 committed=True))
    if on_disk is not None and (newest is None or on_disk != newest):
        rows.insert(0, _version("current", changed_at, on_disk, with_text=with_text,
                                committed=False, message="Not committed yet" if rows else ""))
    if rows:
        rows[0]["current"] = True
    for index, row in enumerate(rows):
        older = rows[index + 1] if index + 1 < len(rows) else None
        row["text_changed"] = older is None or older["hash"] != row["hash"]
    return rows[:max(1, int(limit or 30))]


def version(brain, note_id, ref) -> dict | None:
    """One version of an entry, with its `body` and `meta`: `ref` is "current", a commit (or
    the first seven or more characters of one), or a journal reference from `versions`."""
    wanted = str(ref or "").strip()
    if not wanted:
        return None
    for row in versions(brain, note_id, limit=500, with_text=True) or []:
        if row["ref"] == wanted or (wanted == "current" and row.get("current")) or (
                len(wanted) >= 7 and str(row.get("commit") or "").startswith(wanted)):
            return row
    return None
