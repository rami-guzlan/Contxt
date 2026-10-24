"""The heartbeat: the one scheduled loop of Release 1 (the auto default, section 4).

Every few minutes (5, 15, 30 or 60; quiet hours respected) the governing CLI reads, read-only,
what changed in each connector since its cursor, then judges each new item in one model call:
which region of the Brain it belongs to, which project, and what it updates (a sheet cell, a
project's progress, a task, a note), each with its reason. Code checks every write before it
is made (in scope, not into a sealed project, not a private item, not over a must-hold) and
makes it through the Brain's one proposal path, with the item as its source: governance says
whether it goes in at once with an undo point or waits for the owner. Then the beat's record:
what it read and wrote, what waits, what it held back, and what it used.

A beat never sends, posts, replies or spends: it can only start the CLI with the read-only
tools Gnomon listed itself (connectors.py), and it calls no orchestrator.

Regions are the Brain's areas. Each keeps a headline (written by the same model call, only
when a line changed) and the lines the beats wrote, newest first. Undoing a line undoes its
write the way any undo does, and records that the next beat must not write it again.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso, parse_iso
from workspace_core.db import schema
from workspace_core.domain import states
from workspace_core.domain.policy import Principal
from workspace_core.domain.schedule import zone
from workspace_core.errors import Conflict, NotFound, ValidationFailed, WorkspaceError
from workspace_core.ids import new_id
from workspace_core.workspace import Workspace

from ..runners import RUNNERS, Runners, usage_of
from ..scout import Scout
from . import connectors as conn

log = logging.getLogger(__name__)
ACCOUNT_TTL = 1800.0  # seconds a listing of the Claude account's connectors is kept
ACCOUNT_PLACE = "Your Claude account"

CADENCES = (5, 15, 30, 60)
QUIET = {"off": "Off", "night": "7pm to 7am", "nights_weekends": "Nights and weekends"}
DEFAULTS: dict[str, Any] = {"cadence": 15, "quiet": "night", "paused": False, "cli": None}
CLI_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex CLI",
    "gemini": "Gemini CLI",
    "gnomon": "Gnomon",
}
HOW_LABELS = {"mcp": "MCP", "computer": "Computer use", "folder": "Folder"}
LOCK_MINUTES = 20  # a beat that holds the lock longer than this has stopped: its lock expires
BACKOFF_MINUTES = 30  # after a provider limit, scheduled beats wait this long
MAX_ITEMS = 25  # items read from one connector in one beat
FILE_WORDS = 4000  # characters of a Scout file the judge reads


def _file_words(ws: Any, path: str, name: str) -> str:
    """The words of a file Scout found, as Capture would read them, cut to FILE_WORDS: the judge
    decides from what the file says, not from its name."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(8_000_000)
    except OSError:
        return ""
    extractor = getattr(ws.rt, "extractor", None)
    text = extractor.extract(data, name, None) if extractor is not None else None
    if text is None:
        text = data.decode("utf-8", errors="replace")
    text = text.strip()
    return text if len(text) <= FILE_WORDS else text[:FILE_WORDS] + " [cut to fit]"


WRITE_KINDS = ("sheet", "progress", "task", "note")
LIMIT = re.compile(
    r"rate.?limit|usage limit|quota|\b429\b|too many requests|limit (?:reached|exceeded)|"
    r"overloaded|out of (?:credits|tokens)",
    re.I,
)
# What a Brain or a CLI that cannot answer now raises: the beat goes on without that part.
UNREADABLE = (WorkspaceError, OSError, ValueError, RuntimeError, KeyError, AttributeError)
SIGN_IN = re.compile(
    r"login no longer works|not signed in|sign in again|authenticat|unauthori[sz]ed|\b401\b",
    re.I,
)


