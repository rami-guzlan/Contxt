"""Workspace's live context (UX plan 4.3, BL 8): sheets, boards and calendars over the Brain's
State tier. One sheet, three views: a board groups rows by a status column and a calendar
places them by a date column, and moving a card or an event is a cell write with its history,
exactly like editing the grid. The sheets live in the Brain's vault (brainkit/state.py); this
service is the owner's door to them, and every change is a bus event.
"""

from __future__ import annotations

from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.errors import ValidationFailed

from .runtime import Runtime

VIEWS = ("grid", "board", "calendar")


class LiveContext:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def overview(self, who: Principal) -> dict[str, Any]:
        """The sheets, the templates, and the AI values waiting for the owner."""
        who.require("brain.read")
        port = self.rt.brain
        return {
            "sheets": port.state_act("sheets").get("sheets") or [],
            "templates": port.state_act("templates").get("templates") or [],
            "waiting": port.state_act("waiting").get("waiting") or [],
        }

    def sheet(self, who: Principal, sheet_id: str) -> dict[str, Any]:
        """One sheet: its columns, rows (current values, computed ones, AI marks, what waits)
        and summary row."""
        who.require("brain.read")
        return self.rt.brain.state_act("rows", {"sheet": sheet_id})

    def history(
        self, who: Principal, sheet_id: str, row: str, column: str | None = None
    ) -> list[dict[str, Any]]:
        who.require("brain.read")
        found = self.rt.brain.state_act(
            "history", {"sheet": sheet_id, "row": row, "column": column}
        )
        return list(found.get("events") or [])

    def act(self, who: Principal, action: str, fields: dict[str, Any]) -> dict[str, Any]:
        """create_sheet, add_column, add_row, write, touch, decide, remove_row."""
        who.require("brain.govern")
        if action not in (
            "create_sheet",
            "add_column",
            "add_row",
            "write",
            "touch",
            "decide",
            "remove_row",
        ):
            raise ValidationFailed(f"Unknown action {action!r}.", field="action")
        done = self.rt.brain.state_act(action, fields)
        sheet_id = str(fields.get("sheet") or (done.get("sheet") or {}).get("id") or "")
        with self.rt.write() as tx:
            tx.emit(
                f"state.{action}",
                actor_id=who.actor_id,
                subject_type="sheet",
                subject_id=sheet_id or "state",
                data={k: fields.get(k) for k in ("row", "key", "column") if fields.get(k)},
                noise=action in ("write", "touch"),
            )
        if action == "create_sheet":
            return done
        return self.sheet(who, sheet_id) if sheet_id else done
