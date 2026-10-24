"""Scout (Release 1 plan, M03): the person's chosen folders, inspected when they press Scan now.

A scan reads every file of a chosen format in the chosen folders and compares it with what the
last successful scan saw, by content hash, never by file time:

    new       a file Scout has not seen
    changed   a file whose content changed since the last scan
    renamed   the same content under another name (nothing is proposed for it)
    removed   a file that is gone

A save without a change, or a rename, stays quiet: nothing is proposed. A new or changed file
is a difference the person can bring in, which makes it a capture: from there it goes through
Distill and Catch up like anything else captured. Nothing in a folder is ever moved, changed
or deleted. Watching folders and scanning on a schedule are a later phase.

Kept in the workspace's settings (`scout`): the folders, the formats, the inventory of the
last successful scan, the differences waiting, and when the last scan succeeded or failed.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from brainkit.importers import gate_folder
from workspace_core.clock import iso
from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import NotFound, ValidationFailed
from workspace_core.ids import new_id

FORMATS = {
    "md": True,
    "txt": True,
    "docx": True,
    "pdf": True,
    "xlsx": True,
    "csv": False,
    "vtt": True,
    "srt": True,
    "html": False,
    "pptx": False,
}
MAX_FILES = 2000  # files read in one scan
MAX_BYTES = 25 * 1024 * 1024
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
MAX_FOLDERS = 20


def _hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Scout:
    def __init__(self, ws: Any) -> None:
        self.ws = ws

    # ---------------------------------------------------------------- settings
    def _load(self) -> dict[str, Any]:
        with self.ws.rt.read() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
        found = dict((row["settings"] or {}).get("scout") or {})
        found.setdefault("folders", [])
        found["formats"] = {**FORMATS, **(found.get("formats") or {})}
        found.setdefault("inventory", {})
        found.setdefault("differences", [])
        return found

    def _save(self, state: dict[str, Any], event: str, who: Principal) -> None:
        with self.ws.rt.write() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
            tx.update(
                schema.workspaces, row, {"settings": {**(row["settings"] or {}), "scout": state}}
            )
            tx.emit(
                event,
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=row["id"],
                data={},
            )

    def overview(self, who: Principal) -> dict[str, Any]:
        """The folders, formats, the last inspection and the differences waiting."""
        who.require("context.read")
        state = self._load()
        return {
            "folders": state["folders"],
            "formats": state["formats"],
            "last_inspection": state.get("last_inspection"),
            "last_error": state.get("last_error"),
            "files_seen": len(state["inventory"]),
            "differences": [d for d in state["differences"] if d.get("status") == "waiting"],
            "later": ["Watching folders", "Scans on a schedule", "Connected tools"],
        }

    def configure(
        self,
        who: Principal,
        *,
        folders: list[dict[str, Any]] | None = None,
        formats: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        who.require("workspace.admin")
        state = self._load()
        if folders is not None:
            clean = []
            for folder in folders[:MAX_FOLDERS]:
                path = os.path.abspath(os.path.expanduser(str(folder.get("path") or "")))
                problem = gate_folder(path)
                if problem:
                    raise ValidationFailed(problem, field="folders")
                clean.append({"path": path, "project": folder.get("project") or None})
            state["folders"] = clean
        if formats is not None:
            unknown = [k for k in formats if k not in FORMATS]
            if unknown:
                raise ValidationFailed(
                    f"Formats are {', '.join(FORMATS)}; not {', '.join(unknown)}.", field="formats"
                )
            state["formats"] = {**state["formats"], **{k: bool(v) for k, v in formats.items()}}
        self._save(state, "scout.configured", who)
        return self.overview(who)

    # ---------------------------------------------------------------- scanning
    def scan(self, who: Principal) -> dict[str, Any]:
        """Scan now: compare every chosen file with the last successful scan, by content."""
        who.require("context.write")
        state = self._load()
        if not state["folders"]:
            raise ValidationFailed("Choose a folder for Scout first.", field="folders")
        wanted = tuple(f".{k}" for k, on in state["formats"].items() if on)
        seen: dict[str, dict[str, Any]] = {}
        unreadable: list[str] = []
        try:
            for folder in state["folders"]:
                for current, dirs, files in os.walk(folder["path"]):
                    dirs[:] = sorted(
                        d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                    )
                    for name in sorted(files):
                        if not name.lower().endswith(wanted) or len(seen) >= MAX_FILES:
                            continue
                        path = os.path.join(current, name)
                        try:
                            size = os.path.getsize(path)
                            if size > MAX_BYTES:
                                continue
                            seen[path] = {
                                "hash": _hash(path),
                                "size": size,
                                "project": folder.get("project"),
                            }
                        except OSError:
                            unreadable.append(path)
        except OSError as exc:
            state["last_error"] = {"at": iso(self.ws.rt.clock.now()), "why": str(exc)}
            self._save(state, "scout.failed", who)
            raise ValidationFailed(f"Scout could not read a folder: {exc}") from exc
        before: dict[str, dict[str, Any]] = state["inventory"]
        old_hashes = {v["hash"]: p for p, v in before.items()}
        waiting = {d["path"]: d for d in state["differences"] if d.get("status") == "waiting"}
        found: list[dict[str, Any]] = []
        now = iso(self.ws.rt.clock.now())
        for path, info in seen.items():
            was = before.get(path)
            if was is not None and was["hash"] == info["hash"]:
                continue  # saved without a change: quiet
            if was is None and info["hash"] in old_hashes and old_hashes[info["hash"]] not in seen:
                found.append(
                    {
                        "kind": "renamed",
                        "path": path,
                        "from": old_hashes[info["hash"]],
                        "quiet": True,
                    }
                )
                continue  # the same content under a new name: nothing to bring in
            kind = "changed" if was is not None else "new"
            found.append(
                {"kind": kind, "path": path, "size": info["size"], "project": info.get("project")}
            )
        renamed_from = {d["from"] for d in found if d["kind"] == "renamed"}
        for path in before:
            if path not in seen and path not in renamed_from:
                found.append({"kind": "removed", "path": path, "quiet": True})
        for diff in found:
            if diff.get("quiet"):
                continue
            prior = waiting.get(diff["path"])
            if prior is not None:
                prior.update(kind=diff["kind"], size=diff.get("size"), at=now)
                continue
            state["differences"].append(
                {
                    "id": new_id("scd", self.ws.rt.clock.now()),
                    "status": "waiting",
                    "at": now,
                    **diff,
                }
            )
        state["differences"] = state["differences"][-200:]
        state["inventory"] = seen
        state["last_inspection"] = now
        state.pop("last_error", None)
        self._save(state, "scout.scanned", who)
        out = self.overview(who)
        out["found"] = found
        out["unreadable"] = unreadable[:20]
        return out

    # ---------------------------------------------------------------- differences
    def _difference(self, state: dict[str, Any], diff_id: str) -> dict[str, Any]:
        found = next(
            (
                d
                for d in state["differences"]
                if d["id"] == diff_id and d.get("status") == "waiting"
            ),
            None,
        )
        if found is None:
            raise NotFound(f"No waiting difference {diff_id}.", id=diff_id)
        return found

    def bring_in(self, who: Principal, diff_id: str) -> dict[str, Any]:
        """Make a difference a capture: from there it is distilled and reviewed as usual."""
        who.require("context.write")
        state = self._load()
        diff = self._difference(state, diff_id)
        try:
            with open(diff["path"], "rb") as handle:
                data = handle.read()
        except OSError as exc:
            raise ValidationFailed(f"Scout could not read {diff['path']}: {exc}") from exc
        note = self.ws.captures.bring_in(who, data=data, filename=os.path.basename(diff["path"]))
        diff.update(status="captured", capture_id=note.id)
        self._save(state, "scout.brought_in", who)
        return {"difference": diff, "capture_id": note.id}

    def dismiss(self, who: Principal, diff_id: str) -> dict[str, Any]:
        who.require("context.write")
        state = self._load()
        diff = self._difference(state, diff_id)
        diff["status"] = "dismissed"
        self._save(state, "scout.dismissed", who)
        return self.overview(who)