def _hash(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _flat(text: Any, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def json_answer(text: str) -> Any:
    """The JSON object in a model's answer (fenced or not); ValueError when there is none."""
    body = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", body, re.S)
    if fenced:
        body = fenced.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the answer")
    return json.loads(body[start : end + 1])


def tokens_of(usage: dict[str, Any] | None) -> int | None:
    if not usage:
        return None
    return sum(
        int(usage.get(k) or 0) for k in ("tokens_in", "tokens_out", "cache_read", "cache_write")
    )


def classify(message: str) -> str:
    """The connector status a failed read means."""
    if LIMIT.search(message):
        return "provider_limit"
    if SIGN_IN.search(message):
        return "unhealthy_sign_in"
    return "error"


class Heartbeat:
    def __init__(self, ws: Workspace, runners: Runners) -> None:
        self.ws = ws
        self.runners = runners
        self._running: dict[str, Any] | None = None  # the beat under way: what it reads now
        self._guard = threading.Lock()
        # Gnomon itself lists a server's tools (tests stand in a fake server's listing here).
        self.list_tools = conn.list_tools
        self.discover = conn.discover
        self.find = conn.find
        self._accounts: tuple[float, list[conn.Found]] | None = None

    def _account(self, who: Principal, *, fresh: bool = False) -> list[conn.Found] | None:
        """The Claude account's connectors (claude.ai), as Claude Code lists them when it
        starts; kept for ACCOUNT_TTL so a beat does not start Claude Code once per connector.
        None when Claude Code could not say (signed out, not here): nothing is changed then."""
        now = time.monotonic()
        if not fresh and self._accounts and now - self._accounts[0] < ACCOUNT_TTL:
            return self._accounts[1]
        try:
            listed = conn.from_account(self.runners.account_servers(who))
        except (WorkspaceError, OSError) as exc:
            log.info("the Claude account's connectors could not be listed: %s", exc)
            return self._accounts[1] if self._accounts else None
        self._accounts = (now, listed)
        return listed

    def _find(self, who: Principal, row: dict[str, Any]) -> conn.Found | None:
        if row.get("found_in") == ACCOUNT_PLACE:
            return next((f for f in self._account(who) or [] if f.id == row["id"]), None)
        return self.find(row["id"])

    # ---------------------------------------------------------------- settings

    def settings(self) -> dict[str, Any]:
        with self.ws.rt.read() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
        found = dict((row["settings"] or {}).get("heartbeat") or {})
        return {**DEFAULTS, **found, "timezone": row["timezone"] or "UTC"}

    def _save(
        self, who: Principal, changes: dict[str, Any], event: str, data: dict[str, Any]
    ) -> None:
        with self.ws.rt.write() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
            settings = dict(row["settings"] or {})
            settings["heartbeat"] = {**dict(settings.get("heartbeat") or {}), **changes}
            tx.update(schema.workspaces, row, {"settings": settings})
            tx.emit(
                event,
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=row["id"],
                data=data,
            )

    def cli(self, settings: dict[str, Any] | None = None) -> str:
        """The governing CLI: the one chosen for the heartbeat, else the knowledge agent's, else
        Claude Code. A beat never switches it."""
        chosen = (settings or self.settings()).get("cli")
        if chosen in RUNNERS:
            return str(chosen)
        try:
            model = self.ws.agent.chosen_model() or ""
        except UNREADABLE:  # no Brain: the default
            model = ""
        named = model.partition(":")[0]
        return named if named in RUNNERS else "claude"

    def in_quiet_hours(self, settings: dict[str, Any], moment: datetime | None = None) -> bool:
        quiet = settings.get("quiet") or "off"
        if quiet == "off":
            return False
        local = (moment or self.ws.rt.clock.now()).astimezone(zone(settings["timezone"]))
        night = local.hour >= 19 or local.hour < 7
        if quiet == "nights_weekends":
            return night or local.weekday() >= 5
        return night

    def configure(
        self,
        who: Principal,
        *,
        cadence: int | None = None,
        quiet: str | None = None,
        paused: bool | None = None,
        cli: str | None = None,
        connectors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        who.require("workspace.admin")
        changes: dict[str, Any] = {}
        if cadence is not None:
            if int(cadence) not in CADENCES:
                raise ValidationFailed(
                    f"Cadence is one of {', '.join(map(str, CADENCES))} minutes.", field="cadence"
                )
            changes["cadence"] = int(cadence)
        if quiet is not None:
            if quiet not in QUIET:
                raise ValidationFailed(
                    f"Quiet hours are one of {', '.join(QUIET)}.", field="quiet_hours"
                )
            changes["quiet"] = quiet
        if paused is not None:
            changes["paused"] = bool(paused)
            if not paused:
                changes["backoff"] = None  # resuming tries again at once
        if cli is not None:
            if cli not in RUNNERS:
                raise ValidationFailed(f"The CLI is one of {', '.join(RUNNERS)}.", field="cli")
            changes["cli"] = cli
        if changes:
            self._save(who, changes, "heartbeat.configured", {k: v for k, v in changes.items()})
        for item in connectors or []:
            self.set_connector(
                who,
                str(item.get("id") or ""),
                enabled=item.get("enabled"),
                feeds=item.get("feeds"),
                cadence_minutes=item.get("cadence_minutes"),
            )
        return self.status(who)

    # ---------------------------------------------------------------- connectors

    def _connectors(self) -> list[dict[str, Any]]:
        with self.ws.rt.read() as tx:
            return tx.rows(
                sa.select(schema.heartbeat_connectors)
                .where(schema.heartbeat_connectors.c.workspace_id == self.ws.rt.workspace_id)
                .order_by(schema.heartbeat_connectors.c.cli, schema.heartbeat_connectors.c.name)
            )

    def _connector_view(self, row: dict[str, Any]) -> dict[str, Any]:
        own = row["cadence_minutes"]
        how = HOW_LABELS.get(row["how"], row["how"])
        return {
            "id": row["id"],
            "name": row["name"],
            "cli": row["cli"],
            "cli_label": CLI_LABELS.get(row["cli"], row["cli"]),
            "how": row["how"],
            "how_label": how + (f", every {own} min" if own else ""),
            "cadence_minutes": own,
            "feeds": list(row["feeds"] or []),
            "enabled": bool(row["enabled"]),
            "last_read_at": row["last_read_at"],
            "last_items": int(row["last_items"] or 0),
            "status": row["status"],
            "status_line": row["status_line"],
            "tools": list(row["tools"] or []),
            "found_in": row["found_in"],
            "present": bool(row["present"]),
        }

    def connectors(self, who: Principal) -> list[dict[str, Any]]:
        who.require("brain.read")
        return [self._connector_view(r) for r in self._connectors()]

    def _check(self, found: conn.Found) -> tuple[str, str, list[str], list[str]]:
        """(status, status line, read-only tools, other tools) of one MCP server, as Gnomon
        lists its tools itself."""
        if found.how == "computer":
            label = CLI_LABELS.get(found.cli, found.cli)
            return (
                "off",
                f"Reads through {label}'s computer use, which the heartbeat does not use yet.",
                [],
                [],
            )
        if found.spec.get("account"):
            # Listed by Claude Code from the account: names only, no annotations.
            said = found.spec.get("status")
            if said == "needs-auth":
                return (
                    "unhealthy_sign_in",
                    "It needs signing in again in Claude (claude.ai, Settings, Connectors). "
                    "It is not read until then.",
                    [],
                    [],
                )
            tools = [{"name": n} for n in found.spec.get("tools") or [] if isinstance(n, str)]
            if said != "connected" or not tools:
                return (
                    "error",
                    "Claude Code could not reach it just now. The next look tries again.",
                    [],
                    [],
                )
        else:
            try:
                tools = self.list_tools(found)
            except conn.ListingFailed as exc:
                return (
                    "cannot_confirm_read_only",
                    f"Its tools could not be listed ({exc}), so it cannot be confirmed "
                    "read-only. It is not read.",
                    [],
                    [],
                )
        allowed, refused = conn.keep_read_only(tools, found.name)
        if not allowed:
            return (
                "cannot_confirm_read_only",
                f"None of its {len(tools)} tools only reads, so it is not read.",
                [],
                refused,
            )
        return (
            "ok",
            f"Read-only: {len(allowed)} of {len(tools)} tools"
            + (f" ({len(refused)} that could change something are refused)" if refused else "")
            + ".",
            allowed,
            refused,
        )

    def rescan(self, who: Principal) -> dict[str, Any]:
        """Find connectors in my CLIs: read each CLI's settings again and list each server's
        tools. New connectors that only read start on; the owner's on/off choices stay."""
        who.require("workspace.admin")
        account = self._account(who, fresh=True)
        found = [*self.discover(), *(account or [])]
        checked = {f.id: (f, self._check(f)) for f in found}
        scout = Scout(self.ws).overview(who)
        has_folders = bool(scout.get("folders"))
        now = iso(self.ws.rt.clock.now())
        added: list[str] = []
        with self.ws.rt.write() as tx:
            rows = {
                r["id"]: r
                for r in tx.rows(
                    sa.select(schema.heartbeat_connectors).where(
                        schema.heartbeat_connectors.c.workspace_id == tx.workspace_id
                    )
                )
            }
            for cid, (f, (status, line, allowed, _refused)) in checked.items():
                row = rows.get(cid)
                values = {
                    "name": f.name,
                    "cli": f.cli,
                    "how": f.how,
                    "tools": allowed,
                    "found_in": f.found_in,
                    "present": True,
                }
                if row is None:
                    # One of the account's connectors reads the person's own account (their
                    # mail, their CRM): it starts off until they turn it on.
                    mine = bool(f.spec.get("account"))
                    on = status == "ok" and not mine
                    if mine and status == "ok":
                        line += " Off until you turn it on: it reads your own account."
                    tx.insert(
                        schema.heartbeat_connectors,
                        {
                            "id": cid,
                            "workspace_id": tx.workspace_id,
                            **values,
                            "cadence_minutes": 60 if f.how == "computer" else None,
                            "feeds": [],
                            "enabled": on,
                            "status": status if status != "ok" or on else "off",
                            "status_line": line,
                            "last_items": 0,
                            "created_by": who.actor_id,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    added.append(cid)
                else:
                    keep = status if status != "ok" else ("ok" if row["enabled"] else "off")
                    tx.update(
                        schema.heartbeat_connectors,
                        row,
                        {**values, "status": keep, "status_line": line},
                    )
            for cid, row in rows.items():
                if account is None and row["found_in"] == ACCOUNT_PLACE:
                    continue  # Claude Code could not say: leave the account's connectors be
                if cid != "scout" and cid not in checked and row["present"]:
                    tx.update(
                        schema.heartbeat_connectors,
                        row,
                        {
                            "present": False,
                            "status": "off",
                            "status_line": "No longer in the CLI's settings.",
                        },
                    )
            scout_line = (
                f"Reads the {len(scout['folders'])} Scout folder(s) by content."
                if has_folders
                else "Choose a folder for Scout first."
            )
            if "scout" not in rows:
                tx.insert(
                    schema.heartbeat_connectors,
                    {
                        "id": "scout",
                        "workspace_id": tx.workspace_id,
                        "name": "Scout folders",
                        "cli": "gnomon",
                        "how": "folder",
                        "tools": [],
                        "found_in": "Gnomon",
                        "present": True,
                        "cadence_minutes": None,
                        "feeds": [],
                        "enabled": has_folders,
                        "status": "ok" if has_folders else "off",
                        "status_line": scout_line,
                        "last_items": 0,
                        "created_by": who.actor_id,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                added.append("scout")
            else:
                tx.update(
                    schema.heartbeat_connectors,
                    rows["scout"],
                    {
                        "status_line": scout_line,
                        "status": (
                            rows["scout"]["status"]
                            if has_folders and rows["scout"]["enabled"]
                            else "off"
                        ),
                    },
                )
            tx.emit(
                "heartbeat.connectors_found",
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=tx.workspace_id,
                data={"found": len(checked), "added": added},
            )
        listed = self.connectors(who)
        by_cli: dict[str, int] = {}
        for c in listed:
            if c["present"]:
                by_cli[c["cli_label"]] = by_cli.get(c["cli_label"], 0) + 1
        said = ", ".join(f"{n} in {label}" for label, n in by_cli.items()) or "none"
        return {
            "found": len([c for c in listed if c["present"]]),
            "added": added,
            "line": f"Found {len([c for c in listed if c['present']])} connectors: {said}."
            + (f" {len(added)} new." if added else " Nothing new to add."),
            "connectors": listed,
        }

    def set_connector(
        self,
        who: Principal,
        connector_id: str,
        *,
        enabled: bool | None = None,
        feeds: list[str] | None = None,
        cadence_minutes: int | None = None,
    ) -> dict[str, Any]:
        who.require("workspace.admin")
        with self.ws.rt.write() as tx:
            row = tx.get(schema.heartbeat_connectors, connector_id)
            if row is None or row["workspace_id"] != tx.workspace_id:
                raise NotFound(f"No connector {connector_id}.", id=connector_id)
            values: dict[str, Any] = {}
            if enabled is not None:
                if enabled and row["status"] == "cannot_confirm_read_only":
                    raise Conflict(
                        f"{row['name']} cannot be confirmed read-only, so it stays off: "
                        "find connectors again once its tools can be listed."
                    )
                if enabled and row["how"] == "computer":
                    raise Conflict(
                        f"{row['name']} reads through computer use, which the heartbeat does "
                        "not use yet."
                    )
                values["enabled"] = bool(enabled)
                values["status"] = "ok" if enabled else "off"
                if not enabled:
                    values["status_line"] = "Off. The heartbeat does not read it."
            if feeds is not None:
                values["feeds"] = [str(f) for f in feeds][:20]
            if cadence_minutes is not None:
                own = int(cadence_minutes)
                if own and own not in CADENCES:
                    raise ValidationFailed(
                        f"A connector's own cadence is one of {', '.join(map(str, CADENCES))}.",
                        field="cadence_minutes",
                    )
                values["cadence_minutes"] = own or None
            if values:
                row = tx.update(schema.heartbeat_connectors, row, values)
                tx.emit(
                    "heartbeat.connector_changed",
                    actor_id=who.actor_id,
                    subject_type="heartbeat_connector",
                    subject_id=connector_id,
                    data={k: v for k, v in values.items() if k != "status_line"},
                )
        return self._connector_view(row)

    # ---------------------------------------------------------------- status

    def _beats(self, *, since: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        table = schema.heartbeat_beats
        query = sa.select(table).where(table.c.workspace_id == self.ws.rt.workspace_id)
        if since:
            query = query.where(table.c.started_at >= since)
        with self.ws.rt.read() as tx:
            return tx.rows(
                query.order_by(table.c.started_at.desc(), table.c.id.desc()).limit(limit)
            )

    @staticmethod
    def beat_view(row: dict[str, Any]) -> dict[str, Any]:
        changes = int(row["changes"] or 0)
        nothing = row["status"] == "done" and not (
            changes or row["waits"] or row["held"] or row["items"]
        )
        return {
            "id": row["id"],
            "status": row["status"],
            "trigger": row["trigger"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "connectors": list(row["connectors"] or []),
            "connectors_read": len([c for c in row["connectors"] or [] if c.get("read")]),
            "items": int(row["items"] or 0),
            "changes": changes,
            "waits": int(row["waits"] or 0),
            "held": int(row["held"] or 0),
            "tokens": row["tokens"],
            "tokens_known": row["tokens"] is not None and not row["tokens_unknown"],
            "tokens_unknown": int(row["tokens_unknown"] or 0),
            "duration_ms": row["duration_ms"],
            "errors": list(row["errors"] or []),
            "details": list(row["details"] or []),
            "nothing_new": nothing,
        }

    def beats(
        self, who: Principal, *, since: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        who.require("brain.read")
        return [self.beat_view(r) for r in self._beats(since=since, limit=max(1, min(limit, 100)))]

    def next_beat_at(self, settings: dict[str, Any], last: dict[str, Any] | None) -> str | None:
        if settings.get("paused"):
            return None
        now = self.ws.rt.clock.now()
        due = (
            parse_iso(last["started_at"]) + timedelta(minutes=int(settings["cadence"]))
            if last
            else now
        )
        backoff = settings.get("backoff") or {}
        if backoff.get("until"):
            due = max(due, parse_iso(backoff["until"]))
        due = max(due, now)
        for _ in range(24 * 4 * 3):  # past quiet hours, a quarter hour at a time
            if not self.in_quiet_hours(settings, due):
                break
            due = due + timedelta(minutes=15)
        return iso(due)

    def status(self, who: Principal) -> dict[str, Any]:
        """Cadence, quiet hours, the last and next beat, paused or not, why a beat would not
        run now, and the connectors."""
        who.require("brain.read")
        settings = self.settings()
        rows = self._beats(limit=1)
        last = self.beat_view(rows[0]) if rows else None
        listed = [self._connector_view(r) for r in self._connectors()]
        cli = self.cli(settings)
        label = CLI_LABELS.get(cli, cli)
        signed_in: bool | None = None
        detail = ""
        try:
            found = self.runners.status(RUNNERS[cli])
            signed_in = False if not found.installed else found.signed_in
            detail = found.detail
        except UNREADABLE:  # cannot tell now
            signed_in = None
        backoff = settings.get("backoff") or {}
        now = iso(self.ws.rt.clock.now())
        backing = backoff if backoff.get("until") and backoff["until"] > now else {}
        quiet = self.in_quiet_hours(settings)
        if settings.get("paused"):
            state, line = "paused", "Paused. Nothing is read or changed until you resume."
        elif signed_in is False:
            state = "unhealthy_sign_in"
            line = f"{label} is not signed in, so the heartbeat waits. {detail}".strip()
        elif backing:
            state, line = str(backing.get("reason")), str(backing.get("line"))
        elif not any(c["enabled"] for c in listed):
            state = "no_connectors"
            line = (
                "No connector is on. Find connectors in your CLIs in Settings, Approval."
                if listed
                else "No connectors yet. Find connectors in your CLIs in Settings, Approval."
            )
        elif quiet:
            state = "quiet"
            line = f"Quiet hours ({QUIET[settings['quiet']]}). The next beat waits until they end."
        else:
            state, line = "ready", "Ready."
        running = dict(self._running) if self._running else None
        return {
            "state": state,
            "line": line,
            "cadence": int(settings["cadence"]),
            "cadences": list(CADENCES),
            "quiet_hours": settings["quiet"],
            "quiet_options": [{"id": k, "label": v} for k, v in QUIET.items()],
            "in_quiet_hours": quiet,
            "paused": bool(settings.get("paused")),
            "cli": cli,
            "cli_label": label,
            "signed_in": signed_in,
            "backoff": backing or None,
            "last_beat": last,
            "next_beat_at": self.next_beat_at(settings, rows[0] if rows else None),
            "running": running,
            "connectors": listed,
            "cost": self.cost(),
        }

    def cost(self) -> dict[str, Any]:
        """What a beat uses, from the beats' own records: with changes and with none."""
        rows = [r for r in self._beats(limit=50) if r["status"] == "done"]
        changed = [r["tokens"] for r in rows if r["changes"] and r["tokens"] is not None]
        nothing = [r["tokens"] for r in rows if not r["changes"] and r["tokens"] is not None]

        def average(values: list[int]) -> int | None:
            return round(sum(values) / len(values)) if values else None

        return {
            "with_changes": average(changed),
            "nothing_new": average(nothing),
            "beats": len(rows),
            "unknown": len([r for r in rows if r["tokens"] is None]),
        }

    # ---------------------------------------------------------------- the beat

    def due(self) -> bool:
        """Whether the worker should beat now (a scheduled beat)."""
        settings = self.settings()
        if settings.get("paused") or self.in_quiet_hours(settings):
            return False
        rows = self._beats(limit=1)
        at = self.next_beat_at(settings, rows[0] if rows else None)
        return at is not None and at <= iso(self.ws.rt.clock.now())

    def _skip(self, reason: str, line: str) -> dict[str, Any]:
        return {"skipped": reason, "line": line}

    def start(self, who: Principal, trigger: str = "now") -> dict[str, Any]:
        """Take the lock and open the beat's record; a skip says why there is no beat."""
        who.require("brain.propose")
        settings = self.settings()
        if settings.get("paused"):
            return self._skip("paused", "The heartbeat is paused. Resume it first.")
        if trigger == "schedule" and self.in_quiet_hours(settings):
            return self._skip("quiet", "Quiet hours: no beat until they end.")
        now = self.ws.rt.clock.now()
        backoff = settings.get("backoff") or {}
        if trigger == "schedule" and backoff.get("until") and backoff["until"] > iso(now):
            return self._skip(str(backoff.get("reason")), str(backoff.get("line")))
        cli = self.cli(settings)
        try:
            found = self.runners.status(RUNNERS[cli])
        except UNREADABLE:  # the Brain or the CLI cannot say now
            found = None
        if found is not None and (not found.installed or found.signed_in is False):
            label = CLI_LABELS.get(cli, cli)
            line = (
                f"{label} is not installed on this computer, so the heartbeat waits."
                if not found.installed
                else f"{label} is not signed in, so the heartbeat waits. Sign in: {found.sign_in}"
            )
            return self._skip("unhealthy_sign_in", line)
        beat_id = new_id("beat", now)
        with self.ws.rt.write() as tx:
            lock = tx.get(schema.heartbeat_locks, tx.workspace_id)
            if lock is not None and lock["expires_at"] > tx.now:
                return self._skip("busy", "Another beat is running. It finishes first.")
            until = iso(now + timedelta(minutes=LOCK_MINUTES))
            if lock is None:
                tx.insert(
                    schema.heartbeat_locks,
                    {"id": tx.workspace_id, "beat_id": beat_id, "expires_at": until},
                )
            else:  # a stale lock: the beat that held it stopped
                tx.conn.execute(
                    schema.heartbeat_locks.update()
                    .where(schema.heartbeat_locks.c.id == tx.workspace_id)
                    .values(beat_id=beat_id, expires_at=until)
                )
            tx.insert(
                schema.heartbeat_beats,
                {
                    "id": beat_id,
                    "workspace_id": tx.workspace_id,
                    "status": states.BEAT.initial,
                    "trigger": trigger,
                    "started_at": tx.now,
                    "connectors": [],
                    "errors": [],
                    "details": [],
                    "created_by": who.actor_id,
                    "created_at": tx.now,
                    "updated_at": tx.now,
                },
            )
            tx.emit(
                "heartbeat.beat_started",
                actor_id=who.actor_id,
                subject_type="heartbeat_beat",
                subject_id=beat_id,
                data={"trigger": trigger},
            )
        self._running = {"beat_id": beat_id, "reading": None, "read": []}
        return {"beat_id": beat_id}

    def beat(self, who: Principal, trigger: str = "now", *, wait: bool = True) -> dict[str, Any]:
        """One beat: read what changed, judge it, write it through governance, record it.
        `wait` False starts it in the background and returns its id."""
        opened = self.start(who, trigger)
        if "skipped" in opened:
            return opened
        beat_id = opened["beat_id"]
        if not wait:
            threading.Thread(
                target=self._run_safely, args=(beat_id,), name="heartbeat", daemon=True
            ).start()
            return {"beat_id": beat_id, "status": "running"}
        self._run_safely(beat_id)
        return self.get_beat(who, beat_id)

    def get_beat(self, who: Principal, beat_id: str) -> dict[str, Any]:
        who.require("brain.read")
        with self.ws.rt.read() as tx:
            row = tx.get(schema.heartbeat_beats, beat_id)
        if row is None or row["workspace_id"] != self.ws.rt.workspace_id:
            raise NotFound(f"No beat {beat_id}.", id=beat_id)
        return self.beat_view(row)

    def _run_safely(self, beat_id: str) -> None:
        started = time.monotonic()
        try:
            self._run(beat_id, started)
        except Exception as exc:  # the beat's record says what stopped it
            log.warning("beat %s failed", beat_id, exc_info=True)
            self._finish(beat_id, started, status="failed", errors=[_flat(str(exc), 300)])
        finally:
            with self.ws.rt.write() as tx:
                tx.conn.execute(
                    schema.heartbeat_locks.delete().where(
                        schema.heartbeat_locks.c.id == tx.workspace_id,
                        schema.heartbeat_locks.c.beat_id == beat_id,
                    )
                )
            self._running = None

    def _due_connectors(self, trigger: str, cadence: int) -> list[dict[str, Any]]:
        now = self.ws.rt.clock.now()
        out = []
        for row in self._connectors():
            if not row["enabled"] or not row["present"] or row["how"] == "computer":
                continue
            if row["status"] == "cannot_confirm_read_only":
                continue
            own = int(row["cadence_minutes"] or 0)
            needed = max(own, cadence) if trigger == "schedule" else own
            if row["last_read_at"] and needed:
                elapsed = (now - parse_iso(row["last_read_at"])).total_seconds() / 60
                if elapsed < needed - 0.5:
                    continue
            out.append(row)
        return out

    def _read(self, owner: Principal, row: dict[str, Any]) -> dict[str, Any]:
        """What changed in one connector since its cursor: {items, cursor, usage}."""
        if row["how"] == "folder":
            return self._read_scout(owner, row)
        found = self._find(owner, row)
        if found is None:
            raise ConnectorProblem("off", "No longer in the CLI's settings.", present=False)
        status, line, allowed, refused = self._check(found)
        if status != "ok":
            raise ConnectorProblem(status, line, tools=allowed)
        server = conn.safe_server(found.name)
        since = row["cursor"] or "the last 24 hours"
        prompt = (
            f"Read, read-only, what changed in {found.name} since {since}. Use only these "
            f"tools: {', '.join(allowed)}. Never send, post, reply, create, change, delete or "
            "pay for anything; you have no tool that can. Reply with one JSON object only: "
            '{"cursor": "<the newest time or marker you saw>", "items": [{"id": "<the '
            'item\'s own id>", "title": "...", "text": "<what it says or what changed, at most '
            '600 characters>", "at": "<ISO 8601 time>", "url": "", "speaker": "<who wrote it, '
            'or empty>", "private": false}]}. Mark private true for anything marked private '
            f"or confidential. At most {MAX_ITEMS} items, newest first; none: an empty list."
        )
        got = self.runners.read_through(
            owner,
            found.cli,
            server=server,
            spec=found.spec,
            allowed=allowed,
            refused=refused,
            prompt=prompt,
        )
        try:
            answer = json_answer(got.get("text") or "")
        except ValueError as exc:
            raise ConnectorProblem("error", "Its answer could not be read.") from exc
        items = []
        for raw in (answer.get("items") or [])[:MAX_ITEMS]:
            if not isinstance(raw, dict) or not str(raw.get("id") or "").strip():
                continue
            items.append(
                {
                    "id": _flat(raw.get("id"), 300),
                    "title": _flat(raw.get("title"), 200),
                    "text": _flat(raw.get("text"), 600),
                    "at": _flat(raw.get("at"), 32),
                    "url": _flat(raw.get("url"), 300),
                    "speaker": _flat(raw.get("speaker"), 80),
                    "private": raw.get("private") is True,
                }
            )
        cursor = _flat(answer.get("cursor"), 200) or row["cursor"]
        return {"items": items, "cursor": cursor, "usage": got.get("usage"), "tools": allowed}

    def _read_scout(self, owner: Principal, row: dict[str, Any]) -> dict[str, Any]:
        try:
            found = Scout(self.ws).scan(owner)
        except ValidationFailed as exc:
            raise ConnectorProblem("off", str(exc)) from exc
        items = []
        for diff in found.get("found") or []:
            if diff.get("quiet"):
                continue
            name = str(diff["path"]).replace("\\", "/").rsplit("/", 1)[-1]
            words = _file_words(self.ws, str(diff["path"]), name)
            items.append(
                {
                    "id": str(diff["path"])[:300],
                    "title": name,
                    "text": f"{'A new file' if diff['kind'] == 'new' else 'A new version of'} "
                    f"{name} in a Scout folder."
                    + (f" It says:\n{words}" if words else " Its words could not be read."),
                    "at": found.get("last_inspection") or "",
                    "url": "",
                    "speaker": "",
                    "private": False,
                    "digest": _hash(diff["path"], diff.get("size"), found.get("last_inspection")),
                }
            )
        return {"items": items[:MAX_ITEMS], "cursor": found.get("last_inspection"), "usage": None}

    def _seen(self, connector_id: str, keys: list[tuple[str, str]]) -> set[tuple[str, str]]:
        if not keys:
            return set()
        table = schema.heartbeat_seen
        with self.ws.rt.read() as tx:
            rows = tx.rows(
                sa.select(table.c.item_id, table.c.digest).where(
                    table.c.connector_id == connector_id,
                    table.c.item_id.in_([k for k, _ in keys]),
                )
            )
        return {(r["item_id"], r["digest"]) for r in rows}

    def _brain(self) -> dict[str, Any]:
        """What the judge is shown: the regions (the Brain's areas), its projects, its sheets
        and its must-holds."""
        brain = self.ws.rt.brain
        try:
            areas = [{"id": a.key, "name": a.label} for a in brain.catalog().areas]
        except UNREADABLE:  # the Brain or the CLI cannot say now
            areas = []
        try:
            projects = [
                {
                    "id": p.id,
                    "title": p.title,
                    "status": p.status,
                    "now": p.current,
                    "area": (p.topic or "").partition("/")[0],
                }
                for p in brain.projects()
            ]
        except UNREADABLE:  # the Brain or the CLI cannot say now
            projects = []
        try:
            sheets = [
                {
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "key": s.get("key"),
                    "columns": [c.get("name") for c in s.get("columns") or []],
                }
                for s in brain.get_state().get("sheets") or []
            ]
        except UNREADABLE:  # the Brain or the CLI cannot say now
            sheets = []
        try:
            holds = [
                {"id": n["id"], "text": n.get("text") or n.get("title")}
                for group in brain.ladder().get("must_holds") or []
                for n in group.get("notes") or []
            ]
        except UNREADABLE:  # the Brain or the CLI cannot say now
            holds = []
        return {"regions": areas, "projects": projects, "sheets": sheets, "must_holds": holds}

    def _regions_now(self) -> dict[str, dict[str, Any]]:
        with self.ws.rt.read() as tx:
            rows = tx.rows(
                sa.select(schema.heartbeat_regions).where(
                    schema.heartbeat_regions.c.workspace_id == tx.workspace_id
                )
            )
        return {r["id"]: r for r in rows}

    def _ask(self, owner: Principal, cli: str, prompt: str) -> tuple[str, int | None]:
        """One answer from the governing CLI and the tokens it said it used (None: unknown)."""
        if cli == "claude":
            found = self.runners.ask_json(owner, prompt, timeout=300)
            usage = usage_of(found)
            if usage is not None:
                self.runners.count_usage("heartbeat", usage)
            return str(found.get("result") or ""), tokens_of(usage)
        # Codex and Gemini CLI do not say what one answer used in this mode.
        return self.runners.ask(owner, prompt, runner=cli, job="heartbeat", timeout=300), None

    def judge_prompt(
        self, items: list[dict[str, Any]], brain: dict[str, Any], regions: dict[str, Any]
    ) -> str:
        shown = {
            "regions": [
                {**r, "headline": (regions.get(r["id"]) or {}).get("headline") or ""}
                for r in brain["regions"]
            ],
            "projects": brain["projects"],
            "sheets": brain["sheets"],
            "must_holds": brain["must_holds"],
            "items": [
                {
                    "item": i["key"],
                    "connector": i["connector_name"],
                    "feeds": i["feeds"],
                    "title": i["title"],
                    "text": i["text"],
                    "at": i["at"],
                    "speaker": i["speaker"],
                }
                for i in items
            ],
        }
        return (
            "You keep a person's Brain current. Below, as JSON: the Brain's regions, projects, "
            "context sheets and must-holds, and items that changed in their connected tools. "
            "For each item say which region it belongs to (one of the region ids; a connector's "
            "feeds are a hint), which project (an id, or null), one plain line saying what "
            "changed, and what it updates: none, or writes of these kinds, each with its "
            'reason: {"kind": "sheet", "sheet": id, "row": key, "column": name, "value": '
            'text}, {"kind": "progress", "project": id, "text": what moved, "next_up": text}, '
            '{"kind": "task", "project": id, "text": the task, "due": "YYYY-MM-DD" or "", '
            '"owner": ""}, {"kind": "note", "area": region id, "topic": a short '
            'lowercase-hyphenated name, "text": the fact, "revises": an entry id or null}. '
            "Prefer one write per item: the one place it belongs. "
            'Add "customer_facing": true to a write a customer would see, and "spends": true '
            "to one about spending money. Write only what the item says; never invent. "
            "If a must-hold protects what an item says (it would quote or change it), name it "
            'in "protected_by". Then a new headline (one short sentence) for each region that '
            "got a line, and a status line for each project that moved. Reply with one JSON "
            'object only: {"items": [{"item": key, "region": id, "project": id or null, '
            '"line": text, "protected_by": id or null, "writes": [...]}], "headlines": '
            '{region id: text}, "projects": {project id: text}}.\n\n'
            + json.dumps(shown, ensure_ascii=False)
        )

    def _run(self, beat_id: str, started: float) -> None:
        owner = self.ws.owner()
        settings = self.settings()
        cli = self.cli(settings)
        due = self._due_connectors(self._trigger(beat_id), int(settings["cadence"]))
        read_log: list[dict[str, Any]] = []
        errors: list[str] = []
        details: list[str] = []
        tokens: int | None = None
        unknown = 0
        fresh: list[dict[str, Any]] = []
        reads: dict[str, dict[str, Any]] = {}
        limited: str | None = None
        for row in due:
            if self._running is not None:
                self._running["reading"] = row["id"]
            entry: dict[str, Any] = {"id": row["id"], "name": row["name"], "read": False}
            try:
                got = self._read(owner, row)
            except ConnectorProblem as problem:
                self._connector_problem(owner, row, problem)
                entry["status"] = problem.status
                if problem.status != "off":
                    errors.append(f"{row['name']}: {problem.line}")
                read_log.append(entry)
                continue
            except WorkspaceError as exc:
                status = classify(str(exc))
                if status == "provider_limit":
                    limited = str(exc)
                self._connector_problem(owner, row, ConnectorProblem(status, _flat(str(exc), 300)))
                entry["status"] = status
                errors.append(f"{row['name']}: {_flat(str(exc), 200)}")
                read_log.append(entry)
                continue
            if self._running is not None:
                self._running["read"].append(row["id"])
            spent = tokens_of(got.get("usage"))
            if row["how"] != "folder":
                if spent is None:
                    unknown += 1
                else:
                    tokens = (tokens or 0) + spent
            keys = [
                (i["id"], i.get("digest") or _hash(i["title"], i["text"], i["at"]))
                for i in got["items"]
            ]
            seen = self._seen(row["id"], keys)
            new = []
            for item, key in zip(got["items"], keys, strict=True):
                if key in seen:
                    continue
                new.append(
                    {
                        **item,
                        "digest": key[1],
                        "key": f"connector:{row['id']}:{item['id']}",
                        "connector_id": row["id"],
                        "connector_name": row["name"],
                        "cli": row["cli"],
                        "feeds": list(row["feeds"] or []),
                    }
                )
            entry.update(read=True, status="ok", items=len(got["items"]), new=len(new))
            read_log.append(entry)
            reads[row["id"]] = {"row": row, "got": got, "new": new}
            fresh.extend(new)
        if self._running is not None:
            self._running["reading"] = None
        if limited:
            self._back_off(
                owner, "provider_limit", f"A provider limit was hit: {_flat(limited, 160)}"
            )
        counts = {"changes": 0, "waits": 0, "held": 0}
        if fresh:
            brain = self._brain()
            regions_before = self._regions_now()
            try:
                answer, spent = self._ask(
                    owner, cli, self.judge_prompt(fresh, brain, regions_before)
                )
            except WorkspaceError as exc:
                status = classify(str(exc))
                if status == "provider_limit":
                    self._back_off(
                        owner, "provider_limit", f"A provider limit was hit: {_flat(str(exc), 160)}"
                    )
                elif status == "unhealthy_sign_in":
                    self._back_off(owner, "unhealthy_sign_in", _flat(str(exc), 200))
                raise
            if spent is None:
                unknown += 1
            else:
                tokens = (tokens or 0) + spent
            try:
                judged = json_answer(answer)
            except ValueError as exc:
                raise Conflict(
                    "The judge's answer could not be read; nothing was written."
                ) from exc
            counts = self._write_all(owner, beat_id, fresh, judged, brain, details)
        else:
            details.append(
                f"Read {len([e for e in read_log if e['read']])} connectors. Nothing new."
                if read_log
                else "No connector was due."
            )
        # Only now are the items seen and the cursors moved: a beat that stopped before this
        # point reads the same items again next time.
        self._advance(beat_id, reads)
        self._finish(
            beat_id,
            started,
            status="done",
            connectors=read_log,
            items=len(fresh),
            tokens=tokens,
            unknown=unknown,
            errors=errors,
            details=details,
            **counts,
        )

    def _trigger(self, beat_id: str) -> str:
        with self.ws.rt.read() as tx:
            row = tx.one(schema.heartbeat_beats, beat_id, "beat")
        return str(row["trigger"])

    def _connector_problem(
        self, owner: Principal, row: dict[str, Any], problem: ConnectorProblem
    ) -> None:
        with self.ws.rt.write() as tx:
            current = tx.one(schema.heartbeat_connectors, row["id"], "connector")
            values: dict[str, Any] = {"status": problem.status, "status_line": problem.line}
            if problem.present is not None:
                values["present"] = problem.present
            if problem.tools is not None:
                values["tools"] = problem.tools
            tx.update(schema.heartbeat_connectors, current, values)

    def _back_off(self, owner: Principal, reason: str, line: str) -> None:
        until = iso(self.ws.rt.clock.now() + timedelta(minutes=BACKOFF_MINUTES))
        self._save(
            owner,
            {
                "backoff": {
                    "reason": reason,
                    "line": line + " The heartbeat tries again later.",
                    "until": until,
                }
            },
            "heartbeat.backed_off",
            {"reason": reason, "until": until},
        )

    def _advance(self, beat_id: str, reads: dict[str, dict[str, Any]]) -> None:
        with self.ws.rt.write() as tx:
            for cid, read in reads.items():
                for item in read["new"]:
                    tx.insert(
                        schema.heartbeat_seen,
                        {
                            "id": tx.new_id("hbs"),
                            "workspace_id": tx.workspace_id,
                            "connector_id": cid,
                            "item_id": item["id"],
                            "digest": item["digest"],
                            "beat_id": beat_id,
                            "seen_at": tx.now,
                        },
                    )
                current = tx.one(schema.heartbeat_connectors, cid, "connector")
                values: dict[str, Any] = {
                    "cursor": read["got"].get("cursor"),
                    "last_read_at": tx.now,
                    "last_items": len(read["new"]),
                    "status": "ok",
                }
                if read["got"].get("tools") is not None:
                    values["tools"] = read["got"]["tools"]
                    values["status_line"] = (
                        f"Read-only: {len(read['got']['tools'])} tools. "
                        f"{len(read['new'])} new last beat."
                    )
                tx.update(schema.heartbeat_connectors, current, values)

    def _finish(self, beat_id: str, started: float, *, status: str, **fields: Any) -> None:
        with self.ws.rt.write() as tx:
            row = tx.one(schema.heartbeat_beats, beat_id, "beat")
            if row["status"] != "running":
                return
            states.BEAT.check(row["status"], status)
            values: dict[str, Any] = {
                "status": status,
                "finished_at": tx.now,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
            for key in ("connectors", "items", "changes", "waits", "held", "errors", "details"):
                if key in fields:
                    values[key] = fields[key]
            if "tokens" in fields:
                values["tokens"] = fields["tokens"]
                values["tokens_unknown"] = int(fields.get("unknown") or 0)
            row = tx.update(schema.heartbeat_beats, row, values)
            tx.emit(
                "heartbeat.beat_finished",
                actor_id=row["created_by"],
                subject_type="heartbeat_beat",
                subject_id=beat_id,
                data={
                    "status": status,
                    "items": row["items"],
                    "changes": row["changes"],
                    "waits": row["waits"],
                    "held": row["held"],
                    "tokens": row["tokens"],
                },
            )

    # ---------------------------------------------------------------- writing

    def _suppressed(self) -> set[str]:
        with self.ws.rt.read() as tx:
            rows = tx.rows(
                sa.select(schema.heartbeat_suppressions.c.fingerprint).where(
                    schema.heartbeat_suppressions.c.workspace_id == tx.workspace_id
                )
            )
        return {r["fingerprint"] for r in rows}

    def protecting(self, text: str) -> dict[str, Any] | None:
        """The must-hold an item's words would quote or change: one whose trigger words it
        uses, among those its domain brings into play."""
        try:
            found = self.ws.rt.brain.preview(text[:2000])
        except UNREADABLE:  # the Brain or the CLI cannot say now
            return None
        low = text.lower()
        for hold in found.get("must_holds") or []:
            words = [str(t).lower() for t in hold.get("triggers") or [] if str(t).strip()]
            if words and any(w in low for w in words):
                return hold
        return None

    @staticmethod
    def wrote_label(write: dict[str, Any], projects: dict[str, str]) -> str:
        kind = write.get("kind")
        title = projects.get(str(write.get("project") or ""), str(write.get("project") or ""))
        if kind == "sheet":
            where = f"{write.get('sheet')} › {write.get('row')} › {write.get('column')}"
            return f"{where}: {write.get('value')}"
        if kind == "progress":
            return f"{title} › latest progress"
        if kind == "task":
            return f"{title} › Tasks: {_flat(write.get('text'), 80)}"
        return f"{write.get('area')}/{write.get('topic')}"

    def _propose(
        self, owner: Principal, item: dict[str, Any], write: dict[str, Any], line: str
    ) -> Any:
        """Make one write through the Brain's one proposal path, with the item as its source."""
        kind = write["kind"]
        at = str(item.get("at") or "")[:10]
        cited: dict[str, Any] = {
            "title": _flat(line or item["title"] or item["text"], 120),
            "evidence": _flat(
                f"Why: {write.get('reason') or 'it changed'}. From {item['connector_name']}: "
                f"{item['text']}",
                1200,
            ),
            "sources": [item["key"]],
            "source_locator": _flat(item.get("url") or item.get("title") or item["id"], 80),
            "source_speaker": item.get("speaker") or None,
            "source_excerpt": item["text"] or item["title"],
            "as_of": at if re.fullmatch(r"\d{4}-\d{2}-\d{2}", at) else None,
            "capture_origin": "connector",
            # A plain reason: an Auto change records it as why the governor kept it.
            "reason": _flat(
                f"{write.get('reason') or 'It changed'} (from {item['connector_name']}, "
                "read by the heartbeat)",
                300,
            ),
        }
        if kind == "sheet":
            value = _flat(write.get("value"), 300)
            return self.ws.brain.propose(
                owner,
                statement=f"{write.get('column')}: {value}",
                destination="sheet",
                place={k: write.get(k) for k in ("sheet", "row", "column")} | {"value": value},
                **cited,
            )
        if kind == "progress":
            return self.ws.brain.propose(
                owner,
                statement=_flat(write.get("text"), 600),
                destination="progress",
                place={"project": write.get("project"), "next_up": write.get("next_up") or ""},
                **cited,
            )
        if kind == "task":
            # A due date the model wrote another way is left out, not refused.
            due = str(write.get("due") or "")
            return self.ws.brain.propose(
                owner,
                statement=_flat(write.get("text"), 300),
                destination="todo",
                place={
                    "project": write.get("project") or "",
                    "owner": write.get("owner") or "",
                    "due": due if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due) else "",
                },
                **cited,
            )
        name = re.sub(r"[^a-z0-9]+", "-", str(write.get("topic") or "").lower()).strip("-")
        topic = f"{write.get('area')}/{name}" if name else None
        return self.ws.brain.propose(
            owner,
            statement=_flat(write.get("text"), 1200),
            kind="fact",
            topic=None if write.get("revises") else topic,
            revises=write.get("revises") or None,
            flags=[f for f in ("customer_facing", "spends") if write.get(f) is True] or None,
            **cited,
        )

    def _write_all(
        self,
        owner: Principal,
        beat_id: str,
        items: list[dict[str, Any]],
        judged: dict[str, Any],
        brain: dict[str, Any],
        details: list[str],
    ) -> dict[str, int]:
        region_ids = {r["id"] for r in brain["regions"]}
        projects = {p["id"]: p for p in brain["projects"]}
        titles = {p["id"]: p["title"] for p in brain["projects"]}
        sheets = {s["id"] for s in brain["sheets"]}
        holds = {h["id"]: h for h in brain["must_holds"]}
        by_key = {i["key"]: i for i in items}
        suppressed = self._suppressed()
        counts = {"changes": 0, "waits": 0, "held": 0}
        touched: dict[str, set[str]] = {}  # region: projects that moved
        lines: list[dict[str, Any]] = []
        for verdict in judged.get("items") or []:
            if not isinstance(verdict, dict):
                continue
            item = by_key.get(str(verdict.get("item") or ""))
            if item is None:
                continue
            region = str(verdict.get("region") or "")
            if region not in region_ids:
                details.append(
                    f"{item['connector_name']}: {item['title'] or item['id']} fits no region; "
                    "nothing written."
                )
                continue
            project = str(verdict.get("project") or "") or None
            if project and project not in projects:
                project = None
            text = _flat(verdict.get("line") or item["title"] or item["text"], 300)
            protected = holds.get(str(verdict.get("protected_by") or "")) or None
            writes = [w for w in verdict.get("writes") or [] if isinstance(w, dict)]
            if not writes:
                lines.append(self._line(beat_id, item, region, project, text, {}, "noted", "", ""))
                touched.setdefault(region, set())
                continue
            for write in writes:
                kind = str(write.get("kind") or "")
                reason = _flat(write.get("reason"), 300)
                target = write.get("project") or project
                if kind in ("progress", "task"):
                    write = {**write, "project": target}
                fingerprint = _hash(
                    item["key"],
                    kind,
                    {
                        k: write.get(k)
                        for k in (
                            "sheet",
                            "row",
                            "column",
                            "value",
                            "project",
                            "area",
                            "topic",
                            "revises",
                        )
                    },
                    _flat(write.get("text") or write.get("value"), 600).lower(),
                )
                if fingerprint in suppressed:
                    details.append(f"Not written again (you undid it): {text}")
                    continue
                status, wrote, problem = self._check_write(
                    write, kind, region_ids, projects, sheets, holds, item, protected
                )
                if status == "refused":
                    lines.append(
                        self._line(
                            beat_id,
                            item,
                            region,
                            project,
                            text,
                            write,
                            "refused",
                            f"Not written: {problem}",
                            reason,
                            fingerprint,
                        )
                    )
                    details.append(f"{item['connector_name']}: not written, {problem}")
                    continue
                if status == "held":
                    counts["held"] += 1
                    lines.append(
                        self._line(
                            beat_id,
                            item,
                            region,
                            project,
                            text,
                            write,
                            "held",
                            problem,
                            reason,
                            fingerprint,
                        )
                    )
                    details.append(f"{item['connector_name']}: {problem}")
                    touched.setdefault(region, set())
                    continue
                label = self.wrote_label(write, titles)
                try:
                    made = self._propose(owner, item, write, text)
                except WorkspaceError as exc:
                    lines.append(
                        self._line(
                            beat_id,
                            item,
                            region,
                            project,
                            text,
                            write,
                            "refused",
                            f"Not written: {_flat(str(exc), 200)}",
                            reason,
                            fingerprint,
                        )
                    )
                    details.append(f"{item['connector_name']}: not written, {_flat(str(exc), 160)}")
                    continue
                must_change = kind == "note" and str(write.get("revises") or "") in holds
                if made.status == "applied" and not must_change:
                    counts["changes"] += 1
                    line = self._line(
                        beat_id,
                        item,
                        region,
                        project,
                        text,
                        write,
                        "applied",
                        f"Wrote: {label}",
                        reason,
                        fingerprint,
                        proposal=made.proposal_id or made.entry_id,
                        checkpoint=made.checkpoint_id,
                    )
                    details.append(f"{item['connector_name']}: {text} → {label}")
                elif made.status in ("pending", "applied"):
                    counts["waits"] += 1
                    why = ["a must-hold change"] if must_change else list(made.waits or [])
                    said = f"Waits for you ({', '.join(why)}): " if why else "Waits for you: "
                    line = self._line(
                        beat_id,
                        item,
                        region,
                        project,
                        text,
                        write,
                        "waiting",
                        said + label,
                        reason,
                        fingerprint,
                        proposal=made.proposal_id,
                        checkpoint=made.checkpoint_id,
                    )
                    details.append(f"Waits for you: {text} ({item['connector_name']})")
                elif made.status == "duplicate":
                    details.append(f"Already waiting: {text}")
                    continue
                else:
                    line = self._line(
                        beat_id,
                        item,
                        region,
                        project,
                        text,
                        write,
                        "refused",
                        f"Not written: {_flat(made.message, 200)}",
                        reason,
                        fingerprint,
                    )
                    details.append(
                        f"{item['connector_name']}: not written, {_flat(made.message, 160)}"
                    )
                lines.append(line)
                if line["status"] in ("applied", "waiting"):
                    touched.setdefault(region, set())
                    if target and target in projects:
                        touched[region].add(str(target))
        self._keep_lines(owner, beat_id, lines, judged, touched, projects)
        return counts

    def _check_write(
        self,
        write: dict[str, Any],
        kind: str,
        regions: set[str],
        projects: dict[str, dict[str, Any]],
        sheets: set[str],
        holds: dict[str, dict[str, Any]],
        item: dict[str, Any],
        protected: dict[str, Any] | None,
    ) -> tuple[str, str, str]:
        """(go | held | refused, wrote, why): code's check of one write before it is made."""
        if kind not in WRITE_KINDS:
            return "refused", "", f"a write of kind {kind!r} is not one Gnomon makes"
        target = str(write.get("project") or "")
        if kind in ("progress", "task") and target not in projects:
            return "refused", "", "out of scope: no project it belongs to"
        if kind == "sheet" and str(write.get("sheet") or "") not in sheets:
            return "refused", "", "out of scope: no such sheet"
        if (
            kind == "note"
            and not write.get("revises")
            and str(write.get("area") or "") not in regions
        ):
            return "refused", "", "out of scope: no such region"
        if kind == "note" and write.get("revises") and str(write.get("revises")) in holds:
            return "go", "", ""  # a must-hold change: it goes in as a proposal that waits
        if target and str(projects.get(target, {}).get("status") or "") == "sealed":
            return "held", "", f"Held back: sealed project {projects[target]['title']}"
        if item.get("private"):
            return "held", "", "Held back: a private item"
        words = " ".join(str(write.get(k) or "") for k in ("value", "text")) + " " + item["text"]
        hold = protected or self.protecting(words)
        if hold:
            said = hold.get("line") or hold.get("text") or hold.get("title") or hold.get("id")
            return "held", "", f"Held back: must-hold: {_flat(said, 160)}"
        return "go", "", ""

    def _line(
        self,
        beat_id: str,
        item: dict[str, Any],
        region: str,
        project: str | None,
        text: str,
        write: dict[str, Any],
        status: str,
        wrote: str,
        reason: str,
        fingerprint: str = "",
        *,
        proposal: str | None = None,
        checkpoint: str | None = None,
    ) -> dict[str, Any]:
        return {
            "beat_id": beat_id,
            "region": region,
            "project": project,
            "text": text,
            "connector_id": item["connector_id"],
            "cli": item["cli"],
            "item_id": item["key"],
            "item_at": item.get("at") or None,
            "wrote": wrote,
            "write": write,
            "reason": reason,
            "status": status,
            "proposal_id": proposal,
            "checkpoint_id": checkpoint,
            "fingerprint": fingerprint or _hash(item["key"], text),
        }

    def _keep_lines(
        self,
        owner: Principal,
        beat_id: str,
        lines: list[dict[str, Any]],
        judged: dict[str, Any],
        touched: dict[str, set[str]],
        projects: dict[str, dict[str, Any]],
    ) -> None:
        said_heads, said_moved = judged.get("headlines"), judged.get("projects")
        headlines: dict[str, Any] = said_heads if isinstance(said_heads, dict) else {}
        moved: dict[str, Any] = said_moved if isinstance(said_moved, dict) else {}
        with self.ws.rt.write() as tx:
            for line in lines:
                line_id = tx.new_id("hbl")
                if line["status"] not in states.HEARTBEAT_LINE.states:
                    raise ValueError(line["status"])
                tx.insert(
                    schema.heartbeat_lines,
                    {
                        "id": line_id,
                        "workspace_id": tx.workspace_id,
                        **line,
                        "created_by": owner.actor_id,
                        "created_at": tx.now,
                        "updated_at": tx.now,
                    },
                )
                tx.emit(
                    "heartbeat.line_written",
                    actor_id=owner.actor_id,
                    subject_type="heartbeat_line",
                    subject_id=line_id,
                    data={
                        "beat_id": beat_id,
                        "region": line["region"],
                        "status": line["status"],
                        "source_id": line["item_id"],
                        "proposal_id": line["proposal_id"],
                        "checkpoint_id": line["checkpoint_id"],
                    },
                )
            # The headline is written again only where a line changed.
            for region, moved_projects in touched.items():
                row = tx.get(schema.heartbeat_regions, region)
                headline = _flat(headlines.get(region), 200)
                statuses = dict((row or {}).get("projects") or {})
                for pid in moved_projects:
                    said = _flat(moved.get(pid), 160)
                    if said:
                        statuses[pid] = {"status": said, "at": tx.now, "beat_id": beat_id}
                if row is None:
                    tx.insert(
                        schema.heartbeat_regions,
                        {
                            "id": region,
                            "workspace_id": tx.workspace_id,
                            "headline": headline,
                            "headline_at": tx.now if headline else None,
                            "projects": statuses,
                            "created_by": owner.actor_id,
                            "created_at": tx.now,
                            "updated_at": tx.now,
                        },
                    )
                else:
                    values: dict[str, Any] = {"projects": statuses}
                    if headline:
                        values.update(headline=headline, headline_at=tx.now)
                    tx.update(schema.heartbeat_regions, row, values)

    # ---------------------------------------------------------------- regions and undo

    def _line_view(
        self, row: dict[str, Any], names: dict[str, dict[str, Any]], latest: str | None
    ) -> dict[str, Any]:
        connector = names.get(row["connector_id"]) or {}
        held = row["status"] == "held"
        return {
            "id": row["id"],
            "beat_id": row["beat_id"],
            "region": row["region"],
            "project": row["project"],
            "text": row["text"],
            "connector_id": row["connector_id"],
            "connector": connector.get("name") or row["connector_id"],
            "how": connector.get("how_label") or "",
            "cli": row["cli"],
            "cli_label": CLI_LABELS.get(row["cli"], row["cli"]),
            "at": row["item_at"] or row["created_at"],
            "written_at": row["created_at"],
            "wrote": row["wrote"],
            "write": row["write"],
            "reason": row["reason"],
            "status": row["status"],
            "held": held,
            "new_this_beat": latest is not None and row["beat_id"] == latest,
            "proposal_id": row["proposal_id"],
            "checkpoint_id": row["checkpoint_id"],
            "source_id": row["item_id"],
            "can_undo": row["status"] in ("applied", "waiting"),
        }

    def regions(self, who: Principal) -> list[dict[str, Any]]:
        """Live status per region: headline, lines (text, connector, CLI, time, what it
        wrote), projects with their status."""
        who.require("brain.read")
        brain = self._brain()
        names = {c["id"]: c for c in (self._connector_view(r) for r in self._connectors())}
        kept = self._regions_now()
        last = next((b for b in self._beats(limit=10) if b["status"] == "done"), None)
        latest = last["id"] if last else None
        with self.ws.rt.read() as tx:
            rows = tx.rows(
                sa.select(schema.heartbeat_lines)
                .where(schema.heartbeat_lines.c.workspace_id == tx.workspace_id)
                .order_by(
                    schema.heartbeat_lines.c.created_at.desc(), schema.heartbeat_lines.c.id.desc()
                )
                .limit(500)
            )
        projects = {p["id"]: p for p in brain["projects"]}
        out = []
        for region in brain["regions"]:
            # A write the Brain refused stays in its beat's record, not in the region's lines.
            mine = [
                self._line_view(r, names, latest)
                for r in rows
                if r["region"] == region["id"] and r["status"] != "refused"
            ]
            row = kept.get(region["id"]) or {}
            statuses = dict(row.get("projects") or {})
            listed = []
            for pid, said in statuses.items():
                project = projects.get(pid)
                if project is None or project["status"] == "sealed":
                    continue
                sources = sorted({x["connector"] for x in mine if x["project"] == pid})
                listed.append(
                    {
                        "id": pid,
                        "title": project["title"],
                        "status": said.get("status") or "",
                        "at": said.get("at"),
                        "from": sources[:2],
                    }
                )
            out.append(
                {
                    "id": region["id"],
                    "name": region["name"],
                    "headline": row.get("headline") or "",
                    "headline_at": row.get("headline_at"),
                    "updated_at": mine[0]["written_at"] if mine else None,
                    "lines": mine[:50],
                    # Items, not writes: one item that moved two homes is one new line.
                    "new_this_beat": len(
                        {
                            (x["beat_id"], x["source_id"])
                            for x in mine
                            if x["new_this_beat"] and x["status"] != "undone"
                        }
                    ),
                    "projects": listed,
                }
            )
        return out

    def undo(self, who: Principal, line_id: str) -> dict[str, Any]:
        """Undo one line: its write is undone the way any undo is (an undo point taken back, or
        a waiting proposal turned down), the line is marked undone, and the next beat will not
        write it again."""
        who.require("brain.govern")
        with self.ws.rt.read() as tx:
            row = tx.get(schema.heartbeat_lines, line_id)
        if row is None or row["workspace_id"] != self.ws.rt.workspace_id:
            raise NotFound(f"No line {line_id}.", id=line_id)
        states.HEARTBEAT_LINE.check(row["status"], "undone")
        how = "noted"
        if row["status"] == "applied" and row["checkpoint_id"]:
            self.ws.brain.undo(who, row["checkpoint_id"])
            how = "undone"
        elif row["status"] in ("waiting", "applied") and row["proposal_id"]:
            try:
                self.ws.brain.decide(
                    who, row["proposal_id"], approve=False, reason="Undone from the heartbeat."
                )
                how = "turned down"
            except NotFound as exc:
                raise Conflict(
                    "That change was already decided in Catch up: undo it from Undo points."
                ) from exc
        with self.ws.rt.write() as tx:
            current = tx.one(schema.heartbeat_lines, line_id, "line")
            states.HEARTBEAT_LINE.check(current["status"], "undone")
            tx.update(schema.heartbeat_lines, current, {"status": "undone"})
            if (
                tx.first(
                    sa.select(schema.heartbeat_suppressions.c.id).where(
                        schema.heartbeat_suppressions.c.fingerprint == current["fingerprint"]
                    )
                )
                is None
            ):
                tx.insert(
                    schema.heartbeat_suppressions,
                    {
                        "id": tx.new_id("hbx"),
                        "workspace_id": tx.workspace_id,
                        "fingerprint": current["fingerprint"],
                        "line_id": line_id,
                        "created_at": tx.now,
                    },
                )
            tx.emit(
                "heartbeat.line_undone",
                actor_id=who.actor_id,
                subject_type="heartbeat_line",
                subject_id=line_id,
                data={
                    "how": how,
                    "proposal_id": current["proposal_id"],
                    "checkpoint_id": current["checkpoint_id"],
                },
            )
        names = {c["id"]: c for c in (self._connector_view(r) for r in self._connectors())}
        with self.ws.rt.read() as tx:
            done = tx.one(schema.heartbeat_lines, line_id, "line")
        out = self._line_view(done, names, None)
        out["line"] = "Undone. The next beat won't write that again."
        return out


class ConnectorProblem(Exception):
    def __init__(
        self,
        status: str,
        line: str,
        *,
        present: bool | None = None,
        tools: list[str] | None = None,
    ) -> None:
        super().__init__(line)
        self.status = status
        self.line = line
        self.present = present
        self.tools = tools


class HeartbeatWorker:
    """Runs the beats that are due while the computer is on (and the server with it)."""

    def __init__(self, heartbeat: Heartbeat, interval: float = 30.0) -> None:
        self.heartbeat = heartbeat
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._looked = False  # whether it looked for connectors since the server started

    def run_once(self) -> dict[str, Any] | None:
        owner = self.heartbeat.ws.owner()
        if not self._looked and not self.heartbeat.connectors(owner):
            # A new Brain: find the connectors in the CLIs once, as "Find connectors" would.
            self._looked = True
            self.heartbeat.rescan(owner)
        self._looked = True
        if not self.heartbeat.due():
            return None
        if not any(c["enabled"] for c in self.heartbeat.connectors(owner)):
            return None
        return self.heartbeat.beat(self.heartbeat.ws.owner(), "schedule")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except UNREADABLE:  # the Brain or the CLI cannot say now
                log.warning("a scheduled beat could not run", exc_info=True)
            self._stop.wait(self.interval)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
