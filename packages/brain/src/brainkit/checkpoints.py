"""Undo points: a batch of governed decisions, taken back as a unit.

While a batch runs (approvals, rejections, archiving), the vault records every file the batch
is about to change, once, before its first change: the bytes it held, or that it did not
exist. When the batch ends, the undo point keeps those before-states and a hash of what each
file holds after. It lives in `vault/.brain/checkpoints/` (runtime state, never committed;
file bytes are stored once, by hash).

UNDO puts back exactly those files, and only when each still holds what the batch left there.
A file changed since (a later decision, an edit by hand) refuses the undo and names what
changed, so an undo never overwrites work it did not make. The decision journal is never
rewound: the undo appends what it reverted. Proposals the batch decided return to the inbox,
their staged files with them. An undo is recorded as an undo point of its own, so undoing it
redoes the batch.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import time

from . import util

KEEP = 200  # undo points kept; older ones (and bytes only they needed) are dropped
RUNTIME = ".brain/"
_BATCH = threading.Lock()


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _folder(brain) -> str:
    return os.path.join(brain.vault.runtime_dir, "checkpoints")


def _blob_path(brain, digest: str) -> str:
    return os.path.join(_folder(brain), "blobs", digest)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _current(brain, relpath: str) -> str | None:
    """The hash of what a vault file holds now, or None when it does not exist."""
    full = brain.vault.path(*relpath.split("/"))
    if not os.path.isfile(full):
        return None
    with open(full, "rb") as handle:
        return _digest(handle.read())


class Batch:
    """A batch in progress: the before-state of every vault file it touches (captured at the
    first touch), and one summary per decision, which callers add to `decisions`."""

    def __init__(self, brain):
        self.brain = brain
        self.before: dict[str, str | None] = {}
        self.decisions: list[dict] = []
        self.checkpoint: dict | None = None

    def capture(self, path) -> None:
        root = self.brain.vault.root
        full = os.path.abspath(path if os.path.isabs(path) else os.path.join(root, path))
        relpath = util.rel(full, root)
        if relpath == ".." or relpath.startswith("../") or os.path.isabs(relpath):
            return
        if os.path.isdir(full):
            for folder, _dirs, names in os.walk(full):
                for name in names:
                    self.capture(os.path.join(folder, name))
            return
        if relpath in self.before:
            return
        if not os.path.isfile(full):
            self.before[relpath] = None
            return
        with open(full, "rb") as handle:
            data = handle.read()
        digest = _digest(data)
        blob = _blob_path(self.brain, digest)
        if not os.path.exists(blob):
            util.atomic_write_bytes(blob, data)
        self.before[relpath] = digest


@contextlib.contextmanager
def batch(brain, *, actor, label=None, source=None, undoes=None, kind="decisions"):
    """Record everything the block changes as one undo point (`Batch.checkpoint`, or None
    when nothing changed). A batch started inside another joins it."""
    vault = brain.vault
    if vault.recording is not None:
        yield vault.recording
        return
    with _BATCH:
        current = Batch(brain)
        vault.recording = current
        try:
            yield current
        finally:
            vault.recording = None
        files = []
        for relpath, before in sorted(current.before.items()):
            after = _current(brain, relpath)
            if after != before:
                files.append({"path": relpath, "before": before, "after": after})
        if files:
            current.checkpoint = _save(brain, {
                "id": _new_id(), "seq": time.time_ns(), "at": util.now_iso(), "by": actor,
                "kind": kind,
                "label": label or describe(current.decisions),
                "source": source or {}, "decisions": current.decisions, "files": files,
                "undoes": undoes, "undone_by": None, "undone_at": None})


VERBS = (("approved", "approved"), ("edited", "edited"), ("restored", "restored"),
         ("updated", "updated"), ("verified", "verified"), ("marked", "marked"),
         ("rejected", "rejected"), ("archived", "archived"), ("unarchived", "brought back"),
         ("reverted", "reverted"), ("redone", "redone"))


def describe(decisions) -> str:
    """"Approved 3, rejected 1": what a batch did, in the order people read it."""
    parts = []
    for action, word in VERBS:
        count = sum(1 for d in decisions if d.get("action") == action)
        if count:
            parts.append(f"{word} {count}")
    text = ", ".join(parts) or "no decisions"
    return text[:1].upper() + text[1:]


def _new_id() -> str:
    stamp = util.now().strftime("%Y%m%dT%H%M%S%fZ")
    return f"cp-{stamp}-{os.urandom(3).hex()}"


def _write(brain, point: dict) -> None:
    util.atomic_write(os.path.join(_folder(brain), point["id"] + ".json"),
                      json.dumps(point, indent=1, ensure_ascii=False))


def _save(brain, point: dict) -> dict:
    _write(brain, point)
    _prune(brain)
    return point


def _load(brain, checkpoint_id) -> dict | None:
    name = str(checkpoint_id or "")
    if not name.startswith("cp-") or any(c in name for c in "/\\.:"):
        return None
    point = util.read_json(os.path.join(_folder(brain), name + ".json"))
    return point if isinstance(point, dict) else None


def _all(brain) -> list[dict]:
    folder = _folder(brain)
    if not os.path.isdir(folder):
        return []
    points = []
    for name in os.listdir(folder):
        if name.startswith("cp-") and name.endswith(".json"):
            point = util.read_json(os.path.join(folder, name))
            if isinstance(point, dict) and point.get("id"):
                points.append(point)
    points.sort(key=lambda p: (int(p.get("seq") or 0), str(p["id"])), reverse=True)
    return points


def _prune(brain) -> None:
    points = _all(brain)
    folder = _folder(brain)
    for old in points[KEEP:]:
        with contextlib.suppress(OSError):
            os.remove(os.path.join(folder, old["id"] + ".json"))
    needed = {f.get("before") for p in points[:KEEP] for f in p.get("files") or []}
    blobs = os.path.join(folder, "blobs")
    if os.path.isdir(blobs):
        for name in os.listdir(blobs):
            if name not in needed:
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(blobs, name))


def _what(brain, relpath: str) -> str:
    """A changed file, as a person knows it: the entry or proposal it holds."""
    st = brain.state()
    for note in list(st.index.notes.values()) + list(st.index.archived.values()):
        if note.path == relpath:
            return f"the entry “{note.title}”"
    if relpath.startswith("inbox/"):
        return f"the proposal {os.path.splitext(os.path.basename(relpath))[0]}"
    return relpath


def _blocked(brain, point: dict) -> list[dict]:
    return [{"path": f["path"], "what": _what(brain, f["path"])}
            for f in point.get("files") or [] if _current(brain, f["path"]) != f.get("after")]


def list_checkpoints(brain, limit=50) -> list[dict]:
    """Undo points, newest first, each saying whether it can be undone now and, when not,
    what changed since."""
    rows = []
    for point in _all(brain)[:max(1, int(limit or 50))]:
        blocked = [] if point.get("undone_by") else _blocked(brain, point)
        rows.append(dict(point, blocked=blocked,
                         undoable=not point.get("undone_by") and not blocked))
    return rows


def get(brain, checkpoint_id) -> dict | None:
    return _load(brain, checkpoint_id)


def undo(brain, checkpoint_id, *, actor=None):
    """Put back what an undo point changed, recorded as a new undo point of its own."""
    from . import governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    point = _load(brain, checkpoint_id)
    if point is None:
        return _result(f"No undo point {checkpoint_id!r}.", {"status": "missing"}, True)
    if point.get("undone_by"):
        return _result(f"“{point['label']}” was already undone ({point['undone_by']}); undo "
                       "that instead to bring it back.", {"status": "conflict"}, True)
    blocked = _blocked(brain, point)
    if blocked:
        names = ", ".join(b["what"] for b in blocked[:5])
        more = f" and {len(blocked) - 5} more" if len(blocked) > 5 else ""
        return _result(f"Cannot undo “{point['label']}”: {names}{more} changed since. Undo "
                       "the later change first, or change it by hand.",
                       {"status": "conflict", "blocked": blocked}, True)
    redo = point.get("kind") == "undo"
    base = str(point.get("label") or "")
    for prefix in ("Undo: ", "Redo: "):
        if base.startswith(prefix):
            base = base[len(prefix):]
    label = ("Redo: " if redo else "Undo: ") + base
    verb = "redone" if redo else "reverted"
    touched = []
    with batch(brain, actor=who, label=label, source=point.get("source"),
               undoes=point["id"], kind="redo" if redo else "undo") as current:
        for entry in point.get("files") or []:
            full = brain.vault.path(*entry["path"].split("/"))
            brain.vault.touch(full)
            if entry.get("before"):
                with open(_blob_path(brain, entry["before"]), "rb") as handle:
                    util.atomic_write_bytes(full, handle.read())
            elif os.path.exists(full):
                os.remove(full)
                _prune_empty(os.path.dirname(full), brain.vault.root)
            touched.append(full)
        for decision in reversed(point.get("decisions") or []):
            # What the person first decided, however many undos and redos ago.
            original = (decision.get("reverted") or decision.get("redone")
                        or decision.get("action"))
            record = {"at": util.now_iso(), "action": verb, "by": who,
                      "checkpoint": point["id"], verb: original}
            for key in ("proposal", "note", "kind", "title"):
                if decision.get(key):
                    record[key] = decision[key]
            brain.vault.append_decision(record)
            summary = {k: v for k, v in decision.items() if k not in ("reverted", "redone")}
            current.decisions.append(dict(summary, action=verb, **{verb: original}))
        touched.append(brain.vault.path("journal", "decisions.jsonl"))
    committed = [p for p in touched
                 if not util.rel(p, brain.vault.root).startswith(RUNTIME)]
    outcome = brain.after_write(committed, label)
    if current.checkpoint:
        stored = _load(brain, point["id"]) or point
        stored.update(undone_by=current.checkpoint["id"], undone_at=util.now_iso())
        _write(brain, stored)
    return _result(f"{label}: done.",
                   {"status": "undone", "undone": point["id"], "checkpoint": current.checkpoint,
                    "commit": outcome.get("commit")})


def _prune_empty(folder: str, root: str) -> None:
    """Remove folders an undo left empty, up to (not including) the top-level folder."""
    root = os.path.abspath(root)
    folder = os.path.abspath(folder)
    while folder != root and os.path.dirname(folder) != root:
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)
