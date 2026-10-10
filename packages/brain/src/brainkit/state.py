"""The State tier (brain-logic plan 8): structured, current values per entity that change faster
than anyone can review, such as an account's stakeholders and health, a repo's owners, a
standard's current version. Not knowledge (nothing here is reviewed before it applies) and not
documents. People edit it in Workspace as sheets, boards and calendars (one sheet, three views);
AIs read it with `get_state` and write it with `update_state`; every change is a cell event with
who, when and why, so the history is the log itself.

Files, the same pattern as project journals (decision 3):

    state/<sheet>/schema.json      the sheet: key column, typed columns, partition rule, scope
    state/<sheet>/<row>.jsonl      append-only events: a row made, a cell written, an alias
    state/<sheet>/SNAPSHOT.md      generated, for people and for git diffs

A column says who may change it (its friction): `free` (AIs may change it; their values are
marked AI-filled until a person touches them), `confirm` (an AI's value waits for one tap) or
`locked` (only a person, or for the Tasks sheet only `hand_off`). Under the regulated preset
every AI write waits (decision 4). A column may have an age limit; older values are flagged
stale. Computed columns (formulas.py) are worked out at read time, never written, and never
editable by AIs.

Partitions stay sealed: a sheet with a partition rule files each row under the partition its
partition column names, and a caller sees only the partitions it may. Must-holds win over any
cell: a brief carries both, the must-hold first.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from . import formulas, util

TYPES = ("text", "number", "money", "date", "date_range", "status", "person", "link",
         "reference")
FRICTIONS = ("free", "confirm", "locked")
FRICTION_WORDS = {"free": "AIs may change", "confirm": "Ask me first", "locked": "Only me"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
MAX_COLUMNS = 40
MAX_VALUE = 2000
ROW_TOKENS = 300  # a row's block in a brief, at most
FOLDER = "state"


@dataclass
class Column:
    name: str
    type: str = "text"
    friction: str = "free"
    age_days: int | None = None
    source: str = ""
    sensitivity: str = ""
    options: list[str] = field(default_factory=list)  # a status column's values
    ref: str = ""                                     # a reference column's sheet
    formula: str = ""                                 # a computed column

    @property
    def computed(self) -> bool:
        return bool(self.formula)


@dataclass
class Sheet:
    id: str
    title: str
    key: str
    columns: list[Column]
    partition_by: str = ""
    scope: str = ""
    template: str = ""
    builtin: bool = False
    description: str = ""

    def column(self, name: str) -> Column | None:
        wanted = str(name or "").strip().lower()
        return next((c for c in self.columns if c.name.lower() == wanted), None)

    def to_dict(self) -> dict:
        out = asdict(self)
        for column in out["columns"]:
            if column["formula"]:
                column["formula_words"] = formulas.describe(column["formula"])
        return out


@dataclass
class Cell:
    value: Any
    at: str
    by: str
    said_by: str = ""
    as_of: str = ""
    source: str = ""
    ai: bool = False
    stale: bool = False


@dataclass
class Row:
    id: str
    key: str
    aliases: list[str]
    partition: str
    created: str
    updated: str
    cells: dict[str, Cell]
    pending: list[dict]
    computed: dict[str, Any] = field(default_factory=dict)

    def value(self, column: str) -> Any:
        cell = self.cells.get(column)
        return None if cell is None else cell.value

    def to_dict(self) -> dict:
        return {"id": self.id, "key": self.key, "aliases": self.aliases,
                "partition": self.partition, "created": self.created,
                "updated": self.updated,
                "cells": {k: asdict(v) for k, v in self.cells.items()},
                "computed": self.computed, "pending": self.pending}


# ---------------------------------------------------------------------- templates
def _cols(*specs) -> list[Column]:
    return [Column(**spec) if isinstance(spec, dict) else Column(name=spec) for spec in specs]


TASK_STATUSES = ["open", "handed_off", "working", "waiting_for_you", "blocked", "done",
                 "dropped"]
TEMPLATES: dict[str, dict] = {
    "accounts": {"title": "Accounts", "key": "Account", "columns": _cols(
        "Account", {"name": "Stage", "type": "status",
                    "options": ["prospect", "active", "renewing", "churned"]},
        {"name": "Health", "type": "status", "options": ["green", "amber", "red"],
         "age_days": 30},
        {"name": "Owner", "type": "person"}, {"name": "Renewal date", "type": "date"},
        {"name": "Value", "type": "money"}, {"name": "Last contact", "type": "date"},
        {"name": "Next step", "age_days": 14},
        {"name": "Days until renewal", "formula": "[Renewal date] - TODAY()"})},
    "repos": {"title": "Repos or services", "key": "Repo", "columns": _cols(
        "Repo", {"name": "Owner", "type": "person"}, {"name": "Status", "type": "status",
                                                      "options": ["active", "frozen",
                                                                  "retired"]},
        {"name": "Gotchas", "age_days": 90}, {"name": "Link", "type": "link"})},
    "standards": {"title": "Standards", "key": "Standard", "columns": _cols(
        "Standard", {"name": "Current version"}, {"name": "Effective", "type": "date"},
        {"name": "Owner", "type": "person"}, {"name": "Link", "type": "link"})},
    "vendors": {"title": "Vendors", "key": "Vendor", "columns": _cols(
        "Vendor", {"name": "Contact", "type": "person"}, {"name": "Contract end",
                                                          "type": "date"},
        {"name": "Cost", "type": "money"}, {"name": "Status", "type": "status",
                                            "options": ["trial", "active", "ending"]})},
    "contacts": {"title": "Contacts", "key": "Name", "columns": _cols(
        "Name", {"name": "Email"}, {"name": "Role"}, {"name": "Company"},
        {"name": "Last contact", "type": "date"})},
    "content-calendar": {"title": "Content calendar", "key": "Piece", "columns": _cols(
        "Piece", {"name": "Channel", "type": "status",
                  "options": ["blog", "email", "social", "webinar"]},
        {"name": "Status", "type": "status", "options": ["idea", "drafting", "review",
                                                         "scheduled", "published"]},
        {"name": "Publish date", "type": "date"}, {"name": "Owner", "type": "person"})},
    "project-board": {"title": "Project board", "key": "Item", "columns": _cols(
        "Item", {"name": "Status", "type": "status", "options": ["todo", "doing", "done"]},
        {"name": "Owner", "type": "person"}, {"name": "Due", "type": "date"})},
    "tasks": {"title": "Tasks", "key": "Task id", "builtin": True,
              "description": "Every task, who owns it and where it stands. Owner, Status, "
                             "Evidence and Card change only through hand_off.",
              "columns": _cols(
                  "Task id", {"name": "Task"}, {"name": "Goal", "friction": "confirm"},
                  {"name": "Project"}, {"name": "For"},
                  {"name": "Milestone", "type": "status", "options": ["yes", "no"],
                   "friction": "confirm"},
                  {"name": "Owner", "friction": "locked"}, {"name": "Tool"},
                  {"name": "Status", "type": "status", "options": TASK_STATUSES,
                   "friction": "locked"},
                  {"name": "Due", "type": "date", "friction": "confirm"},
                  {"name": "Evidence", "friction": "locked"},
                  {"name": "Card", "friction": "locked"},
                  {"name": "Days open", "formula": "TODAY() - CREATED()"},
                  {"name": "Since update", "formula": "TODAY() - UPDATED()"})},
}
HANDOFF_ONLY = ("Owner", "Status", "Evidence", "Card")  # the Tasks sheet's, through hand_off


# ---------------------------------------------------------------------- reading
def _folder(brain, sheet_id: str) -> str:
    return brain.vault.path(FOLDER, sheet_id)


def _load(raw: dict) -> Sheet:
    columns = [Column(**{k: v for k, v in c.items() if k in Column.__dataclass_fields__})
               for c in raw.get("columns") or []]
    return Sheet(id=raw["id"], title=raw.get("title") or raw["id"], key=raw.get("key") or
                 (columns[0].name if columns else ""), columns=columns,
                 partition_by=raw.get("partition_by") or "", scope=raw.get("scope") or "",
                 template=raw.get("template") or "", builtin=bool(raw.get("builtin")),
                 description=raw.get("description") or "")


def sheets(brain) -> list[Sheet]:
    base = brain.vault.path(FOLDER)
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "schema.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                out.append(_load(json.load(handle)))
    return out


def sheet(brain, sheet_id: str) -> Sheet | None:
    path = os.path.join(_folder(brain, str(sheet_id or "")), "schema.json")
    if not SLUG.match(str(sheet_id or "")) or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return _load(json.load(handle))


def _events(brain, sheet_id: str, row_id: str) -> list[dict]:
    return util.read_jsonl(os.path.join(_folder(brain, sheet_id), f"{row_id}.jsonl"))


def _age(stamp: str, today: dt.date) -> int | None:
    found = util.parse_date(str(stamp or "")[:10])
    return None if found is None else (today - found).days


def _build(found: Sheet, row_id: str, events: list[dict], today: dt.date) -> Row | None:
    made = next((e for e in events if e.get("kind") == "row"), None)
    if made is None or any(e.get("kind") == "removed" for e in events):
        return None
    cells: dict[str, Cell] = {}
    pending: list[dict] = []
    aliases = list(made.get("aliases") or [])
    decided = {e.get("event") for e in events if e.get("kind") in ("confirmed", "declined")}
    confirmed = {e.get("event") for e in events if e.get("kind") == "confirmed"}
    touched_by_person: dict[str, bool] = {}
    for event in events:
        kind = event.get("kind")
        if kind == "alias":
            aliases = list(event.get("aliases") or [])
        elif kind == "cell":
            if event.get("pending") and event.get("id") not in confirmed:
                if event.get("id") not in decided:
                    pending.append(event)
                continue
            column = str(event.get("column"))
            ai = bool(event.get("ai"))
            cells[column] = Cell(value=event.get("value"), at=str(event.get("at") or ""),
                                 by=str(event.get("by") or ""),
                                 said_by=str(event.get("said_by") or ""),
                                 as_of=str(event.get("as_of") or ""),
                                 source=str(event.get("source") or ""), ai=ai)
            touched_by_person[column] = not ai
        elif kind == "touched":
            column = str(event.get("column"))
            if column in cells:
                cells[column].ai = False
    for name, cell in cells.items():
        column = found.column(name)
        if column and column.age_days:
            age = _age(cell.as_of or cell.at, today)
            cell.stale = age is not None and age > int(column.age_days)
    partition = ""
    if found.partition_by:
        partition = str((cells.get(found.partition_by).value
                         if cells.get(found.partition_by) else "") or "")
    updated = max([str(e.get("at") or "") for e in events] or [""])
    return Row(id=row_id, key=str(made.get("key") or row_id), aliases=aliases,
               partition=util.slugify(partition) if partition else "",
               created=str(made.get("at") or ""), updated=updated, cells=cells,
               pending=pending)


def rows(brain, sheet_id: str, *, partitions=None, today: dt.date | None = None,
         with_computed: bool = True) -> list[Row]:
    """A sheet's rows with their current values (the latest valid event per cell), computed
    columns worked out. With `partitions`, only rows in those partitions (and unpartitioned
    ones) are seen."""
    found = sheet(brain, sheet_id)
    if found is None:
        return []
    today = today or util.today_date()
    folder = _folder(brain, sheet_id)
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".jsonl"):
            continue
        row = _build(found, name[:-6], _events(brain, sheet_id, name[:-6]), today)
        if row is None:
            continue
        if partitions is not None and found.partition_by and row.partition \
                and row.partition not in partitions:
            continue
        out.append(row)
    if with_computed:
        _compute(brain, found, out, today)
    return out


def _linked_rows(brain, sheet_id: str, target: Sheet, row: Row, today) -> list[dict]:
    """Rows of another sheet whose reference column points at this row."""
    other = sheet(brain, sheet_id)
    if other is None:
        return []
    refs = [c.name for c in other.columns if c.type == "reference" and c.ref == target.id]
    found = []
    for candidate in rows(brain, sheet_id, today=today, with_computed=False):
        if any(str(candidate.value(r) or "").lower() in (row.id, row.key.lower())
               for r in refs):
            found.append({k: c.value for k, c in candidate.cells.items()})
    return found


def _compute(brain, found: Sheet, out: list[Row], today: dt.date) -> None:
    computed = [c for c in found.columns if c.computed]
    if not computed:
        return
    names = [c.name for c in found.columns]
    parsed = {}
    for column in computed:
        try:
            parsed[column.name] = formulas.parse(column.formula, names)
        except formulas.FormulaError:
            continue
    for row in out:
        values = {k: c.value for k, c in row.cells.items()}
        ages = {k: _age(c.at, today) or 0 for k, c in row.cells.items()}

        def lookup(ref: str, column: str, row=row) -> Any:
            ref_column = next((c for c in found.columns if c.type == "reference"
                               and str(row.value(c.name) or "") == ref), None)
            if ref_column is None or not ref_column.ref:
                return None
            for target in rows(brain, ref_column.ref, today=today, with_computed=False):
                if ref.lower() in (target.id, target.key.lower()):
                    return target.value(column)
            return None

        reader = formulas.Row(values, created=row.created, updated=row.updated, ages=ages,
                              linked=lambda sid, row=row: _linked_rows(brain, sid, found, row,
                                                                       today),
                              lookup=lookup)
        for name, (tree, slots) in parsed.items():
            row.computed[name] = formulas.evaluate(tree, slots, reader, today)


def summary(found: Sheet, out: list[Row]) -> dict:
    """The summary row: counts, sums and averages per column, and counts by status."""
    result: dict[str, dict] = {}
    for column in found.columns:
        values = [row.computed.get(column.name) if column.computed else row.value(column.name)
                  for row in out]
        filled = [v for v in values if v not in (None, "")]
        entry: dict[str, Any] = {"filled": len(filled)}
        if column.type == "status":
            counts: dict[str, int] = {}
            for value in filled:
                counts[str(value)] = counts.get(str(value), 0) + 1
            entry["by_status"] = counts
        numbers = [n for n in (formulas._number(v) for v in filled) if n is not None]
        if column.type in ("number", "money") or (column.computed and numbers
                                                  and len(numbers) == len(filled)):
            entry["sum"] = round(sum(numbers), 4) if numbers else 0
            entry["average"] = round(sum(numbers) / len(numbers), 4) if numbers else None
        result[column.name] = entry
    return {"rows": len(out), "columns": result}


def history(brain, sheet_id: str, row_id: str, column: str | None = None) -> list[dict]:
    """A row's events, newest first (a column's only, with `column`)."""
    events = _events(brain, sheet_id, row_id)
    if column:
        events = [e for e in events if str(e.get("column") or "").lower()
                  == str(column).lower()]
    return list(reversed(events))


# ---------------------------------------------------------------------- writing
def _result(message, data=None, is_error=False):
    from .governance import _result as result
    return result(message, data, is_error)


def _check_value(column: Column, value: Any, brain=None) -> tuple[Any, str]:
    """(the value as stored, why it cannot be) for one cell."""
    if value is None or value == "":
        return "", ""
    if isinstance(value, (dict, list)):
        return None, f"{column.name} takes one value"
    text = " ".join(str(value).split())[:MAX_VALUE]
    kind = column.type
    if kind in ("number", "money"):
        number = formulas._number(text)
        if number is None:
            return None, f"{column.name} is a number"
        return (int(number) if number.is_integer() else number), ""
    if kind == "date":
        found = util.parse_date(text[:10])
        if found is None:
            return None, f"{column.name} is a date (YYYY-MM-DD)"
        return found.isoformat(), ""
    if kind == "date_range":
        parts = [p.strip() for p in re.split(r"\s+to\s+|\s*/\s*|\s*\.\.\s*", text) if p.strip()]
        dates = [util.parse_date(p[:10]) for p in parts[:2]]
        if len(dates) != 2 or dates[0] is None or dates[1] is None:
            return None, f"{column.name} is a date range (YYYY-MM-DD to YYYY-MM-DD)"
        return f"{dates[0].isoformat()} to {dates[1].isoformat()}", ""
    if kind == "status" and column.options:
        wanted = text.lower()
        match = next((o for o in column.options
                      if o.lower() in (wanted, wanted.replace(" ", "_"))), None)
        if match is None:
            return None, f"{column.name} is one of {', '.join(column.options)}"
        return match, ""
    if kind == "link" and not re.match(r"^(https?://|mailto:|/)", text):
        return None, f"{column.name} is a link (https://...)"
    if kind == "reference" and brain is not None and column.ref:
        target = find_row(brain, column.ref, text)
        if target is None:
            return None, f"{column.name} names a row of {column.ref}"
        return target.key, ""
    return text, ""


def _event_id() -> str:
    return util.short_hash(util.now_iso() + os.urandom(8).hex(), 10)


def _write(brain, sheet_id: str, row_id: str, events: list[dict], message: str) -> None:
    path = os.path.join(_folder(brain, sheet_id), f"{row_id}.jsonl")
    brain.vault.touch(path)
    for event in events:
        util.append_jsonl(path, event)
    snapshot = write_snapshot(brain, sheet_id)
    brain.after_write([path, snapshot], message)


def _save_schema(brain, found: Sheet) -> str:
    path = os.path.join(_folder(brain, found.id), "schema.json")
    brain.vault.touch(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    util.atomic_write(path, json.dumps(asdict(found), indent=2, sort_keys=True) + "\n")
    return path


def schema_problems(columns: list[Column], key: str, partition_by: str = "") -> list[str]:
    problems = []
    names = [c.name.strip() for c in columns]
    if not columns:
        problems.append("a sheet needs at least one column")
    if len(columns) > MAX_COLUMNS:
        problems.append(f"a sheet has at most {MAX_COLUMNS} columns")
    if len({n.lower() for n in names}) != len(names):
        problems.append("two columns share a name")
    if key and key.lower() not in (n.lower() for n in names):
        problems.append(f"the key column {key!r} is not a column")
    if partition_by and partition_by.lower() not in (n.lower() for n in names):
        problems.append(f"the partition column {partition_by!r} is not a column")
    for column in columns:
        if not column.name.strip() or len(column.name) > 80 or "[" in column.name \
                or "]" in column.name:
            problems.append("a column's name is a few words, without brackets")
        if column.type not in TYPES:
            problems.append(f"{column.name}: a column's type is one of {', '.join(TYPES)}")
        if column.friction not in FRICTIONS:
            problems.append(f"{column.name}: who may change it is one of "
                            f"{', '.join(FRICTIONS)}")
        if column.type == "reference" and not column.ref:
            problems.append(f"{column.name}: a reference names the sheet it points to")
        if column.formula:
            try:
                formulas.parse(column.formula, names)
            except formulas.FormulaError as exc:
                problems.append(f"{column.name}: {exc}")
    return problems


def create_sheet(brain, *, title: str = "", template: str = "", columns=None, key: str = "",
                 sheet_id: str = "", partition_by: str = "", scope: str = "", actor=None):
    """A new sheet, from a template or from columns; the owner's own act, one undo point."""
    from . import checkpoints, governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    base = TEMPLATES.get(template) if template else None
    if template and base is None:
        return _result(f"There is no template {template!r}.", {"status": "invalid"}, True)
    base = base or {}
    title = " ".join(str(title or base.get("title") or "").split())[:80]
    if not title:
        return _result("Give the sheet a name.", {"status": "invalid", "field": "title"}, True)
    wanted = sheet_id or (template if base.get("builtin") else util.slugify(title, 48))
    if not SLUG.match(wanted or ""):
        return _result("A sheet's id is lowercase words joined by hyphens.",
                       {"status": "invalid"}, True)
    if sheet(brain, wanted) is not None:
        return _result(f"There is already a sheet {wanted!r}.",
                       {"status": "exists", "id": wanted}, True)
    made = [Column(**asdict(c)) for c in base.get("columns", [])]
    for raw in columns or []:
        made.append(Column(**{k: v for k, v in dict(raw).items()
                              if k in Column.__dataclass_fields__}))
    key = key or base.get("key") or (made[0].name if made else "")
    problems = schema_problems(made, key, partition_by)
    if problems:
        return _result("Not made: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    found = Sheet(id=wanted, title=title, key=key, columns=made, partition_by=partition_by,
                  scope=scope or who, template=template, builtin=bool(base.get("builtin")),
                  description=str(base.get("description") or ""))
    with checkpoints.batch(brain, actor=who, label=f"Sheet: {title}") as batch:
        path = _save_schema(brain, found)
        snapshot = write_snapshot(brain, wanted)
        brain.after_write([path, snapshot], f"Sheet {wanted} made")
        batch.decisions.append({"action": "approved", "note": f"state/{wanted}",
                                "title": title})
    return _result(f"Sheet made: {title}.", {"status": "made", "sheet": found.to_dict(),
                                             "checkpoint": batch.checkpoint})


