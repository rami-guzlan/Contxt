"""The workspace before the Brain took over: what it held, written out as files, and the
context in it moved into the Brain.

Goals, to-dos, meetings, project memory, sheets, canvases and AI tasks are no longer shown,
and no table is dropped. `export` writes everything they hold to a folder anyone can read
without the app. `bring_into_brain` moves the context in them to where every AI finds it:

- each project becomes (or is matched to) a Brain project;
- its memories, kept or still suggested, become proposed notes in that project, waiting for
  the owner's review as one batch;
- meeting transcripts are filed into the project they fed, and documents and other material
  added to working context into the project they were added to;
- a project's open to-dos become its next steps, and every open to-do goes into one private
  note, by project, so none is out of sight (a to-do with no project has no other home).

Each part happens once: running it again skips what is already in.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso
from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, ValidationFailed
from workspace_core.ports import BrainProject

from .notes import Notes
from .runtime import Runtime

# The AI work the Brain still runs: distillation and reconciling a clash.
KEPT_TEMPLATES = ("distill", "reconcile")
# A memory's kind, as the Brain's proposals take it (a constraint or a risk is a fact).
MEMORY_KINDS = ("fact", "rule", "preference", "decision", "procedure", "identity")
MEMORY_STATES = ("kept", "suggested")
# Working context that is material for the Brain: filed there as documents.
MATERIAL = ("document", "file", "image", "audio", "note", "idea", "link")
NEXT_LIMIT = 900  # characters of carried-over to-dos in a project's next steps
TODO_NOTE = "Open to-dos from the earlier workspace"


def _slug(text: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug[:limit].rstrip("-") or "item"


def _name(text: str) -> str:
    """A project's name as matching compares it: words only, any case or separator."""
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _proposer(who: Principal) -> str:
    return f"{who.kind}:{who.name} ({who.actor_id})"


