"""Context sheets' cell events in SQLite (the owner's list, item 3).

One file, `state/sheets.sqlite` in the vault, holds every sheet's append-only events: a row
made, a cell written, an alias, a decision. The events and the API on top (state.py) are as
they were in the per-row `.jsonl` logs; only where they live changed, so a busy sheet no
longer means a file and a commit per cell.

The database is the working store. It is kept out of git (`state/.gitignore`) and can be
rebuilt: git keeps the events as append-only text, one file a month
(`state/events/<YYYY-MM>.jsonl`, each line `{"seq", "sheet", "row", "event"}`), so diffs stay
small and a cloned Brain carries its whole sheet history. When the database is missing, or
behind the newest event in those files, it is rebuilt or caught up when the Brain opens it.

The event files and each sheet's SNAPSHOT.md are written and committed together once per beat
(`commit`, after a heartbeat beat and before a version is tagged) or, at the latest, with the
first write of a new day. Between those, a note's commit leaves them alone; events written
since the last sheets commit live only in the database until the next one.

Earlier per-row `.jsonl` logs are imported once, the first time a Brain opens the store, and
removed; the next sheets commit writes them into the monthly files.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import threading

from . import util

FILE = "sheets.sqlite"
FOLDER = "state"
EVENTS = "events"
IGNORE = f"{FILE}\n{FILE}-journal\n"
MONTH = re.compile(r"^\d{4}-\d{2}\.jsonl$")
_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    sheet TEXT NOT NULL,
    row TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_row ON events (sheet, row, seq);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def path(brain) -> str:
    return brain.vault.path(FOLDER, FILE)


def _events_folder(brain) -> str:
    return brain.vault.path(FOLDER, EVENTS)


def _connect(brain) -> sqlite3.Connection:
    target = path(brain)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    ignore = brain.vault.path(FOLDER, ".gitignore")
    if not os.path.isfile(ignore):
        util.atomic_write(ignore, IGNORE)
    conn = sqlite3.connect(target, timeout=30)
    conn.executescript(SCHEMA)
    return conn


@contextlib.contextmanager
def _db(brain):
    conn = _connect(brain)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _ready(brain) -> None:
    """Before the first read or write: rebuild or catch up the database from the monthly
    event files, and import earlier per-row logs."""
    if getattr(brain, "_sheets_ready", False):
        return
    with _LOCK:
        if getattr(brain, "_sheets_ready", False):
            return
        _catch_up(brain)
        _import(brain)
        brain._sheets_ready = True


def _month_files(brain) -> list[str]:
    folder = _events_folder(brain)
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if MONTH.match(n)]


def _catch_up(brain) -> int:
    """Insert the events in the monthly files that the database does not hold yet (all of
    them when it is new), with their own sequence numbers."""
    conn = _connect(brain)
    added = 0
    try:
        with conn:
            have = int(conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0])
            for file in _month_files(brain):
                for line in util.read_jsonl(file):
                    seq = int(line.get("seq") or 0)
                    if seq <= have or not isinstance(line.get("event"), dict):
                        continue
                    event = line["event"]
                    conn.execute(
                        "INSERT OR IGNORE INTO events (seq, sheet, row, at, body)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (seq, str(line.get("sheet") or ""), str(line.get("row") or ""),
                         str(event.get("at") or ""), json.dumps(event, sort_keys=True)))
                    added += 1
    finally:
        conn.close()
    return added


def _import(brain) -> int:
    """Move every sheet's per-row `.jsonl` cell logs into the database, once. Returns the
    events moved; the logs are removed (git keeps them in its history)."""
    base = brain.vault.path(FOLDER)
    if not os.path.isdir(base):
        return 0
    moved, gone = 0, []
    conn = _connect(brain)
    try:
        with conn:
            for sheet in sorted(os.listdir(base)):
                folder = os.path.join(base, sheet)
                if sheet == EVENTS or not os.path.isdir(folder):
                    continue
                for name in sorted(os.listdir(folder)):
                    if not name.endswith(".jsonl"):
                        continue
                    file = os.path.join(folder, name)
                    for event in util.read_jsonl(file):
                        conn.execute(
                            "INSERT INTO events (sheet, row, at, body) VALUES (?, ?, ?, ?)",
                            (sheet, name[:-6], str(event.get("at") or ""),
                             json.dumps(event, sort_keys=True)))
                        moved += 1
                    gone.append(file)
            if gone:
                top = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
                conn.execute("INSERT OR REPLACE INTO meta VALUES ('imported_seq', ?)",
                             (str(top[0]),))
    finally:
        conn.close()
    for file in gone:
        brain.vault.touch(file)
        os.remove(file)
    return moved


def events(brain, sheet: str, row: str) -> list[dict]:
    _ready(brain)
    with _db(brain) as conn:
        found = conn.execute(
            "SELECT body FROM events WHERE sheet = ? AND row = ? ORDER BY seq", (sheet, row))
        return [json.loads(b) for (b,) in found]


def row_ids(brain, sheet: str) -> list[str]:
    _ready(brain)
    with _db(brain) as conn:
        found = conn.execute(
            "SELECT DISTINCT row FROM events WHERE sheet = ? ORDER BY row", (sheet,))
        return [r for (r,) in found]


def has_row(brain, sheet: str, row: str) -> bool:
    _ready(brain)
    with _db(brain) as conn:
        return conn.execute("SELECT 1 FROM events WHERE sheet = ? AND row = ? LIMIT 1",
                            (sheet, row)).fetchone() is not None


def append(brain, sheet: str, row: str, new: list[dict]) -> None:
    _ready(brain)
    with _LOCK, _db(brain) as conn:
        conn.executemany(
            "INSERT INTO events (sheet, row, at, body) VALUES (?, ?, ?, ?)",
            [(sheet, row, str(e.get("at") or ""), json.dumps(e, sort_keys=True)) for e in new])
    brain.vault.touch(path(brain))


def last_seq(brain) -> int:
    _ready(brain)
    with _db(brain) as conn:
        return int(conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0])


def meta(brain, key: str) -> str | None:
    _ready(brain)
    with _db(brain) as conn:
        found = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return found[0] if found else None


def set_meta(brain, key: str, value: str) -> None:
    with _LOCK, _db(brain) as conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))


def cells_between(brain, after_seq: int, upto_seq: int | None = None) -> list[dict]:
    """The cell events written after `after_seq` (and up to `upto_seq`), oldest first."""
    _ready(brain)
    with _db(brain) as conn:
        found = conn.execute(
            "SELECT sheet, row, body FROM events WHERE seq > ? AND seq <= ? ORDER BY seq",
            (int(after_seq), int(upto_seq if upto_seq is not None else 2**62)))
        out = []
        for sheet, row, body in found:
            event = json.loads(body)
            if event.get("kind") == "cell":
                out.append({"sheet": sheet, "row": row, "column": event.get("column"),
                            "value": event.get("value"), "at": event.get("at")})
        return out


def _exported(brain) -> int:
    """The newest event already in the monthly files (each file is in sequence order)."""
    top = 0
    for file in _month_files(brain):
        lines = util.read_jsonl(file)
        if lines:
            top = max(top, int(lines[-1].get("seq") or 0))
    return top


def export(brain) -> list[str]:
    """Append the events not yet in the monthly files to them, each in the month it was
    written. Returns the files changed."""
    _ready(brain)
    since = _exported(brain)
    with _db(brain) as conn:
        found = conn.execute("SELECT seq, sheet, row, at, body FROM events WHERE seq > ?"
                             " ORDER BY seq", (since,)).fetchall()
    if not found:
        return []
    fallback = util.now_iso()[:7]
    by_month: dict[str, list[str]] = {}
    for seq, sheet, row, at, body in found:
        month = at[:7] if re.match(r"^\d{4}-\d{2}", str(at or "")) else fallback
        line = json.dumps({"seq": seq, "sheet": sheet, "row": row, "event": json.loads(body)},
                          sort_keys=True, ensure_ascii=False)
        by_month.setdefault(month, []).append(line)
    folder = _events_folder(brain)
    os.makedirs(folder, exist_ok=True)
    changed = []
    for month, lines in sorted(by_month.items()):
        file = os.path.join(folder, f"{month}.jsonl")
        brain.vault.touch(file)
        with open(file, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(line + "\n" for line in lines))
        changed.append(file)
    return changed


def paths(brain) -> list[str]:
    """What a sheets commit carries besides the event files: every SNAPSHOT.md and the
    `.gitignore` that keeps the database out."""
    base = brain.vault.path(FOLDER)
    out = [brain.vault.path(FOLDER, ".gitignore")]
    if os.path.isdir(base):
        for sheet in sorted(os.listdir(base)):
            folder = os.path.join(base, sheet)
            if sheet != EVENTS and os.path.isdir(folder):
                out.append(os.path.join(folder, "SNAPSHOT.md"))
    return out


def deferred(rel: str) -> bool:
    """A path (relative to the vault) that waits for the sheets commit, not a note's."""
    parts = rel.replace("\\", "/").split("/")
    if not parts or parts[0] != FOLDER:
        return False
    if len(parts) == 2:
        return parts[1] == ".gitignore" or parts[1].startswith(FILE)
    if len(parts) == 3 and parts[1] == EVENTS:
        return True
    return len(parts) == 3 and (parts[2] == "SNAPSHOT.md" or parts[2].endswith(".jsonl"))


def commit(brain, message: str) -> dict:
    """Write the new events to the monthly files and commit them with the snapshots (and
    any per-row logs an import removed)."""
    from . import gitops
    _ready(brain)
    written = export(brain)
    set_meta(brain, "committed_at", util.now_iso())
    rel = os.path.relpath(brain.vault.root, brain.repo_root).replace("\\", "/")
    prefix = "" if rel in (".", "") else rel + "/"
    pending = [p for p in gitops.uncommitted(brain.repo_root, brain.governed_folders())
               if p.startswith(prefix) and deferred(p[len(prefix):])]
    return gitops.commit(brain.repo_root, written + paths(brain)
                         + [os.path.join(brain.repo_root, p) for p in pending], message)


def due(brain) -> bool:
    """Whether the sheets were last committed on an earlier day (or never)."""
    last = meta(brain, "committed_at")
    if not last:
        return True
    return str(last)[:10] != util.now_iso()[:10]
