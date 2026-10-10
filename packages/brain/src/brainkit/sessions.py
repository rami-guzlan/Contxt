"""The session ledger: what each conversation has already been handed, and what each entry
has been used for.

One SQLite file under the vault's `.brain/` folder, shared by every process (MCP server,
CLI, local API). It is operational memory, not knowledge: deleting it loses deduplication
history and usage counts, nothing else.

DEDUPLICATION RULE. A note body is withheld from a later packet only when the SAME session
already received the SAME body hash. A caller that lost its context (a compacted or new
conversation) passes `fresh=true` or a new session id and receives everything again; from a
fresh call on, nothing the session got before it counts as held (`refresh`). Over-delivery costs
tokens; silent omission costs correctness, so the rule errs toward sending.

HOOKS share a conversation's session: Claude Code's hooks name it `cc:<its session id>`, push
briefs under it and record what they hand over outside a brief (`hand`), so the model's own
`get_task_context` calls with that session id send only what is new.

USAGE. Every handout is counted by day in `usage_daily` (how many conversations got the
item, and how: in a packet, opened afterwards, or in AI work the workspace ran), which is
never pruned, so an entry's use is known for good. The detail behind it (each delivery, with
the version and why routing picked it, and each packet's request) is kept for
`sessions.retention_days` (90 by default), then pruned.

BRIEF DECISIONS. For every brief, every candidate the retrieval engine looked at (or, in
fallback, what routing scored): its keyword, meaning and reranker scores, the decision model's
answers, the outcome (body, pointer, listed, held, out) and its reason, with the engine's mode,
the lock's fingerprint, the cuts and each layer's time in the packet's data. Pruned with the
detail above. An audit reads these, never recomputes them.

MODEL CALLS. Background work that pays a model (a check, the knowledge agent, a run) records
its tokens and cost in `model_calls`, pruned like the detail above, and by day in
`model_daily`, kept for good: the fourth line of what context costs (costs.py).
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import secrets
import sqlite3
import threading

from . import util

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, principal TEXT, created TEXT, seen TEXT, label TEXT);
CREATE TABLE IF NOT EXISTS packets (
    id TEXT PRIMARY KEY, session_id TEXT, at TEXT, request TEXT, mode TEXT,
    tokens INTEGER, text TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS deliveries (
    session_id TEXT, packet_id TEXT, kind TEXT, item TEXT, hash TEXT, tokens INTEGER, at TEXT);
CREATE INDEX IF NOT EXISTS deliveries_session ON deliveries(session_id);
CREATE INDEX IF NOT EXISTS deliveries_item ON deliveries(kind, item);
CREATE INDEX IF NOT EXISTS packets_session ON packets(session_id);
CREATE TABLE IF NOT EXISTS usage_daily (
    day TEXT NOT NULL, kind TEXT NOT NULL, item TEXT NOT NULL,
    conversations INTEGER NOT NULL DEFAULT 0, in_packets INTEGER NOT NULL DEFAULT 0,
    opened INTEGER NOT NULL DEFAULT 0, in_work INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, kind, item));
CREATE TABLE IF NOT EXISTS ledger_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS outputs (
    path TEXT PRIMARY KEY, session_id TEXT, at TEXT, title TEXT, client TEXT);
CREATE TABLE IF NOT EXISTS dismissed (key TEXT PRIMARY KEY, at TEXT);
CREATE TABLE IF NOT EXISTS verdicts (
    key TEXT PRIMARY KEY, relation TEXT, detail TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS kernels (fingerprint TEXT PRIMARY KEY, at TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS brief_decisions (
    packet_id TEXT, session_id TEXT, at TEXT, kind TEXT, item TEXT, keyword REAL,
    meaning REAL, rerank REAL, kev TEXT, outcome TEXT, reason TEXT, found_by TEXT,
    round INTEGER);
CREATE INDEX IF NOT EXISTS brief_decisions_packet ON brief_decisions(packet_id);
CREATE TABLE IF NOT EXISTS model_calls (
    at TEXT, job TEXT, model TEXT, tokens_in INTEGER, tokens_out INTEGER, cache_read INTEGER,
    cache_write INTEGER, cost REAL, ms INTEGER, ref TEXT, measured INTEGER);
CREATE INDEX IF NOT EXISTS model_calls_at ON model_calls(at);
CREATE TABLE IF NOT EXISTS model_daily (
    day TEXT NOT NULL, job TEXT NOT NULL, model TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0, tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0, cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (day, job, model));
"""