class Legacy:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    # ---------------------------------------------------------------- what is there

    def _rows(self, table: sa.Table, *where: Any) -> list[dict[str, Any]]:
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id, *where)
        with self.rt.read() as tx:
            return list(tx.rows(query))

    def _items(self, *kinds: str, live: bool = True) -> list[dict[str, Any]]:
        table = schema.context_items
        where = [table.c.kind.in_(kinds)]
        if live:
            where.append(table.c.archived_at.is_(None))
        rows = self._rows(table, *where)
        if "memory" in kinds and live:
            rows = [r for r in rows if r["kind"] != "memory" or r["memory_state"] in MEMORY_STATES]
        return sorted(rows, key=lambda r: (r["created_at"], r["id"]))

    def _state(self) -> dict[str, Any]:
        with self.rt.read() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        return dict((row["settings"] or {}).get("legacy") or {})

    def _save_state(self, state: dict[str, Any]) -> None:
        with self.rt.write() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            tx.update(schema.workspaces, row, {"settings": {**row["settings"], "legacy": state}})

    def offer(self, who: Principal) -> dict[str, Any] | None:
        """The one-time offer to bring the earlier workspace's context in: what it holds that
        the Brain does not, with a time estimate. None once it is in, or when nothing it holds
        would move."""
        if not who.can("workspace.admin") or not who.can("brain.govern"):
            return None
        summary = self.summary(who)
        if summary.get("moved_at"):
            return None
        counts = summary["counts"]
        parts = [
            (counts["memories"], "note", "notes"),
            (counts["transcripts"], "transcript", "transcripts"),
            (counts["documents"], "document", "documents"),
            (counts["todos_open"], "open to-do", "open to-dos"),
            (counts["projects_without_brain"], "project", "projects"),
        ]
        named = [f"{n} {one if n == 1 else many}" for n, one, many in parts if n]
        if not named:
            return None
        files = counts["transcripts"] + counts["documents"]
        seconds = 30 + 8 * counts["memories"] + 15 * files
        preset = str(self.rt.brain.policies().get("preset") or "careful")
        lead = named[0]
        verb = "is" if lead.startswith("1 ") else "are"
        said = [f"It holds {_and(named)}."] if len(named) > 1 else []
        if counts["memories"]:
            said.append("Notes come in as suggestions you keep or not.")
        if files:
            said.append(
                "Transcripts and documents wait in Review, each with its name."
                if preset in ("careful", "regulated")
                else "Transcripts and documents are filed at once."
            )
        if counts["todos_open"] or counts["projects_without_brain"]:
            said.append("Projects start at once, and open to-dos become their next steps.")
        return {
            "key": "legacy:workspace",
            "title": f"{lead} from your earlier workspace {verb} not in your Brain yet",
            "detail": " ".join(said),
            "counts": counts,
            "seconds": seconds,
            "minutes": max(1, -(-seconds // 60)),
        }

    def summary(self, who: Principal) -> dict[str, Any]:
        """How much the earlier workspace holds, and what has been done with it."""
        who.require("workspace.admin")
        todos = schema.todos
        tasks = schema.tasks
        open_todos = self._rows(todos, todos.c.status == "open", todos.c.archived_at.is_(None))
        done_todos = self._rows(todos, todos.c.status == "done", todos.c.archived_at.is_(None))
        ai_work = [
            t
            for t in self._rows(tasks, tasks.c.archived_at.is_(None))
            if (t["template"] or "") not in KEPT_TEMPLATES
        ]
        projects = self._rows(schema.projects, schema.projects.c.archived_at.is_(None))
        followed = {p.id for p in self.rt.brain.projects()}
        counts = {
            "goals": len(self._rows(schema.goals, schema.goals.c.archived_at.is_(None))),
            "todos_open": len(open_todos),
            "todos_done": len(done_todos),
            "meetings": len(self._rows(schema.meetings, schema.meetings.c.archived_at.is_(None))),
            "transcripts": len(self._items("transcript")),
            "memories": len(self._items("memory")),
            "documents": len(self._items(*MATERIAL)),
            "sheets": len(self._items("sheet", live=False)),
            "canvases": len(self._items("canvas", live=False)),
            "ai_work": len(ai_work),
            "projects": len(projects),
            "projects_without_brain": sum(1 for p in projects if p["brain_ref"] not in followed),
        }
        state = self._state()
        return {
            "counts": counts,
            "has_any": any(counts[k] for k in counts if k != "projects"),
            "exported_at": state.get("exported_at"),
            "export_dir": state.get("export_dir"),
            "moved_at": state.get("moved_at"),
            "moved": state.get("moved") or {},
        }

    # ---------------------------------------------------------------- export

    def export(self, who: Principal, out_dir: str) -> dict[str, Any]:
        """Write everything the earlier workspace holds into `out_dir`: JSON for each kind,
        Markdown where people read it (to-dos, memories, transcripts), sheets as CSV too,
        canvases as .excalidraw files, and every working item with its original file. Nothing
        in the workspace changes."""
        who.require("workspace.admin")
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        written: list[str] = []

        def write(relpath: str, data: str | bytes) -> None:
            path = os.path.join(out_dir, *relpath.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            mode = "wb" if isinstance(data, bytes) else "w"
            kwargs = {} if isinstance(data, bytes) else {"encoding": "utf-8", "newline": "\n"}
            with open(path, mode, **kwargs) as handle:  # type: ignore[call-overload]
                handle.write(data)
            written.append(relpath)

        def dump(relpath: str, rows: list[dict[str, Any]]) -> None:
            write(relpath, json.dumps(rows, indent=1, ensure_ascii=False, default=str) + "\n")

        def original(item: dict[str, Any]) -> bytes | None:
            key = item["object_key"]
            return self.rt.objects.read(key) if key and self.rt.objects.exists(key) else None

        projects = self._rows(schema.projects)
        names = {p["id"]: p["title"] for p in projects}
        dump("projects.json", projects)
        dump("goals.json", self._rows(schema.goals))
        todos = self._rows(schema.todos)
        dump("todos.json", todos)
        lines = ["# To-dos", ""]
        for project_id, group in _grouped(todos, "project_id").items():
            lines += [f"## {names.get(project_id, 'No project')}", ""]
            for t in sorted(group, key=lambda r: (r["status"] != "open", r["due_on"] or "")):
                due = f" (due {t['due_on']})" if t["due_on"] else ""
                owner = f", {t['owner']}" if t["owner"] else ""
                box = "x" if t["status"] == "done" else " "
                lines.append(f"- [{box}] {t['title']}{due}{owner} [{t['status']}]")
            lines.append("")
        write("todos.md", "\n".join(lines))
        dump("meetings.json", self._rows(schema.meetings))
        for item in self._items("transcript", live=False):
            stem = f"{_slug(item['title'])}-{item['id'][-6:].lower()}"
            text = item["text_shadow"] or item["body"] or ""
            if text:
                write(f"transcripts/{stem}.md", text)
            data = original(item)
            if data is not None:
                write(f"transcripts/originals/{stem}-{item['filename'] or 'original'}", data)
        memories = self._items("memory", live=False)
        dump("project-memory.json", memories)
        lines = ["# Project memory", ""]
        for project_id, group in _grouped(memories, "scope_id").items():
            lines += [f"## {names.get(project_id, 'No project')}", ""]
            for m in group:
                kind = ((m["provenance"] or {}).get("memory") or {}).get("kind") or "fact"
                state = "removed" if m["archived_at"] else m["memory_state"] or "kept"
                lines += [f"### {m['title']} ({kind}, {state})", "", m["body"].strip(), ""]
        write("project-memory.md", "\n".join(lines))
        for item in self._items("sheet", live=False):
            stem = f"{_slug(item['title'])}-{item['id'][-6:].lower()}"
            write(f"sheets/{stem}.json", item["body"] or "{}")
            write(f"sheets/{stem}.csv", _sheet_csv(item["body"]))
        for item in self._items("canvas", live=False):
            stem = f"{_slug(item['title'])}-{item['id'][-6:].lower()}"
            write(f"canvases/{stem}.excalidraw", _excalidraw(item["body"]))
        everything = self._rows(schema.context_items)
        dump(
            "working-context.json",
            [
                {k: v for k, v in r.items() if k not in ("body", "text_shadow")}
                | {"text": (r["body"] or r["text_shadow"] or "")[:200_000]}
                for r in everything
                if r["kind"] not in ("sheet", "canvas")
            ],
        )
        for item in everything:
            if item["kind"] in ("transcript", "sheet", "canvas", "memory"):
                continue
            data = original(item)
            if data is not None:
                name = item["filename"] or f"{_slug(item['title'])}.bin"
                write(f"files/{item['id'][-6:].lower()}-{name}", data)
        dump("ai-work.json", self._rows(schema.tasks))
        write(
            "README.md",
            "# The earlier workspace\n\n"
            "Everything the workspace held before it became a Brain app, as files: projects, "
            "goals, to-dos (also as a checklist in todos.md), meetings and their transcripts, "
            "project memory (also readable in project-memory.md), sheets (JSON and CSV), "
            "canvases (open them at excalidraw.com), every working item "
            "(working-context.json, with uploaded originals under files/) and AI work.\n",
        )
        state = self._state()
        state.update(exported_at=iso(self.rt.clock.now()), export_dir=out_dir)
        self._save_state(state)
        return {"dir": out_dir, "files": len(written), "written": written}

    # ---------------------------------------------------------------- into the Brain

    def bring_into_brain(self, who: Principal) -> dict[str, Any]:
        """Move the earlier workspace's context into the Brain (see the module docstring)."""
        who.require("workspace.admin")
        who.require("brain.govern")
        state = self._state()
        moved: dict[str, list[str]] = {
            k: list(v) for k, v in (state.get("moved") or {}).items() if isinstance(v, list)
        }
        report: dict[str, Any] = {
            "projects_started": [],
            "projects_matched": 0,
            "projects_left": [],  # could not be started, with why
            "notes_proposed": 0,
            "files_filed": 0,  # in the Brain at once
            "files_waiting": 0,  # waiting in Review (Careful and Regulated)
            "waiting_files": [],  # their names
            "next_steps": 0,
            "todos_noted": 0,  # open to-dos listed in the note
            "todo_note": None,  # that note's id
            "refused": [],  # what the Brain would not take, with why
            "skipped": 0,  # already in from an earlier run
        }
        homes = self._homes(who, report)
        self._memories(who, homes, moved, report)
        self._files(who, homes, moved, report)
        self._next_steps(who, homes, moved, report)
        state.update(moved=moved, moved_at=iso(self.rt.clock.now()))
        self._save_state(state)
        with self.rt.write() as tx:
            tx.emit(
                "workspace.legacy_moved",
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=self.rt.workspace_id,
                data={k: len(v) if isinstance(v, list) else v for k, v in report.items()},
            )
        return report

    def _homes(self, who: Principal, report: dict[str, Any]) -> dict[str, BrainProject]:
        """Each workspace project's Brain project: the one it points at, else one by the same
        name, else a new one."""
        brain = self.rt.brain
        followed = {p.id: p for p in brain.projects()}
        by_name: dict[str, BrainProject] = {}
        for project in followed.values():
            for name in (project.title, project.id, *project.aliases):
                by_name.setdefault(_name(name), project)
        homes: dict[str, BrainProject] = {}
        for row in self._rows(schema.projects, schema.projects.c.archived_at.is_(None)):
            home = followed.get(row["brain_ref"] or "")
            if home is not None:
                report["projects_matched"] += 1
            else:
                home = by_name.get(_name(row["title"]))
                if home is not None:
                    report["projects_matched"] += 1
                else:
                    try:
                        home = brain.create_project(
                            name=row["title"],
                            summary=row["summary"]
                            or f"{row['title']}, carried over from the workspace.",
                            aliases=[],
                            proposer=_proposer(who),
                        )
                    except (Conflict, ValidationFailed) as exc:
                        report["projects_left"].append({"title": row["title"], "why": str(exc)})
                        continue
                    report["projects_started"].append(home.title)
                    by_name[_name(home.title)] = home
                with self.rt.write() as tx:
                    current = tx.one(schema.projects, row["id"], "project")
                    tx.update(schema.projects, current, {"brain_ref": home.id})
            homes[row["id"]] = home
        fresh = {p.id: p for p in brain.projects()}
        return {key: fresh.get(home.id, home) for key, home in homes.items()}

    def _memories(
        self,
        who: Principal,
        homes: dict[str, BrainProject],
        moved: dict[str, list[str]],
        report: dict[str, Any],
    ) -> None:
        """Kept and suggested memories, proposed as notes in their project's topic."""
        done = set(moved.get("memories", []))
        for item in self._items("memory"):
            if item["id"] in done:
                report["skipped"] += 1
                continue
            meta = (item["provenance"] or {}).get("memory") or {}
            kind = str(meta.get("kind") or "fact")
            home = homes.get(item["scope_id"] or "")
            kept = item["memory_state"] == "kept"
            made = self.rt.brain.propose(
                title=item["title"],
                statement=item["body"],
                kind=kind if kind in MEMORY_KINDS else "fact",
                scope=None,
                evidence=str(meta.get("evidence") or "")
                or (
                    "Kept in the workspace's project memory."
                    if kept
                    else "Suggested for the workspace's project memory, not yet kept."
                ),
                sources=[f"workspace memory {item['id']}"],
                proposer=_proposer(who),
                topic=home.topic if home is not None and home.topic else None,
                origin=f"workspace:{item['id']}",
                # A kept memory is the owner's word; one only suggested is their AI's.
                extra={"said_by": "owner" if kept else "owner-ai"},
            )
            if made.status in ("pending", "applied", "duplicate"):
                report["notes_proposed"] += made.status != "duplicate"
                done.add(item["id"])
            else:
                report["refused"].append({"title": item["title"], "why": made.message})
        moved["memories"] = sorted(done)

    def _files(
        self,
        who: Principal,
        homes: dict[str, BrainProject],
        moved: dict[str, list[str]],
        report: dict[str, Any],
    ) -> None:
        """Transcripts into the project their meeting fed; documents and other material into
        the project they were added to."""
        meetings = {m["item_id"]: m for m in self._rows(schema.meetings)}
        tasks = {t["id"]: t["project_id"] for t in self._rows(schema.tasks)}
        fed: dict[str, Counter[str]] = {}
        for item in self._items("memory", live=False):
            meeting_id = ((item["provenance"] or {}).get("memory") or {}).get("meeting_id")
            if meeting_id and item["scope_id"]:
                fed.setdefault(str(meeting_id), Counter())[item["scope_id"]] += 1
        done = set(moved.get("transcripts", [])) | set(moved.get("documents", []))
        filed: dict[str, list[str]] = {"transcripts": [], "documents": []}
        # A whole workspace's files were never picked one by one: under Careful and Regulated
        # each waits in Review with its name, so nothing confidential becomes quotable unseen.
        preset = str(self.rt.brain.policies().get("preset") or "careful")
        wait = preset in ("careful", "regulated")
        for item in self._items("transcript", *MATERIAL):
            if item["id"] in done:
                report["skipped"] += 1
                continue
            home = None
            description = ""
            if item["kind"] == "transcript":
                meeting = meetings.get(item["id"])
                projects = fed.get(meeting["id"], Counter()) if meeting else Counter()
                home = homes.get(projects.most_common(1)[0][0]) if projects else None
                if meeting is not None and meeting["project_id"]:
                    home = homes.get(meeting["project_id"], home)
                held = meeting["held_on"] if meeting and meeting["held_on"] else ""
                title = f"{item['title']} ({held})" if held else item["title"]
                description = "Transcript of a meeting" + (f" held {held}." if held else ".")
            else:
                project = (
                    item["scope_id"]
                    if item["scope_kind"] == "project"
                    else tasks.get(item["scope_id"] or "")
                    if item["scope_kind"] == "task"
                    else None
                )
                home = homes.get(project or "")
                # An upload named only by its file name gets the Brain's own title for it.
                title = "" if item["title"] == (item["filename"] or "") else item["title"]
            filename, data = self._material(item)
            if not data:
                continue
            made = self.rt.brain.add_file(
                filename=filename,
                data=data,
                title=title,
                description=description,
                topic=None,
                proposer=_proposer(who),
                project=home.id if home is not None else None,
                origin="app",
                wait=wait,
                came_from="movein",
            )
            if made.status in ("applied", "pending", "duplicate"):
                if made.status == "applied":
                    report["files_filed"] += 1
                elif made.status == "pending":
                    report["files_waiting"] += 1
                    report["waiting_files"].append(title or filename)
                filed["transcripts" if item["kind"] == "transcript" else "documents"].append(
                    item["id"]
                )
            else:
                report["refused"].append({"title": title or filename, "why": made.message})
        for key, ids in filed.items():
            moved[key] = sorted({*moved.get(key, []), *ids})

    def _material(self, item: dict[str, Any]) -> tuple[str, bytes]:
        """A working item as a file for the Brain: its original upload, else its text as
        Markdown (a link keeps its address)."""
        key = item["object_key"]
        if key and self.rt.objects.exists(key):
            return item["filename"] or f"{_slug(item['title'])}.bin", self.rt.objects.read(key)
        text = (item["text_shadow"] or item["body"] or "").strip()
        if item["url"]:
            text = f"{item['url']}\n\n{text}".strip()
        if not text:
            return "", b""
        if item["kind"] == "transcript":
            return item["filename"] or f"{_slug(item['title'])}.md", text.encode("utf-8")
        return f"{_slug(item['title'])}.md", f"# {item['title']}\n\n{text}\n".encode()

    def _next_steps(
        self,
        who: Principal,
        homes: dict[str, BrainProject],
        moved: dict[str, list[str]],
        report: dict[str, Any],
    ) -> None:
        """A project's open to-dos, added to its next steps (soonest due first); and every
        open to-do in one note, by project."""
        todos = schema.todos
        open_todos = self._rows(todos, todos.c.status == "open", todos.c.archived_at.is_(None))
        open_todos.sort(key=lambda r: (r["due_on"] or "9999", r["created_at"]))
        done = set(moved.get("todos", []))
        for project_id, group in _grouped(open_todos, "project_id").items():
            home = homes.get(project_id or "")
            if home is None or project_id in done:
                continue
            steps: list[str] = []
            for t in group:
                step = _todo_line(t)
                if len("; ".join([*steps, step])) > NEXT_LIMIT:
                    break
                steps.append(step)
            rest = len(group) - len(steps)
            text = "; ".join(steps) + (
                f"; and {rest} more in the note “{TODO_NOTE}”" if rest else ""
            )
            changes = {"next": f"{home.next}; {text}" if home.next else text}
            if home.current:
                # An update without "current" would make its own line where the project stands.
                changes["current"] = home.current
            try:
                self.rt.brain.project_update(
                    home.id,
                    summary=f"Open to-dos carried over from the workspace ({len(group)})",
                    changes=changes,
                    evidence="the workspace's to-do list",
                )
            except (Conflict, NotFound, ValidationFailed) as exc:
                report["refused"].append({"title": f"Next steps for {home.title}", "why": str(exc)})
                continue
            report["next_steps"] += len(group)
            done.add(project_id)
        moved["todos"] = sorted(done)
        if open_todos and not moved.get("todo_note"):
            note = Notes(self.rt).create(who, title=TODO_NOTE, body=self._todo_note(open_todos))
            moved["todo_note"] = [note.id]
            report["todos_noted"] = len(open_todos)
        noted = moved.get("todo_note") or []
        report["todo_note"] = noted[0] if noted else None

    def _todo_note(self, open_todos: list[dict[str, Any]]) -> str:
        """Every open to-do as a checklist, by project, the ones with no project last."""
        names = {p["id"]: p["title"] for p in self._rows(schema.projects)}
        groups = _grouped(open_todos, "project_id")
        order = sorted(groups, key=lambda p: (p is None, names.get(p or "", "")))
        lines = [
            f"Carried over on {iso(self.rt.clock.now())[:10]}. The ones in a project are also "
            "that project's next steps in the Brain.",
            "",
        ]
        for project_id in order:
            lines += [f"## {names.get(project_id or '', 'No project')}", ""]
            lines += [f"- [ ] {_todo_line(t)}" for t in groups[project_id]]
            lines.append("")
        return "\n".join(lines)


def _and(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _todo_line(todo: dict[str, Any]) -> str:
    """A to-do in a line: what, when it is due, and whose it is."""
    return (
        todo["title"]
        + (f" (due {todo['due_on']})" if todo["due_on"] else "")
        + (f", {todo['owner']}" if todo["owner"] else "")
    )


def _grouped(rows: list[dict[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    out: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row[key], []).append(row)
    return out


def _sheet_csv(body: str | None) -> str:
    """A sheet's rows as CSV, by its columns' names; values as they were typed."""
    try:
        data = json.loads(body or "{}")
    except ValueError:
        return ""
    columns = [c for c in data.get("columns") or [] if isinstance(c, dict)]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([c.get("name") or c.get("id") for c in columns])
    for row in data.get("rows") or []:
        cells = (row or {}).get("cells") or {}
        writer.writerow(
            ["" if cells.get(c.get("id")) is None else cells.get(c.get("id")) for c in columns]
        )
    return buffer.getvalue()


def _excalidraw(body: str | None) -> str:
    try:
        data = json.loads(body or "{}")
    except ValueError:
        data = {}
    return json.dumps(
        {
            "type": "excalidraw",
            "version": 2,
            "source": "local-ai-workspace",
            "elements": data.get("elements") or [],
            "appState": data.get("appState") or {},
            "files": data.get("files") or {},
        },
        indent=1,
    )
