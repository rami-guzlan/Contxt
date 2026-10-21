"""Sheets the Brain keeps by itself (Release 1 plan, M11): read from what it already holds,
worked out when read, never written, so they can never disagree with their source.

    project-status   one row per active project: its status, latest update, what is next,
                     and how many days it has been quiet
    open-loops       the open tasks due within a week, or overdue, with who owns them
"""
from __future__ import annotations

import datetime as dt

from . import util
from .scopes import Scopes

VIEWS = {"project-status": "Project status", "open-loops": "Open loops this week"}
CLOSED = ("done", "dropped")
WEEK = 7


def _days(stamp, today: dt.date) -> int | None:
    found = util.parse_date(str(stamp or "")[:10])
    return (today - found).days if found else None


def project_status(st, chain, partitions=(), today: dt.date | None = None) -> list[dict]:
    today = today or util.today_date()
    rows = []
    for focus in st.index.focuses.values():
        if not focus.active or not Scopes.admits(focus.note.scope, focus.note.partition,
                                                 chain, partitions):
            continue
        now = focus.current()
        latest = focus.updates[-1].summary if focus.updates else ""
        updated = now.get("updated") or focus.note.meta.get("added")
        rows.append({"Project": focus.title, "Status": now.get("status") or "active",
                     "Latest": latest or str(now.get("current") or ""),
                     "Next up": str(now.get("next") or ""),
                     "Days quiet": _days(updated, today), "id": focus.id})
    rows.sort(key=lambda r: (-(r["Days quiet"] or 0), r["Project"]))
    return rows


def open_loops(brain, partitions=None, today: dt.date | None = None) -> list[dict]:
    from . import state
    today = today or util.today_date()
    until = today + dt.timedelta(days=WEEK)
    out = []
    for row in state.rows(brain, "tasks", partitions=partitions, today=today):
        status = str(row.value("Status") or "open")
        due = util.parse_date(str(row.value("Due") or ""))
        if status in CLOSED or due is None or due > until:
            continue
        out.append({"Task": str(row.value("Task") or row.key), "Owner":
                    str(row.value("Owner") or ""), "Due": due.isoformat(), "Status": status,
                    "Project": str(row.value("Project") or ""), "Overdue": due < today,
                    "id": row.id})
    out.sort(key=lambda r: (r["Due"], r["Task"]))
    return out


def view(brain, name, chain, partitions=()) -> tuple[str, dict]:
    """One derived sheet, as text and rows."""
    st = brain.state()
    if name == "project-status":
        rows = project_status(st, chain, partitions)
        lines = [f"- {r['Project']} [{r['Status']}]: {r['Latest'] or 'no update yet'}"
                 + (f"; next: {r['Next up']}" if r["Next up"] else "")
                 + (f"; quiet {r['Days quiet']} days" if r["Days quiet"] else "")
                 for r in rows]
    else:
        rows = open_loops(brain, list(partitions) if partitions else None)
        lines = [f"- {r['Task']} ({r['Owner'] or 'no owner'}), due {r['Due']}"
                 + (" (overdue)" if r["Overdue"] else "") for r in rows]
    title = VIEWS[name]
    text = f"# {title} (kept by the Brain, worked out now)\n\n" + (
        "\n".join(lines) if lines else "Nothing here right now.")
    return text, {"sheet": name, "title": title, "derived": True, "rows": rows}