# How an item reached a conversation: the usage_daily column each way counts in.
VIA = {"packet": "in_packets", "opened": "opened", "work": "in_work"}
FOLLOWUP = "followup"  # the packet id of items opened after a packet (get_note and the like)
WORK = "work"          # the packet id of items handed to AI work the workspace ran
HOOK = "hook"          # the packet id of items a client's hook handed over outside a brief


class Ledger:
    def __init__(self, path: str, retention_days: int = 90):
        self.path = path
        self.retention_days = int(retention_days or 90)
        self._lock = threading.Lock()
        self._conn_lock = threading.RLock()
        self._conn = None
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
        self._pruned = False

    @staticmethod
    def _migrate(conn) -> None:
        """Bring an older ledger up to date: deliveries say why an item was picked, and the
        daily counts start from the deliveries already kept (once, whichever process is
        first)."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(deliveries)")}
        if "reason" not in columns:
            with contextlib.suppress(sqlite3.OperationalError):  # another process added it
                conn.execute("ALTER TABLE deliveries ADD COLUMN reason TEXT")
        held = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        if "engine" not in held:
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE sessions ADD COLUMN engine TEXT")
        if "epoch" not in held:
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE sessions ADD COLUMN epoch INTEGER")
        if "epoch" not in columns:
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE deliveries ADD COLUMN epoch INTEGER")
        claimed = conn.execute("INSERT OR IGNORE INTO ledger_meta (key, value) VALUES "
                               "('usage_backfill', ?)", (util.now_iso(),)).rowcount
        if claimed:
            conn.execute(
                "INSERT INTO usage_daily (day, kind, item, conversations, in_packets, opened, "
                "in_work, tokens) "
                "SELECT substr(at, 1, 10), kind, item, COUNT(DISTINCT session_id), "
                f"SUM(packet_id NOT IN ('{FOLLOWUP}', '{WORK}')), "
                f"SUM(packet_id = '{FOLLOWUP}'), SUM(packet_id = '{WORK}'), "
                "COALESCE(SUM(tokens), 0) FROM deliveries WHERE at IS NOT NULL "
                "GROUP BY 1, 2, 3 ON CONFLICT(day, kind, item) DO NOTHING")

    @contextlib.contextmanager
    def _connect(self):
        """The process's one connection, serialized by a lock; commits on success.

        One connection per process (MCP server, CLI, UI) rather than one per operation: a
        packet touches the ledger four times, and reconnecting each time cost more than
        routing the request. WAL mode lets the processes share the file.
        """
        with self._conn_lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                try:
                    self._conn.execute("PRAGMA journal_mode=WAL")
                except sqlite3.DatabaseError:
                    pass
            try:
                yield self._conn
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    def close(self):
        with self._conn_lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ sessions
    @staticmethod
    def mint() -> str:
        return "sess-" + secrets.token_hex(6)

    @staticmethod
    def valid(session_id) -> bool:
        text = str(session_id or "").strip()
        return 3 <= len(text) <= 120 and all(c.isalnum() or c in "-_.:" for c in text)

    def touch(self, session_id: str, principal: str = "", label: str = "",
              engine: str = "") -> None:
        """Note a session as seen now; `label` names the app it came from (the MCP client)
        and `engine` the engine code it ran, each kept from the first time it is known."""
        now = util.now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, principal, created, seen, label, engine) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET seen = excluded.seen, "
                "principal = COALESCE(NULLIF(sessions.principal, ''), excluded.principal), "
                "label = COALESCE(NULLIF(sessions.label, ''), excluded.label), "
                "engine = COALESCE(NULLIF(sessions.engine, ''), excluded.engine)",
                (session_id, principal, now, now, str(label or "") or None,
                 str(engine or "") or None))
        self.prune()

    def session_principal(self, session_id: str) -> str | None:
        """Who a conversation asked as (the last scope of its caller's chain)."""
        with self._connect() as conn:
            row = conn.execute("SELECT principal FROM sessions WHERE id = ?",
                               (session_id,)).fetchone()
        return (row["principal"] or None) if row is not None else None

    def exists(self, session_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM sessions WHERE id = ?",
                                (session_id,)).fetchone() is not None

    def refresh(self, session_id: str) -> None:
        """The conversation lost what it held (a compaction, a clear): from now on, nothing
        it was handed before counts as held. The record of what it got stays: each refresh
        starts a new epoch of the session, and only the current epoch's deliveries are held."""
        now = util.now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, principal, created, seen, epoch) "
                "VALUES (?, '', ?, ?, 1) ON CONFLICT(id) DO UPDATE SET "
                "epoch = COALESCE(sessions.epoch, 0) + 1, seen = excluded.seen",
                (session_id, now, now))

    def hand(self, session_id: str, items, *, principal: str = "", label: str = "") -> None:
        """Items a hook gave a conversation outside a brief (the person's kernel layer at
        session start): held from now on, and counted as handed out."""
        self.touch(session_id, principal, label)
        self._record(session_id, HOOK, items, "packet")

    # ------------------------------------------------------------------ deliveries
    def delivered(self, session_id: str) -> dict:
        """{(kind, item): {"hash", "packet_id", "at"}} for everything this session holds."""
        out = {}
        if not session_id:
            return out
        with self._connect() as conn:
            epoch = self._epoch(conn, session_id)
            for row in conn.execute(
                    "SELECT kind, item, hash, packet_id, at FROM deliveries "
                    "WHERE session_id = ? AND COALESCE(epoch, 0) = ? ORDER BY at",
                    (session_id, epoch)):
                out[(row["kind"], row["item"])] = {
                    "hash": row["hash"], "packet_id": row["packet_id"], "at": row["at"]}
        return out

    def record(self, session_id: str, packet_id: str, request: str, mode: str, text: str,
               data: dict, items) -> None:
        """Store one packet and the items it delivered: [(kind, item, hash, tokens)], each
        optionally with a fifth element, why routing picked it."""
        now = util.now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO packets (id, session_id, at, request, mode, tokens, "
                "text, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (packet_id, session_id, now, request, mode, util.tokens(text), text,
                 json.dumps(data, ensure_ascii=False, default=str)))
            self._deliver(conn, session_id, packet_id, items, "packet", now)

    def record_items(self, session_id: str, packet_id: str, items) -> None:
        """Items opened after a packet (`packet_id` "followup"), or handed out some other
        way; counted as opened."""
        self._record(session_id, packet_id, items, "opened" if packet_id == FOLLOWUP
                     else "packet")

    def record_use(self, ref: str, items, *, principal: str = "workspace") -> str:
        """Items handed to AI work run outside a conversation (the workspace's task runs):
        recorded under the session `work:<ref>`, so an entry's use names the run. Returns
        that session id."""
        session_id = f"{WORK}:{ref}"
        if not self.valid(session_id):
            raise ValueError(f"{ref!r} cannot name a session")
        self.touch(session_id, principal)
        self._record(session_id, WORK, items, "work")
        return session_id

    def _record(self, session_id, packet_id, items, via) -> None:
        with self._connect() as conn:
            self._deliver(conn, session_id, packet_id, items, via, util.now_iso())

    @staticmethod
    def _epoch(conn, session_id) -> int:
        """The session's current epoch: how many times it was refreshed (0 if never)."""
        found = conn.execute("SELECT epoch FROM sessions WHERE id = ?",
                             (session_id,)).fetchone()
        return int((found["epoch"] if found is not None else 0) or 0)

    def _deliver(self, conn, session_id, packet_id, items, via, now) -> None:
        rows = [tuple(item) + (None,) * (5 - len(item)) for item in items]
        epoch = self._epoch(conn, session_id)
        day = now[:10]
        held = {(r["kind"], r["item"]) for r in conn.execute(
            "SELECT kind, item FROM deliveries WHERE session_id = ? AND at >= ?",
            (session_id, day))}
        conn.executemany(
            "INSERT INTO deliveries (session_id, packet_id, kind, item, hash, tokens, at, "
            "reason, epoch) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(session_id, packet_id, kind, item, digest, int(tokens or 0), now, reason, epoch)
             for kind, item, digest, tokens, reason in rows])
        column = VIA[via]
        for kind, item, _digest, tokens, _reason in rows:
            first = (kind, item) not in held
            held.add((kind, item))
            conn.execute(
                f"INSERT INTO usage_daily (day, kind, item, conversations, {column}, tokens) "
                "VALUES (?, ?, ?, ?, 1, ?) ON CONFLICT(day, kind, item) DO UPDATE SET "
                f"conversations = conversations + excluded.conversations, "
                f"{column} = {column} + 1, tokens = tokens + excluded.tokens",
                (day, kind, item, 1 if first else 0, int(tokens or 0)))

    def record_decisions(self, packet_id: str, session_id: str, rows) -> None:
        """Every candidate's scores and outcome for one brief (engine.Audit.rows)."""
        now = util.now_iso()
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO brief_decisions (packet_id, session_id, at, kind, item, keyword, "
                "meaning, rerank, kev, outcome, reason, found_by, round) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(packet_id, session_id, now, r.get("kind"), r.get("item"), r.get("keyword"),
                  r.get("meaning"), r.get("rerank"),
                  json.dumps(r.get("kev") or {}, ensure_ascii=False), r.get("outcome"),
                  r.get("reason"), r.get("found_by"), int(r.get("round") or 0))
                 for r in rows])

    def decisions(self, packet_id: str) -> list[dict]:
        """What `record_decisions` kept for one brief, in the order it was written."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT kind, item, keyword, meaning, rerank, kev, outcome, reason, found_by, "
                "round FROM brief_decisions WHERE packet_id = ? ORDER BY rowid",
                (packet_id,)).fetchall()
        out = []
        for row in rows:
            found = dict(row)
            try:
                found["kev"] = json.loads(found.get("kev") or "{}")
            except ValueError:
                found["kev"] = {}
            out.append(found)
        return out

    def packet(self, packet_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM packets WHERE id = ?", (packet_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        try:
            out["data"] = json.loads(out.get("data") or "{}")
        except ValueError:
            out["data"] = {}
        return out

    def record_kernel(self, fingerprint: str, text: str) -> None:
        """Keep the startup context a conversation was handed, once per version (its
        fingerprint), so a request can show exactly what it got."""
        if not fingerprint or not text:
            return
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO kernels (fingerprint, at, text) VALUES (?, ?, ?)",
                         (str(fingerprint), util.now_iso(), str(text)))

    def kernel_text(self, fingerprint: str) -> str | None:
        """The startup context kept for this version, if it was kept."""
        with self._connect() as conn:
            row = conn.execute("SELECT text FROM kernels WHERE fingerprint = ?",
                               (str(fingerprint or ""),)).fetchone()
        return row["text"] if row is not None else None

    def last_packet(self, session_id: str) -> dict | None:
        """The most recent packet in this session, for follow-up continuity: its data, plus
        the request it answered (`request`)."""
        with self._connect() as conn:
            row = conn.execute("SELECT request, data FROM packets WHERE session_id = ? "
                               "ORDER BY at DESC, rowid DESC LIMIT 1", (session_id,)).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["data"] or "{}")
        except ValueError:
            return None
        data.setdefault("request", row["request"] or "")
        return data

    def session_summary(self, session_id: str) -> dict:
        with self._connect() as conn:
            packets = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(tokens), 0) AS t FROM packets "
                "WHERE session_id = ?", (session_id,)).fetchone()
            items = conn.execute(
                "SELECT kind, COUNT(DISTINCT item) AS n FROM deliveries WHERE session_id = ? "
                "GROUP BY kind", (session_id,)).fetchall()
        return {"packets": packets["n"], "packet_tokens": packets["t"],
                "items": {row["kind"]: row["n"] for row in items}}

    # ------------------------------------------------------------------ usage
    def usage(self, since: str, kind: str = "note") -> dict[str, int]:
        """{item: how many conversations (and AI work runs) it went to} since an ISO moment,
        counted by day."""
        with self._connect() as conn:
            return {row["item"]: int(row["n"]) for row in conn.execute(
                "SELECT item, SUM(conversations) AS n FROM usage_daily "
                "WHERE kind = ? AND day >= ? GROUP BY item", (kind, str(since)[:10]))}

    def usage_table(self, kind: str | None = None) -> dict[tuple[str, str], dict]:
        """{(kind, item): {"total", "d7", "d30", "last", "tokens", "in_packets", "opened",
        "in_work"}} for every item ever handed out: uses in all, in the last 7 and 30 days,
        and the last day it was used."""
        today = util.now().date()
        d7 = (today - _dt.timedelta(days=6)).isoformat()
        d30 = (today - _dt.timedelta(days=29)).isoformat()
        query = ("SELECT kind, item, SUM(conversations) AS total, "
                 "SUM(CASE WHEN day >= ? THEN conversations ELSE 0 END) AS d7, "
                 "SUM(CASE WHEN day >= ? THEN conversations ELSE 0 END) AS d30, "
                 "MAX(day) AS last, SUM(tokens) AS tokens, SUM(in_packets) AS in_packets, "
                 "SUM(opened) AS opened, SUM(in_work) AS in_work FROM usage_daily")
        params: list = [d7, d30]
        if kind:
            query += " WHERE kind = ?"
            params.append(kind)
        query += " GROUP BY kind, item"
        with self._connect() as conn:
            return {(row["kind"], row["item"]): {
                "total": int(row["total"] or 0), "d7": int(row["d7"] or 0),
                "d30": int(row["d30"] or 0), "last": row["last"],
                "tokens": int(row["tokens"] or 0), "in_packets": int(row["in_packets"] or 0),
                "opened": int(row["opened"] or 0), "in_work": int(row["in_work"] or 0)}
                for row in conn.execute(query, params)}

    def first_day(self) -> str | None:
        """The first day any use was recorded: counts say nothing about the time before."""
        with self._connect() as conn:
            row = conn.execute("SELECT MIN(day) AS d FROM usage_daily").fetchone()
        return row["d"] if row and row["d"] else None

    def item_usage(self, kind: str, item: str, *, days: int = 90, limit: int = 50) -> dict:
        """One item's use: `daily` counts for the last `days` days, and `recent` handouts
        still in the detail window (when, to which conversation or AI work, the version,
        why it was picked, and the request the packet answered)."""
        since = (util.now().date() - _dt.timedelta(days=max(1, int(days)) - 1)).isoformat()
        with self._connect() as conn:
            daily = [dict(r) for r in conn.execute(
                "SELECT day, conversations, in_packets, opened, in_work, tokens "
                "FROM usage_daily WHERE kind = ? AND item = ? AND day >= ? ORDER BY day",
                (kind, item, since))]
            recent = [dict(r) for r in conn.execute(
                "SELECT d.session_id, d.packet_id, d.at, d.hash, d.reason, d.tokens, "
                "p.request, p.mode FROM deliveries d LEFT JOIN packets p ON p.id = d.packet_id "
                "WHERE d.kind = ? AND d.item = ? ORDER BY d.at DESC, d.rowid DESC LIMIT ?",
                (kind, item, int(limit)))]
        for row in recent:
            row["via"] = ("work" if row["packet_id"] == WORK else
                          "opened" if row["packet_id"] == FOLLOWUP else "packet")
        return {"daily": daily, "recent": recent}

    def reach(self, item: str, *, days: int = 30, limit: int = 3) -> dict:
        """How far one note reaches, from the detail window: the conversations it went into
        in the last `days` days (as a note or as a must-hold's line) and the most recent
        requests that received it, newest first."""
        since = (util.now() - _dt.timedelta(days=max(1, int(days)))
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(DISTINCT session_id) AS n FROM deliveries WHERE item = ? AND "
                "kind IN ('note', 'must') AND at >= ?", (item, since)).fetchone()
            rows = conn.execute(
                "SELECT p.request, MAX(d.at) AS at, s.label AS client FROM deliveries d "
                "JOIN packets p ON p.id = d.packet_id LEFT JOIN sessions s ON s.id = p.session_id "
                "WHERE d.item = ? AND d.kind IN ('note', 'must') AND COALESCE(p.request, '') != '' "
                "GROUP BY p.request ORDER BY MAX(d.at) DESC LIMIT ?",
                (item, max(1, int(limit)))).fetchall()
        return {"conversations": int(count["n"] or 0),
                "recent": [{"request": r["request"], "at": r["at"], "client": r["client"] or ""}
                           for r in rows]}

    # ------------------------------------------------------------------ model checks
    def verdicts(self, keys) -> dict[str, dict]:
        """What a model already said about pairs of texts, by pair key: {"relation",
        "detail", "at"}. A pair is asked about once; a new text is a new pair."""
        keys = [str(k) for k in keys or [] if k]
        if not keys:
            return {}
        out = {}
        with self._connect() as conn:
            for start in range(0, len(keys), 500):
                chunk = keys[start:start + 500]
                marks = ",".join("?" * len(chunk))
                for row in conn.execute(
                        f"SELECT key, relation, detail, at FROM verdicts WHERE key IN ({marks})",
                        chunk):
                    try:
                        detail = json.loads(row["detail"] or "{}")
                    except ValueError:
                        detail = {}
                    out[row["key"]] = {"relation": row["relation"], "detail": detail,
                                       "at": row["at"]}
        return out

    def record_verdicts(self, rows) -> int:
        """Keep a model's verdicts: [{"key", "relation", "detail"}]."""
        now = util.now_iso()
        kept = 0
        with self._connect() as conn:
            for row in rows or []:
                if not row.get("key") or not row.get("relation"):
                    continue
                conn.execute(
                    "INSERT INTO verdicts (key, relation, detail, at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET relation = excluded.relation, "
                    "detail = excluded.detail, at = excluded.at",
                    (str(row["key"]), str(row["relation"]),
                     json.dumps(row.get("detail") or {}, ensure_ascii=False), now))
                kept += 1
        return kept

    def verdicts_stamp(self) -> str:
        """Changes when a verdict comes in: what a cached review is checked against."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n, MAX(at) AS at FROM verdicts").fetchone()
        return f"{row['n']}:{row['at'] or ''}"

    def verdicts_since(self, since: str, *, prefix: str = "") -> int:
        """Pairs a model was asked about since an ISO moment (those whose key starts with
        `prefix`): what a cap counts."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM verdicts WHERE at >= ? AND key LIKE ?",
                               (since, prefix.replace("%", "") + "%")).fetchone()
        return int(row["n"] or 0)

    def handouts(self, kind: str, item: str) -> list[dict]:
        """Every delivery of one item still in the detail window, oldest first: session,
        version (`hash`) and when. Recall reads it: who got an older version."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT session_id, packet_id, hash, at FROM deliveries "
                "WHERE kind = ? AND item = ? ORDER BY at", (kind, item))]

    def flow(self, since: str) -> dict:
        """Delivery since an ISO moment: conversations served, packets, AI work runs,
        entries handed out (distinct), tokens handed out, and packets that brought nothing."""
        with self._connect() as conn:
            packets = conn.execute(
                "SELECT COUNT(*) AS n, COUNT(DISTINCT session_id) AS s, "
                "COALESCE(SUM(tokens), 0) AS t FROM packets WHERE at >= ?", (since,)).fetchone()
            items = conn.execute(
                "SELECT COUNT(DISTINCT item) AS n, COALESCE(SUM(tokens), 0) AS t, "
                f"COUNT(DISTINCT CASE WHEN packet_id = '{WORK}' THEN session_id END) AS w "
                "FROM deliveries WHERE kind = 'note' AND at >= ?", (since,)).fetchone()
        empty = sum(1 for g in self.gaps(since) if g["kind"] == "nothing")
        return {"packets": packets["n"], "conversations": packets["s"],
                "packet_tokens": packets["t"], "entries": items["n"],
                "entry_tokens": items["t"], "work_runs": items["w"], "empty": empty}

    def weekly(self, weeks: int = 8) -> list[dict]:
        """Conversations the brain served in each of the last `weeks` weeks, oldest first:
        [{"start", "end", "conversations", "packets"}], a week ending today last. The days
        are the owner's (`util.today()`): packets are stamped in UTC, and each counts on the
        owner's date when it came. Packets are kept for the retention window, so weeks
        before it count none."""
        weeks = max(1, min(int(weeks), 26))
        today = util.today_date()
        start = today - _dt.timedelta(days=7 * weeks - 1)
        buckets = [{"start": (start + _dt.timedelta(days=7 * i)).isoformat(),
                    "end": (start + _dt.timedelta(days=7 * i + 6)).isoformat(),
                    "sessions": set(), "packets": 0} for i in range(weeks)]
        # A day early: no time zone is a whole day from UTC, and the offset check below
        # drops the packets from before the owner's first day.
        since = (start - _dt.timedelta(days=1)).isoformat()
        with self._connect() as conn:
            rows = conn.execute("SELECT session_id, at FROM packets WHERE at >= ?",
                                (since,)).fetchall()
        for row in rows:
            day = util.local_date(row["at"])
            if day is None:
                continue
            offset = (day - start).days // 7
            if 0 <= offset < weeks:
                buckets[offset]["sessions"].add(row["session_id"])
                buckets[offset]["packets"] += 1
        return [{"start": b["start"], "end": b["end"], "conversations": len(b["sessions"]),
                 "packets": b["packets"]} for b in buckets]

    # ------------------------------------------------------------------ outputs
    def record_output(self, path: str, session_id: str, *, title: str = "",
                      client: str = "") -> None:
        """A file an AI saved for the person, and the conversation it was made in."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO outputs (path, session_id, at, title, client) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET session_id = excluded.session_id, "
                "at = excluded.at, title = excluded.title, "
                "client = COALESCE(NULLIF(excluded.client, ''), outputs.client)",
                (path, session_id, util.now_iso(), title, client))

    def output(self, path: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM outputs WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def session_items(self, session_id: str) -> list[tuple]:
        """Everything one session was handed (an AI work run's `work:<run>`), oldest first."""
        with self._connect() as conn:
            return [(r["kind"], r["item"], r["tokens"], r["reason"]) for r in conn.execute(
                "SELECT kind, item, tokens, reason FROM deliveries WHERE session_id = ? "
                "ORDER BY at, rowid", (session_id,))]

    def requests(self, *, limit: int = 50, before: str | None = None,
                 session: str | None = None, packet: str | None = None) -> list[dict]:
        """Packets newest first (older than the packet `before` names, for the next page):
        the request, its tokens, its session's app (`client`), each piece it delivered with
        why, and what the conversation opened after it (until its next packet). With
        `packet`, only that one, with the text it was handed (`text`)."""
        query = ("SELECT p.id, p.session_id, p.at, p.request, p.mode, p.tokens, p.data, "
                 + ("p.text, " if packet else "")
                 + "s.label AS client, s.engine AS engine FROM packets p "
                 "LEFT JOIN sessions s ON s.id = p.session_id")
        params: list = []
        where = []
        if before:
            where.append("(p.at, p.rowid) < (SELECT at, rowid FROM packets WHERE id = ?)")
            params.append(str(before))
        if session:
            where.append("p.session_id = ?")
            params.append(str(session))
        if packet:
            where.append("p.id = ?")
            params.append(str(packet))
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY p.at DESC, p.rowid DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(query, params)]
            if not rows:
                return []
            ids = [r["id"] for r in rows]
            marks = ",".join("?" * len(ids))
            pieces: dict[str, list] = {}
            for d in conn.execute(
                    f"SELECT packet_id, kind, item, tokens, reason FROM deliveries "
                    f"WHERE packet_id IN ({marks}) ORDER BY rowid", ids):
                pieces.setdefault(d["packet_id"], []).append(
                    (d["kind"], d["item"], d["tokens"], d["reason"]))
            sessions = sorted({r["session_id"] for r in rows})
            smarks = ",".join("?" * len(sessions))
            opened = [dict(d) for d in conn.execute(
                f"SELECT session_id, kind, item, tokens, reason, at FROM deliveries WHERE "
                f"packet_id = ? AND session_id IN ({smarks}) ORDER BY at",
                [FOLLOWUP, *sessions])]
            starts = {}
            for p in conn.execute(
                    f"SELECT session_id, id, at FROM packets WHERE session_id IN ({smarks}) "
                    f"ORDER BY at, rowid", sessions):
                starts.setdefault(p["session_id"], []).append((p["at"], p["id"]))
        after: dict[str, list] = {}
        for d in opened:
            owner = None
            for at, packet_id in starts.get(d["session_id"], []):
                if at <= d["at"]:
                    owner = packet_id
            if owner:
                after.setdefault(owner, []).append(
                    (d["kind"], d["item"], d["tokens"], d["reason"]))
        newest = {}
        for session, packets in starts.items():
            newest[session] = packets[-1][1] if packets else None
        for row in rows:
            try:
                row["data"] = json.loads(row.get("data") or "{}")
            except ValueError:
                row["data"] = {}
            row["items"] = pieces.get(row["id"], [])
            row["opened"] = after.get(row["id"], [])
            row["last_in_session"] = newest.get(row["session_id"]) == row["id"]
        return rows

    # ------------------------------------------------------------------ gaps
    def gaps(self, since: str, *, limit: int = 200) -> list[dict]:
        """Requests the brain served poorly since an ISO moment, newest first:

        - `nothing`: a packet that brought no entry (`close` lists the entries it named as
          the closest, when any came near);
        - `searched`: an entry a conversation opened that none of its packets brought or
          listed, so the AI found it some other way (search_notes): routing missed it.

        Dismissed gaps (`dismiss`) stay out."""
        hidden = self.dismissed()
        out = []
        with self._connect() as conn:
            packets = [dict(r) for r in conn.execute(
                "SELECT id, session_id, at, request, mode, data FROM packets WHERE at >= ? "
                "ORDER BY at", (since,))]
            opened = [dict(r) for r in conn.execute(
                "SELECT session_id, item, at FROM deliveries WHERE kind = 'note' AND "
                "packet_id = ? AND at >= ? ORDER BY at", (FOLLOWUP, since))]
        listed: dict[str, list] = {}
        for packet in packets:
            try:
                data = json.loads(packet.get("data") or "{}")
            except ValueError:
                data = {}
            listed.setdefault(packet["session_id"], []).append((packet, data))
            chosen = data.get("note_ids") or data.get("standing_ids") or data.get("held_ids")
            if packet["mode"] == "lean" and not chosen:
                key = f"packet:{packet['id']}"
                if key not in hidden:
                    out.append({"key": key, "kind": "nothing", "at": packet["at"],
                                "session_id": packet["session_id"],
                                "request": packet["request"] or "", "entry": None,
                                "close": list(data.get("related_ids") or [])})
        seen = set()
        for row in opened:
            before = [(p, d) for p, d in listed.get(row["session_id"], []) if p["at"] <= row["at"]]
            brought = {i for _p, d in before for key in ("note_ids", "related_ids",
                                                          "standing_ids", "held_ids")
                       for i in (d.get(key) or [])}
            key = f"opened:{row['session_id']}:{row['item']}"
            if not before or row["item"] in brought or key in hidden or key in seen:
                continue
            seen.add(key)
            out.append({"key": key, "kind": "searched", "at": row["at"],
                        "session_id": row["session_id"], "request": before[-1][0]["request"]
                        or "", "entry": row["item"], "close": []})
        out.sort(key=lambda g: g["at"], reverse=True)
        return out[:int(limit)]

    def dismiss(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO dismissed (key, at) VALUES (?, ?)",
                         (str(key), util.now_iso()))

    def dismissed(self) -> set[str]:
        with self._connect() as conn:
            return {row["key"] for row in conn.execute("SELECT key FROM dismissed")}

    # ------------------------------------------------------------------ model calls
    def record_model_call(self, job: str, model: str, *, tokens_in: int = 0,
                          tokens_out: int = 0, cache_read: int = 0, cache_write: int = 0,
                          cost: float | None = None, ms: int | None = None, ref: str = "",
                          measured: bool = True) -> None:
        """One background call to a model: what it was for (`job`), which model, its tokens
        (`measured` when the model reported them, else estimated from the text) and what it
        cost (from the price table when the caller does not know)."""
        from . import costs
        now = util.now_iso()
        if cost is None:
            cost = costs.call_cost(model, tokens_in, tokens_out, cache_read, cache_write)
        row = (str(job or "other")[:60], str(model or "unknown")[:80], int(tokens_in or 0),
               int(tokens_out or 0), int(cache_read or 0), int(cache_write or 0),
               float(cost or 0.0))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO model_calls (at, job, model, tokens_in, tokens_out, cache_read, "
                "cache_write, cost, ms, ref, measured) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, *row, int(ms) if ms is not None else None, str(ref or "")[:120],
                 1 if measured else 0))
            conn.execute(
                "INSERT INTO model_daily (day, job, model, calls, tokens_in, tokens_out, "
                "cache_read, cache_write, cost) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?) "
                "ON CONFLICT(day, job, model) DO UPDATE SET calls = calls + 1, "
                "tokens_in = tokens_in + excluded.tokens_in, "
                "tokens_out = tokens_out + excluded.tokens_out, "
                "cache_read = cache_read + excluded.cache_read, "
                "cache_write = cache_write + excluded.cache_write, cost = cost + excluded.cost",
                (now[:10], *row))

    def model_usage(self, since_day: str) -> list[dict]:
        """Background model calls by day, job and model since a day (YYYY-MM-DD)."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM model_daily WHERE day >= ? ORDER BY day, job, model",
                (str(since_day)[:10],))]

    def packet_rows(self, since: str) -> list[dict]:
        """Every packet since an ISO moment, oldest first: its session, request, tokens and
        data (the request type, the notes it carried), for the cost and quality report."""
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT p.id, p.session_id, p.at, p.request, p.mode, p.tokens, p.data, "
                "s.label AS client FROM packets p LEFT JOIN sessions s ON s.id = p.session_id "
                "WHERE p.at >= ? ORDER BY p.at, p.rowid", (since,))]
            kernels = {}
            for d in conn.execute(
                    "SELECT packet_id, tokens FROM deliveries WHERE kind = 'kernel' AND at >= ?",
                    (since,)):
                kernels[d["packet_id"]] = kernels.get(d["packet_id"], 0) + int(d["tokens"] or 0)
        for row in rows:
            try:
                row["data"] = json.loads(row.get("data") or "{}")
            except ValueError:
                row["data"] = {}
            row["kernel_tokens"] = kernels.get(row["id"], 0)
        return rows

    def meta(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM ledger_meta WHERE key = ?",
                               (str(key),)).fetchone()
        return row["value"] if row is not None else None

    def set_meta(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO ledger_meta (key, value) VALUES (?, ?) ON CONFLICT(key) "
                         "DO UPDATE SET value = excluded.value", (str(key), str(value)))

    # ------------------------------------------------------------------ housekeeping
    def recent_sessions(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT s.id, s.principal, s.created, s.seen, "
                "(SELECT COUNT(*) FROM packets p WHERE p.session_id = s.id) AS packets "
                "FROM sessions s ORDER BY s.seen DESC LIMIT ?", (limit,))]

    def prune(self) -> None:
        """Drop the detail older than the retention window; daily counts stay."""
        if self._pruned:
            return
        self._pruned = True
        cutoff = (util.now() - _dt.timedelta(days=self.retention_days)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._connect() as conn:
            conn.execute("DELETE FROM deliveries WHERE at < ?", (cutoff,))
            conn.execute("DELETE FROM packets WHERE at < ?", (cutoff,))
            conn.execute("DELETE FROM brief_decisions WHERE at < ?", (cutoff,))
            conn.execute("DELETE FROM sessions WHERE seen < ?", (cutoff,))
            conn.execute("DELETE FROM model_calls WHERE at < ?", (cutoff,))
            conn.execute("DELETE FROM kernels WHERE at < ? AND fingerprint NOT IN "
                         "(SELECT item FROM deliveries WHERE kind = 'kernel')", (cutoff,))