def ensure_tasks(brain, *, actor=None) -> Sheet:
    """The built-in Tasks sheet, made the first time it is needed."""
    found = sheet(brain, "tasks")
    if found is None:
        create_sheet(brain, template="tasks", actor=actor)
        found = sheet(brain, "tasks")
    assert found is not None
    return found


def add_column(brain, sheet_id: str, column: dict, *, actor=None):
    """A new column, a formula column included; the owner's act (an AI may only propose
    one)."""
    from . import governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    found = sheet(brain, sheet_id)
    if found is None:
        return _result(f"No sheet {sheet_id!r}.", {"status": "missing"}, True)
    new = Column(**{k: v for k, v in dict(column).items() if k in Column.__dataclass_fields__})
    problems = schema_problems(found.columns + [new], found.key, found.partition_by)
    if problems:
        return _result("Not added: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    found.columns.append(new)
    path = _save_schema(brain, found)
    snapshot = write_snapshot(brain, sheet_id)
    brain.after_write([path, snapshot], f"Sheet {sheet_id}: column {new.name} ({who})")
    return _result(f"Column added: {new.name}.",
                   {"status": "added", "sheet": found.to_dict()})


def find_row(brain, sheet_id: str, name: str, *, partitions=None) -> Row | None:
    wanted = " ".join(str(name or "").split()).lower()
    if not wanted:
        return None
    for row in rows(brain, sheet_id, partitions=partitions, with_computed=False):
        if wanted in (row.id, row.key.lower()) or wanted in (a.lower() for a in row.aliases):
            return row
    return None


def _regulated(brain) -> bool:
    from . import governance
    return governance.preset_of(brain.state().config) == "regulated"


def _cell_events(brain, found: Sheet, values: dict, *, who, said_by, source, session, ai,
                 at=None, as_of="", handoff=False) -> tuple[list[dict], list[str]]:
    events, problems = [], []
    regulated = ai and not handoff and _regulated(brain)
    for name, raw in values.items():
        column = found.column(name)
        if column is None:
            problems.append(f"{found.title} has no column {name!r}")
            continue
        if column.computed:
            problems.append(f"{column.name} is computed: nobody writes it")
            continue
        if found.id == "tasks" and column.name in HANDOFF_ONLY and not handoff:
            problems.append(f"{column.name} changes only through hand_off")
            continue
        if ai and column.friction == "locked" and not handoff:
            problems.append(f"{column.name} is the owner's alone: an AI cannot change it")
            continue
        value, why = _check_value(column, raw, brain)
        if why:
            problems.append(why)
            continue
        event = {"kind": "cell", "id": _event_id(), "at": at or util.now_iso(),
                 "column": column.name, "value": value, "by": who, "said_by": said_by,
                 "source": source, "session": session, "ai": ai}
        if as_of:
            event["as_of"] = as_of
        if ai and not handoff and (column.friction == "confirm" or regulated):
            event["pending"] = True
        events.append(event)
    return events, problems


def add_row(brain, sheet_id: str, key: str, values: dict | None = None, *, aliases=None,
            who: str, said_by: str = "owner", source: str = "app", session: str = "",
            ai: bool = False, row_id: str = "", handoff: bool = False):
    """A new row (one entity). Its first values follow the same rules as any write."""
    found = sheet(brain, sheet_id)
    if found is None:
        return _result(f"No sheet {sheet_id!r}.", {"status": "missing"}, True)
    key = " ".join(str(key or "").split())[:200]
    if not key:
        return _result(f"Name the row ({found.key}).", {"status": "invalid"}, True)
    if find_row(brain, sheet_id, key) is not None:
        return _result(f"{found.title} already has {key!r}.", {"status": "exists"}, True)
    row_id = row_id or util.slugify(key, 60) or _event_id()
    if os.path.exists(os.path.join(_folder(brain, sheet_id), f"{row_id}.jsonl")):
        row_id = f"{row_id}-{_event_id()[:4]}"
    at = util.now_iso()
    events = [{"kind": "row", "at": at, "key": key, "by": who, "said_by": said_by,
               "source": source, "session": session,
               "aliases": [" ".join(str(a).split()) for a in aliases or [] if str(a).strip()]},
              {"kind": "cell", "id": _event_id(), "at": at, "column": found.key,
               "value": key, "by": who, "said_by": said_by, "source": source,
               "session": session, "ai": ai}]
    cells, problems = _cell_events(brain, found, values or {}, who=who, said_by=said_by,
                                   source=source, session=session, ai=ai, at=at,
                                   handoff=handoff)
    if problems:
        return _result("Not added: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    _write(brain, sheet_id, row_id, events + cells, f"{found.title}: {key} added ({who})")
    return _result(f"Added {key}.", {"status": "added", "row": row_id, "key": key})


def write(brain, sheet_id: str, row_name: str, values: dict, *, who: str,
          said_by: str = "owner", source: str = "app", session: str = "", ai: bool = False,
          as_of: str = "", partitions=None, handoff: bool = False):
    """Cell writes on one row. A person's apply and are logged; an AI's apply on `free`
    columns (marked AI-filled), wait on `confirm` ones (and on all under regulated), and are
    refused on `locked` ones."""
    found = sheet(brain, sheet_id)
    if found is None:
        return _result(f"No sheet {sheet_id!r}.", {"status": "missing"}, True)
    row = find_row(brain, sheet_id, row_name, partitions=partitions)
    if row is None:
        return _result(f"{found.title} has no row {row_name!r}.", {"status": "missing"}, True)
    if as_of and util.parse_date(as_of) is None:
        return _result("as_of is a date (YYYY-MM-DD).", {"status": "invalid"}, True)
    events, problems = _cell_events(brain, found, values, who=who, said_by=said_by,
                                    source=source, session=session, ai=ai, as_of=as_of,
                                    handoff=handoff)
    if not events:
        return _result("Not written: " + "; ".join(problems or ["nothing to write"]) + ".",
                       {"status": "invalid", "problems": problems}, True)
    applied = [e for e in events if not e.get("pending")]
    waiting = [e for e in events if e.get("pending")]
    _write(brain, sheet_id, row.id, events,
           f"{found.title}: {row.key} ({', '.join(e['column'] for e in events)}) by {who}")
    words = []
    if applied:
        words.append(f"{len(applied)} written")
    if waiting:
        words.append(f"{len(waiting)} wait for the owner")
    if problems:
        words.append("refused: " + "; ".join(problems))
    return _result(f"{row.key}: " + ", ".join(words) + ".",
                   {"status": "written" if applied else "pending", "row": row.id,
                    "applied": [e["column"] for e in applied],
                    "pending": [{"column": e["column"], "event": e["id"]} for e in waiting],
                    "refused": problems})


def touch(brain, sheet_id: str, row_name: str, column: str, *, who: str):
    """A person keeps an AI-filled value as it is: it stops being marked."""
    row = find_row(brain, sheet_id, row_name)
    if row is None:
        return _result("No such row.", {"status": "missing"}, True)
    _write(brain, sheet_id, row.id, [{"kind": "touched", "at": util.now_iso(),
                                      "column": column, "by": who}],
           f"{sheet_id}: {row.key} {column} kept by {who}")
    return _result("Kept as it is.", {"status": "touched"})


def decide(brain, sheet_id: str, row_name: str, event_id: str, *, accept: bool, who: str):
    """The owner's tap on an AI's value that waits."""
    row = find_row(brain, sheet_id, row_name)
    if row is None or not any(e.get("id") == event_id for e in row.pending):
        return _result("That value is not waiting.", {"status": "missing"}, True)
    _write(brain, sheet_id, row.id, [{"kind": "confirmed" if accept else "declined",
                                      "event": event_id, "at": util.now_iso(), "by": who}],
           f"{sheet_id}: {row.key} value {'kept' if accept else 'turned down'} by {who}")
    return _result("Kept." if accept else "Turned down.", {"status": "decided"})


def remove_row(brain, sheet_id: str, row_name: str, *, who: str, reason: str = ""):
    row = find_row(brain, sheet_id, row_name)
    if row is None:
        return _result("No such row.", {"status": "missing"}, True)
    _write(brain, sheet_id, row.id, [{"kind": "removed", "at": util.now_iso(), "by": who,
                                      "reason": reason}],
           f"{sheet_id}: {row.key} removed by {who}")
    return _result(f"Removed {row.key}; its history stays.", {"status": "removed"})


def waiting(brain) -> list[dict]:
    """AI values waiting for the owner's tap, across sheets (for Catch up)."""
    out = []
    for item in sheets(brain):
        for row in rows(brain, item.id, with_computed=False):
            for event in row.pending:
                out.append({"sheet": item.id, "sheet_title": item.title, "row": row.key,
                            "column": event.get("column"), "value": event.get("value"),
                            "event": event.get("id"), "at": event.get("at"),
                            "source": event.get("source")})
    return out


# ---------------------------------------------------------------------- snapshot
def write_snapshot(brain, sheet_id: str) -> str:
    """`SNAPSHOT.md`: the sheet as a table, for people and git diffs. Returns its path."""
    found = sheet(brain, sheet_id)
    path = os.path.join(_folder(brain, sheet_id), "SNAPSHOT.md")
    if found is None:
        return path
    current = rows(brain, sheet_id)
    names = [c.name for c in found.columns]
    lines = [f"# {found.title}", "", "Generated from the sheet's cell logs; edit the sheet, "
             "not this file.", "", "| " + " | ".join(names) + " |",
             "| " + " | ".join("---" for _ in names) + " |"]
    for row in current:
        cells = []
        for column in found.columns:
            value = row.computed.get(column.name) if column.computed else row.value(column.name)
            cells.append(str("" if value is None else value).replace("|", "/")[:120])
        lines.append("| " + " | ".join(cells) + " |")
    brain.vault.touch(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    util.atomic_write(path, "\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------- briefs and reading
def _shown(found: Sheet, row: Row, column: Column) -> Any:
    return row.computed.get(column.name) if column.computed else row.value(column.name)


def row_lines(found: Sheet, row: Row, *, since: str = "") -> list[str]:
    lines = [f"**{found.title}: {row.key}**"]
    for column in found.columns:
        if column.name == found.key:
            continue
        if column.computed:
            value = row.computed.get(column.name)
            if value not in (None, ""):
                lines.append(f"- {column.name}: {value} (computed: "
                             f"{formulas.describe(column.formula)})")
            continue
        cell = row.cells.get(column.name)
        if cell is None or cell.value in (None, ""):
            continue
        marks = [f"as of {(cell.as_of or cell.at)[:10]}"]
        if cell.ai:
            marks.append("AI-filled")
        if cell.stale:
            marks.append("may be out of date")
        if since and cell.at >= since:
            marks.append("changed since this conversation last saw it")
        lines.append(f"- {column.name}: {cell.value} ({', '.join(marks)})")
    return lines


def named_rows(brain, request: str, *, partitions=None, limit: int = 3) -> list[tuple]:
    """(sheet, row) for each row whose key or alias the request names exactly."""
    text = " " + re.sub(r"[^\w\s-]", " ", str(request or "").lower()) + " "
    text = " ".join(text.split())
    text = f" {text} "
    found = []
    for item in sheets(brain):
        if item.id == "tasks":
            continue  # a task reaches a brief as its card (handoff.py), not as a row
        for row in rows(brain, item.id, partitions=partitions):
            # A key of three letters or more; an alias, given on purpose, from two.
            names = ([row.key] if len(row.key) >= 3 else []) + [a for a in row.aliases
                                                                if len(a) >= 2]
            if any(f" {' '.join(n.lower().split())} " in text for n in names):
                found.append((item, row))
    return found[:limit]


def brief_block(brain, request: str, *, partitions=None, since: str = "",
                extra: list[tuple] | None = None,
                held: dict | None = None) -> tuple[str, list[tuple]]:
    """The brief's "Current state" and the rows sent in it, as (sheet, row, digest): each
    named row's values, one line each with their dates, computed values marked, at most
    ROW_TOKENS a row. A row this conversation already holds unchanged (`held`: ref to
    {"hash", "at"}) comes as one line, not again in full; a changed one marks what changed
    since it was sent."""
    pairs = list(extra or [])
    for pair in named_rows(brain, request, partitions=partitions):
        if all(pair[1].id != p[1].id or pair[0].id != p[0].id for p in pairs):
            pairs.append(pair)
    if not pairs:
        return "", []
    blocks, shown = [], []
    for found, row in pairs:
        full = row_lines(found, row)
        digest = util.short_hash("\n".join(full), 12)
        before = (held or {}).get(f"{found.id}/{row.key}") or {}
        if before.get("hash") == digest:
            blocks.append(f"**{found.title}: {row.key}**: unchanged since this conversation "
                          "last saw it.")
            continue
        seen = str(before.get("at") or since or "")
        lines = row_lines(found, row, since=seen) if seen else full
        while util.tokens("\n".join(lines)) > ROW_TOKENS and len(lines) > 2:
            lines = lines[:-1]
        if len(lines) < len(full):
            lines.append("- (more with get_state)")
        blocks.append("\n".join(lines))
        shown.append((found, row, digest))
    return ("## Current state\n\nValues people and AIs keep current, dated, and marked when an "
            "AI filled them. A must-hold above wins over any value here.\n\n"
            + "\n\n".join(blocks)), shown


def get_state(brain, *, sheet_id: str = "", row: str = "", query: str = "",
              partitions=None) -> tuple[str, dict]:
    """What `get_state` returns: the sheets, one sheet's rows (filtered by words), or one row
    with its recent changes."""
    if not sheet_id:
        listed = sheets(brain)
        lines = [f"- `{s.id}` {s.title} (key: {s.key}; columns: "
                 f"{', '.join(c.name for c in s.columns)})" for s in listed]
        return ("State sheets:\n" + "\n".join(lines) if lines else "No State sheets yet.",
                {"sheets": [s.to_dict() for s in listed]})
    found = sheet(brain, sheet_id)
    if found is None:
        return f"No sheet {sheet_id!r}.", {"status": "missing"}
    current = rows(brain, sheet_id, partitions=partitions)
    if row:
        match = find_row(brain, sheet_id, row, partitions=partitions)
        full = next((r for r in current if match is not None and r.id == match.id), None)
        if full is None:
            return f"{found.title} has no row {row!r}.", {"status": "missing"}
        recent = [e for e in history(brain, sheet_id, full.id) if e.get("kind") == "cell"][:10]
        text = "\n".join(row_lines(found, full))
        if recent:
            text += "\n\nRecent changes:\n" + "\n".join(
                f"- {str(e.get('at'))[:16]} {e.get('column')}: {e.get('value')} "
                f"({e.get('by')}{', waits for the owner' if e.get('pending') else ''})"
                for e in recent)
        return text, {"row": full.to_dict(), "sheet": found.to_dict()}
    words = [w for w in str(query or "").lower().split() if w]
    if words:
        current = [r for r in current if all(
            any(w in str(v).lower() for v in [r.key, *r.aliases,
                                               *[c.value for c in r.cells.values()],
                                               *r.computed.values()]) for w in words)]
    lines = []
    for item in current[:25]:
        bits = []
        for column in found.columns:
            value = _shown(found, item, column)
            if column.name != found.key and value not in (None, ""):
                bits.append(f"{column.name}: {value}")
        lines.append(f"- {item.key}: " + "; ".join(bits))
    head = f"{found.title}: {len(current)} rows" + (f" matching {query!r}" if words else "")
    return head + ("\n" + "\n".join(lines) if lines else ""), {
        "sheet": found.to_dict(), "rows": [r.to_dict() for r in current],
        "summary": summary(found, current)}


def update_state(brain, updates: list, *, who: str, session: str = "", evidence: str = "",
                 partitions=None) -> tuple[str, dict]:
    """A batch of an AI's cell updates, each {sheet, row, column, value, as_of}. A row that
    does not exist yet is added with its key."""
    if not isinstance(updates, list) or not updates:
        return "Send updates as a list of {sheet, row, column, value}.", {"status": "invalid"}
    grouped: dict[tuple, dict] = {}
    for update in updates[:50]:
        if isinstance(update, dict):
            key = (str(update.get("sheet") or ""), str(update.get("row") or ""),
                   str(update.get("as_of") or ""))
            grouped.setdefault(key, {})[str(update.get("column") or "")] = update.get("value")
    source = ("chat: " + " ".join(str(evidence or "").split()))[:200] if evidence else "chat"
    lines, results = [], []
    for (sheet_id, row_name, as_of), values in grouped.items():
        found = sheet(brain, sheet_id)
        if found is None:
            lines.append(f"No sheet {sheet_id!r}; get_state lists them.")
            continue
        if find_row(brain, sheet_id, row_name, partitions=partitions) is None:
            made = add_row(brain, sheet_id, row_name, {}, who=who, said_by="owner-ai",
                           source=source, session=session, ai=True)
            if made.is_error:
                lines.append(made.text)
                results.append(made.data)
                continue
        done = write(brain, sheet_id, row_name, values, who=who, said_by="owner-ai",
                     source=source, session=session, ai=True, as_of=as_of,
                     partitions=partitions)
        lines.append(done.text)
        results.append(done.data)
    return "\n".join(lines), {"results": results}


# ---------------------------------------------------------------------- promotion
def promotions(brain, *, today: dt.date | None = None, settled_days: int = 180) -> list[dict]:
    """Suggestions only (8.7): a value unchanged for months could be a note; a note revised
    three or more times in 30 days could live in State."""
    today = today or util.today_date()
    out: list[dict] = []
    for item in sheets(brain):
        if item.builtin:
            continue
        for row in rows(brain, item.id, with_computed=False):
            for name, cell in row.cells.items():
                age = _age(cell.at, today)
                if name != item.key and not cell.ai and age is not None \
                        and age >= settled_days and str(cell.value or "").strip():
                    out.append({"kind": "to_note", "sheet": item.id, "row": row.key,
                                "column": name, "value": cell.value, "days": age})
    since = (today - dt.timedelta(days=30)).isoformat()
    revised: dict[str, int] = {}
    for record in brain.vault.decisions():
        if str(record.get("at") or "") >= since and record.get("action") == "edited" \
                and record.get("note"):
            revised[record["note"]] = revised.get(record["note"], 0) + 1
    for note_id, count in revised.items():
        if count >= 3 and brain.state().index.note(note_id) is not None:
            out.append({"kind": "to_state", "note": note_id, "revisions": count})
    return out
