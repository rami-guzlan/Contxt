"""Goals and Projects (goals plan G1): the goal ladder from the Brain, and what the app keeps
beside it.

The Brain keeps the goals themselves (brainkit/ladder.py): goal notes, their journals, their
checks and each goal's shared plan file. The workspace keeps presentation: each goal's strategy
board (its blocks in order, one or two columns, which are collapsed, and which your AIs can
read) and the suggestions waiting for it, with the ones you said no to remembered so they never
come back. Saving a board writes its shared blocks to the goal's plan file, so every AI reads
the same text; private blocks never leave this database.

The goal coach: a short conversation on the model you chose, as a background job (at most
three questions, then a draft goal with at most three first steps, every field editable before
it is saved). Without a model, the same draft comes from the form.

Goals are optional. Without one of yours, the projects page stays Projects, and nothing else
about goals shows anywhere (`has_goals`).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import parse_iso
from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import ValidationFailed

from .runtime import Runtime

CALLS = ("on_track", "at_risk", "off_track")
CADENCES = ("daily", "weekly", "monthly")
# The sheet block waits for State sheets (build step 6).
BLOCK_TYPES = ("note", "checklist", "doc", "projects", "links", "decisions")
MAX_BLOCKS = 24
MAX_TEXT = 8000
MAX_ITEMS = 50
MAX_SUGGESTIONS = 40
MAX_TITLE = 120
MAX_COACH_TURNS = 8
MAX_STEPS = 3
WEEKLY_REVIEW_DAY = 4  # Friday
# The board templates (plan 6.3): the plan blocks start shared, so every AI reads the plan.
TEMPLATES: dict[str, dict[str, Any]] = {
    "plan": {
        "label": "Plan it",
        "blocks": [
            ("note", "Wish and outcome", True),
            ("note", "Obstacles and plan", True),
            ("checklist", "Key results", True),
        ],
    },
    "launch": {
        "label": "Launch",
        "blocks": [("checklist", "Milestones", True), ("projects", "Projects", True)],
    },
    "grow": {
        "label": "Grow a number",
        "blocks": [
            ("note", "The number and what moves it", True),
            ("checklist", "Experiments", True),
        ],
    },
    "blank": {"label": "Blank", "blocks": []},
}

COACH = """You are the goal coach in the owner's Brain app. You help them set ONE goal by
talking it through, the way mental contrasting works: what they want, the best outcome, what
usually gets in the way, and the plan for when it does.

Rules:
- Ask at most three short questions, all in one turn, and only when the answer is not already
  in the conversation. Never ask a second round.
- Then write the draft goal. Use their own words. Never invent numbers, dates or names they
  did not give.
- At most three first steps, each one short action.
- A measure is optional. Use {{"kind": "enter", "target": <number>, "unit": "<unit>"}} only
  when they named a number to reach; otherwise leave it out.
- Due is a date (YYYY-MM-DD) only when they named one.
- No em dashes or en dashes.

Their projects (link one only if it clearly serves the goal): {projects}

Answer with ONE JSON object only, either
{{"questions": ["...", "..."]}}
or
{{"draft": {{"title": "...", "why": "...", "due": "YYYY-MM-DD or empty",
  "cadence": "weekly", "measure": null, "board": {{"wish": "...", "outcome": "...",
  "obstacle": "...", "plan": "..."}}, "first_steps": ["..."], "project": "a project id or
  empty"}}}}

The conversation so far:
{conversation}
"""


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _same(a: str, b: str) -> bool:
    words = re.compile(r"[^a-z0-9]+")
    return words.sub(" ", a.lower()).strip() == words.sub(" ", b.lower()).strip()


def _block(kind: str, title: str, shared: bool, **content: Any) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:10],
        "type": kind,
        "title": title,
        "shared": shared,
        "collapsed": False,
        "column": 0,
        **content,
    }


def template(name: str) -> dict[str, Any]:
    """A board from one of the templates, empty."""
    found = TEMPLATES.get(name) or TEMPLATES["plan"]
    return {
        "columns": 2 if name != "blank" else 1,
        "template": name if name in TEMPLATES else "plan",
        "blocks": [
            dict(_block(kind, title, shared), column=i % 2)
            for i, (kind, title, shared) in enumerate(found["blocks"])
        ],
    }


def clean_layout(layout: Any) -> dict[str, Any]:
    """A board as the owner saved it, checked: known block types, bounded text, a column of
    0 or 1, items with text."""
    if not isinstance(layout, dict):
        raise ValidationFailed("A board is an object with blocks.", field="layout")
    blocks = layout.get("blocks") or []
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise ValidationFailed(f"A board holds at most {MAX_BLOCKS} blocks.", field="blocks")
    columns = 2 if layout.get("columns") == 2 else 1
    out = []
    seen: set[str] = set()
    for raw in blocks:
        if not isinstance(raw, dict) or raw.get("type") not in BLOCK_TYPES:
            raise ValidationFailed(f"A block is one of {', '.join(BLOCK_TYPES)}.", field="blocks")
        ident = _clip(raw.get("id"), 40) or uuid.uuid4().hex[:10]
        if ident in seen:
            ident = uuid.uuid4().hex[:10]
        seen.add(ident)
        block: dict[str, Any] = {
            "id": ident,
            "type": raw["type"],
            "title": _clip(raw.get("title"), MAX_TITLE) or "Untitled",
            "shared": bool(raw.get("shared")),
            "collapsed": bool(raw.get("collapsed")),
            "column": 1 if columns == 2 and raw.get("column") == 1 else 0,
        }
        if raw["type"] == "note":
            block["text"] = _text(raw.get("text"))
        elif raw["type"] == "checklist":
            items = [
                {"text": _clip(i.get("text"), 300), "done": bool(i.get("done"))}
                for i in (raw.get("items") or [])[:MAX_ITEMS]
                if isinstance(i, dict) and _clip(i.get("text"), 300)
            ]
            block["items"] = items
        elif raw["type"] == "doc":
            block["doc_id"] = _clip(raw.get("doc_id"), 60)
            block["doc_title"] = _clip(raw.get("doc_title"), 200)
        elif raw["type"] == "links":
            block["links"] = [
                {"title": _clip(i.get("title"), 200), "url": _clip(i.get("url"), 1000)}
                for i in (raw.get("links") or [])[:MAX_ITEMS]
                if isinstance(i, dict) and (_clip(i.get("url"), 1000) or _clip(i.get("title"), 200))
            ]
        out.append(block)
    return {"columns": columns, "template": _clip(layout.get("template"), 20), "blocks": out}


def render(block: dict[str, Any], goal: dict[str, Any]) -> str:
    """A shared block as the text every AI reads in the plan file."""
    kind = block["type"]
    if kind == "note":
        return str(block.get("text") or "")
    if kind == "checklist":
        return "\n".join(
            f"- [{'x' if i.get('done') else ' '}] {i['text']}" for i in block.get("items") or []
        )
    if kind == "doc":
        title = block.get("doc_title") or "a Workspace doc"
        return f"Doc: {title}" + (f" (`{block['doc_id']}`)" if block.get("doc_id") else "")
    if kind == "projects":
        return "\n".join(f"- {p['title']} (`{p['id']}`)" for p in goal.get("projects") or [])
    if kind == "links":
        return "\n".join(
            f"- {link['title'] or link['url']}" + (f": {link['url']}" if link["url"] else "")
            for link in block.get("links") or []
        )
    if kind == "decisions":
        return "\n".join(
            f"- {str(e.get('at') or '')[:10]}: {e.get('text')}"
            for e in goal.get("journal") or []
            if e.get("kind") == "decision"
        )
    return ""


def read_coach(answer: str) -> dict[str, Any]:
    """The coach's answer: {"questions"} or {"draft"}, checked and clipped. An answer that is
    neither says so, so the person can use the form."""
    found: Any = None
    for match in re.finditer(r"\{.*\}", answer or "", re.DOTALL):
        try:
            found = json.loads(match.group(0))
            break
        except ValueError:
            continue
    if not isinstance(found, dict):
        return {"error": "The coach did not answer in a way the app can read. Use the form."}
    questions = [_clip(q, 300) for q in found.get("questions") or [] if _clip(q, 300)]
    if questions and not found.get("draft"):
        return {"questions": questions[:3]}
    raw = found.get("draft")
    if not isinstance(raw, dict) or not _clip(raw.get("title"), 160):
        return {"error": "The coach did not write a draft the app can read. Use the form."}
    found_board = raw.get("board")
    board: dict[str, Any] = found_board if isinstance(found_board, dict) else {}
    measure = raw.get("measure") if isinstance(raw.get("measure"), dict) else None
    if measure and measure.get("kind") != "enter":
        measure = None
    due = _clip(raw.get("due"), 10)
    try:
        datetime.strptime(due, "%Y-%m-%d")
    except ValueError:
        due = ""
    return {
        "draft": {
            "title": _clip(raw.get("title"), 160),
            "why": _clip(raw.get("why"), 600),
            "due": due,
            "cadence": raw.get("cadence") if raw.get("cadence") in CADENCES else "weekly",
            "measure": measure,
            "board": {
                k: _text(board.get(k), 2000) for k in ("wish", "outcome", "obstacle", "plan")
            },
            "first_steps": [_clip(s, 200) for s in (raw.get("first_steps") or []) if _clip(s, 200)][
                :MAX_STEPS
            ],
            "project": _clip(raw.get("project"), 200),
        }
    }


class Goals:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    # ---------------------------------------------------------------- reading

    def ladder(self, who: Principal, *, with_signals: bool = False) -> dict[str, Any]:
        """The ladder for Goals and Projects and Settings > Alignment, each of your goals with
        how many suggestions wait for it; the signal library too `with_signals`."""
        who.require("brain.read")
        found = self.rt.brain.ladder(with_signals=with_signals)
        waiting = self._waiting_counts()
        for goal in found.get("yours") or []:
            goal["suggestions"] = waiting.get(goal["id"], 0)
        return found

    def rules(self, who: Principal) -> dict[str, Any]:
        """What every AI is told (Settings > Alignment, Rules): the startup context with its
        layers and budget, the must-holds by domain, and the interview's "how" and "never"."""
        who.require("brain.read")
        found = self.rt.brain.ladder()
        return {
            "kernel": self.rt.brain.kernel(tools=True),
            "must_holds": found.get("must_holds") or [],
            "answers": (found.get("purpose") or {}).get("rules") or {},
        }

    def get(self, who: Principal, goal_id: str) -> dict[str, Any]:
        """A goal's page: the goal, its checks and journal, its board, the suggestions waiting
        for it, and what an AI receives for it."""
        who.require("brain.read")
        found = self.rt.brain.goal(goal_id)
        row = self._row(goal_id)
        found["board"] = self._board(row, found)
        found["suggestions"] = [
            s for s in (row["suggestions"] if row else []) if s.get("status") == "waiting"
        ]
        found["templates"] = [{"id": k, "label": v["label"]} for k, v in TEMPLATES.items()]
        return found

    def _row(self, goal_id: str) -> dict[str, Any] | None:
        table = schema.goal_boards
        with self.rt.read() as tx:
            return tx.first(
                sa.select(table).where(
                    table.c.workspace_id == self.rt.workspace_id, table.c.goal_id == goal_id
                )
            )

    def _board(self, row: dict[str, Any] | None, goal: dict[str, Any]) -> dict[str, Any]:
        if row is None:
            board = template("plan")
            board["version"] = 0
            return board
        return dict(row["layout"], version=row["version"])

    def _waiting_counts(self) -> dict[str, int]:
        table = schema.goal_boards
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table.c.goal_id, table.c.suggestions).where(
                    table.c.workspace_id == self.rt.workspace_id
                )
            )
        return {
            r["goal_id"]: sum(1 for s in r["suggestions"] or [] if s.get("status") == "waiting")
            for r in rows
        }

    # ---------------------------------------------------------------- setting and changing

    def set(self, who: Principal, fields: dict[str, Any]) -> dict[str, Any]:
        """Set a goal (the coach's draft or the form), with its board from a template filled
        with the coach's words, and its first steps as suggestions."""
        who.require("brain.govern")
        wanted = {
            k: fields[k]
            for k in ("title", "why", "level", "kept_by", "measure", "due", "cadence", "serves")
            if fields.get(k) not in (None, "")
        }
        made = self.rt.brain.act_goal("set", "", wanted)
        goal = made["goal"]
        board = template(str(fields.get("template") or "plan"))
        given = fields.get("board")
        words: dict[str, Any] = given if isinstance(given, dict) else {}
        for block in board["blocks"]:
            if block["title"] == "Wish and outcome":
                block["text"] = "\n\n".join(
                    _text(words.get(k), 2000) for k in ("wish", "outcome") if words.get(k)
                )
            elif block["title"] == "Obstacles and plan":
                parts = []
                if words.get("obstacle"):
                    parts.append("What gets in the way: " + _text(words["obstacle"], 2000))
                if words.get("plan"):
                    parts.append("If it happens: " + _text(words["plan"], 2000))
                block["text"] = "\n\n".join(parts)
        steps = [_clip(s, 200) for s in fields.get("first_steps") or [] if _clip(s, 200)]
        self._save(who, goal["id"], board, None, goal)
        for step in steps[:MAX_STEPS]:
            self.suggest(who, goal["id"], step, source="goal coach")
        project = _clip(fields.get("project"), 200)
        if project and any(p.id == project for p in self.rt.brain.projects()):
            self.rt.brain.act_goal("link", goal["id"], {"project": project})
        with self.rt.write() as tx:
            tx.emit(
                "goal.added",
                actor_id=who.actor_id,
                subject_type="goal",
                subject_id=goal["id"],
                data={"title": goal["title"], "level": goal["level"]},
            )
        return self.get(who, goal["id"])

    def link(
        self, who: Principal, goal_id: str, project_id: str, *, linked: bool = True
    ) -> dict[str, Any]:
        """Link a project to the goal it serves, or unlink it."""
        who.require("brain.govern")
        self.rt.brain.act_goal("link", goal_id, {"project": project_id, "linked": linked})
        return self.get(who, goal_id)

    def change(
        self, who: Principal, goal_id: str, changes: dict[str, Any], reason: str = ""
    ) -> dict[str, Any]:
        who.require("brain.govern")
        self.rt.brain.act_goal("change", goal_id, {"changes": changes, "reason": reason})
        return self.get(who, goal_id)

    def check_in(
        self,
        who: Principal,
        goal_id: str,
        *,
        call: str,
        value: float | None = None,
        line: str = "",
    ) -> dict[str, Any]:
        """Your check-in: the call, the number when the goal tracks one, and a line."""
        who.require("brain.govern")
        if call not in CALLS:
            raise ValidationFailed("Say how it is going.", field="call")
        done = self.rt.brain.act_goal(
            "check_in", goal_id, {"call": call, "value": value, "line": line}
        )
        with self.rt.write() as tx:
            tx.emit(
                "goal.checked_in",
                actor_id=who.actor_id,
                subject_type="goal",
                subject_id=goal_id,
                data={"call": call, "value": value},
            )
        return dict(done["goal"])

    def decide(self, who: Principal, goal_id: str, text: str) -> dict[str, Any]:
        """A decision recorded on the goal (its Decisions block)."""
        who.require("brain.govern")
        self.rt.brain.act_goal("note", goal_id, {"text": text, "kind": "decision"})
        with self.rt.write() as tx:
            tx.emit(
                "goal.note_added",
                actor_id=who.actor_id,
                subject_type="goal",
                subject_id=goal_id,
                data={"kind": "decision"},
            )
        return self.get(who, goal_id)

    def starters(self, who: Principal) -> dict[str, Any]:
        """The knowledge agent's four goals, in one tap."""
        who.require("brain.govern")
        self.rt.brain.act_goal("starters")
        return self.ladder(who)

    def run_checks(self, who: Principal, *, force: bool = False) -> list[dict[str, Any]]:
        """The computed checks, now (the worker runs them on their cadence)."""
        who.require("brain.read")
        found = list(self.rt.brain.act_goal("check", "", {"force": force}).get("checks") or [])
        if found:
            with self.rt.write() as tx:
                for check in found:
                    tx.emit(
                        "goal.checked",
                        actor_id=who.actor_id,
                        subject_type="goal",
                        subject_id=check["goal"],
                        data={"status": check["status"], "card": check["card"]},
                        noise=not check["card"],
                    )
        return found

    # ---------------------------------------------------------------- the board

    def save_board(
        self,
        who: Principal,
        goal_id: str,
        layout: Any,
        *,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """Save the board, and write its shared blocks to the goal's plan file."""
        who.require("brain.govern")
        goal = self.rt.brain.goal(goal_id)
        board = clean_layout(layout)
        self._save(who, goal_id, board, expected_version, goal)
        return self.get(who, goal_id)

    def _save(
        self,
        who: Principal,
        goal_id: str,
        board: dict[str, Any],
        expected_version: int | None,
        goal: dict[str, Any],
    ) -> None:
        table = schema.goal_boards
        with self.rt.write() as tx:
            row = tx.first(
                sa.select(table).where(
                    table.c.workspace_id == self.rt.workspace_id, table.c.goal_id == goal_id
                )
            )
            if row is None:
                tx.insert(
                    table,
                    {
                        "id": tx.new_id("gbd"),
                        "workspace_id": self.rt.workspace_id,
                        "goal_id": goal_id,
                        "kind": "goal",
                        "layout": board,
                        "suggestions": [],
                        "created_by": who.actor_id,
                        "created_at": tx.now,
                        "updated_at": tx.now,
                        "version": 1,
                    },
                )
            else:
                tx.update(table, row, {"layout": board}, expected_version=expected_version or None)
        # Only shared blocks ever reach the vault, so only they reach a brief.
        shared = [
            {"title": b["title"], "text": render(b, goal)}
            for b in board["blocks"]
            if b.get("shared")
        ]
        self.rt.brain.act_goal("plan", goal_id, {"blocks": shared})

    # ---------------------------------------------------------------- suggestions

    def suggest(self, who: Principal, goal_id: str, text: str, *, source: str) -> bool:
        """A suggested next step for one of your goals. One you said no to never comes back,
        and one already waiting is not added twice."""
        who.require("brain.read")
        text = _clip(text, 300)
        if not text:
            return False
        table = schema.goal_boards
        with self.rt.write() as tx:
            row = tx.first(
                sa.select(table).where(
                    table.c.workspace_id == self.rt.workspace_id, table.c.goal_id == goal_id
                )
            )
            if row is None:
                board = template("plan")
                row = tx.insert(
                    table,
                    {
                        "id": tx.new_id("gbd"),
                        "workspace_id": self.rt.workspace_id,
                        "goal_id": goal_id,
                        "kind": "goal",
                        "layout": board,
                        "suggestions": [],
                        "created_by": who.actor_id,
                        "created_at": tx.now,
                        "updated_at": tx.now,
                        "version": 1,
                    },
                )
            found = list(row["suggestions"] or [])
            if any(_same(s["text"], text) for s in found):
                return False
            found.append(
                {
                    "id": uuid.uuid4().hex[:10],
                    "text": text,
                    "source": _clip(source, 80),
                    "at": tx.now,
                    "status": "waiting",
                }
            )
            tx.update(table, row, {"suggestions": found[-MAX_SUGGESTIONS:]})
            tx.emit(
                "goal.suggestion_added",
                actor_id=who.actor_id,
                subject_type="goal",
                subject_id=goal_id,
                data={"text": text, "source": source},
                noise=True,
            )
        return True

    def answer_suggestion(
        self, who: Principal, goal_id: str, suggestion_id: str, *, accept: bool
    ) -> dict[str, Any]:
        """Make a suggestion a step (it joins the board's first checklist, or a new "Next
        steps" one; a task from build step G2), or say no, which is remembered."""
        who.require("brain.govern")
        goal = self.rt.brain.goal(goal_id)
        row = self._row(goal_id)
        found = list(row["suggestions"] if row else [])
        match = next((s for s in found if s["id"] == suggestion_id), None)
        if row is None or match is None or match.get("status") != "waiting":
            raise ValidationFailed("That suggestion is not waiting.", field="suggestion_id")
        match["status"] = "accepted" if accept else "dismissed"
        board = dict(row["layout"])
        if accept:
            blocks = [dict(b) for b in board.get("blocks") or []]
            target = next((b for b in blocks if b["type"] == "checklist"), None)
            if target is None:
                target = _block("checklist", "Next steps", True, items=[])
                blocks.append(target)
            target["items"] = [*(target.get("items") or []), {"text": match["text"], "done": False}]
            board["blocks"] = blocks
        table = schema.goal_boards
        with self.rt.write() as tx:
            current = tx.one(table, row["id"], "goal board")
            tx.update(table, current, {"suggestions": found, "layout": board})
        if accept:
            self._save(who, goal_id, clean_layout(board), None, goal)
        return self.get(who, goal_id)

    # ---------------------------------------------------------------- the coach

    def coach_prompt(self, who: Principal, messages: list[dict[str, Any]]) -> str:
        """The coach's prompt for this conversation ([{"role": "you" | "coach", "text"}])."""
        who.require("brain.read")
        turns = [m for m in messages if isinstance(m, dict) and _clip(m.get("text"), 4000)]
        if not turns:
            raise ValidationFailed("Say what you want to achieve.", field="messages")
        if len(turns) > MAX_COACH_TURNS:
            raise ValidationFailed("Start over: the coach keeps it short.", field="messages")
        projects = [p for p in self.rt.brain.projects() if p.active]
        listed = "; ".join(f"`{p.id}` {p.title}" for p in projects[:20]) or "none"
        asked = any(m.get("role") == "coach" for m in turns)
        conversation = "\n".join(
            f"{'Coach' if m.get('role') == 'coach' else 'Owner'}: {_clip(m.get('text'), 4000)}"
            for m in turns
        )
        if asked:
            conversation += "\n(You already asked your questions: write the draft now.)"
        return COACH.format(projects=listed, conversation=conversation)

    # ---------------------------------------------------------------- Home and Catch up

    def settings(self, who: Principal) -> dict[str, Any]:
        """Whether the weekly review is on (off by default)."""
        who.require("brain.read")
        with self.rt.read() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        found = dict((row["settings"] or {}).get("goals") or {})
        return {"weekly_review": bool(found.get("weekly_review"))}

    def configure(self, who: Principal, *, weekly_review: bool) -> dict[str, Any]:
        who.require("brain.govern")
        with self.rt.write() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            settings = dict(row["settings"] or {})
            settings["goals"] = dict(settings.get("goals") or {}, weekly_review=weekly_review)
            tx.update(schema.workspaces, row, {"settings": settings})
        return self.settings(who)

    def home(self, who: Principal) -> dict[str, Any]:
        """Home's strip: the purpose in a line, the goals due a check-in, at most three agent
        goals that need you, and on review day the weekly review (when it is on)."""
        who.require("brain.read")
        weekly_review = self.settings(who)["weekly_review"]
        found = self.rt.brain.ladder()
        cards = self.rt.brain.goal_cards()
        due = [g for g in found.get("yours") or [] if g.get("check_in_due")]
        out: dict[str, Any] = {
            "has_goals": bool(found.get("has_goals")),
            "purpose": (found.get("purpose") or {}).get("text") or "",
            "check_ins": due,
            "agent_goals": [c["goal"] for c in cards][:3],
            "review": None,
        }
        now = self.rt.clock.now()
        if weekly_review and now.weekday() == WEEKLY_REVIEW_DAY:
            out["review"] = self._review(found, now)
        return out

    def _review(self, found: dict[str, Any], now: datetime) -> dict[str, Any]:
        """The weekly review, built by code: your goals with their calls and flags, agent
        goals that moved or slipped, the week's progress notes, up to three next steps."""
        since = now - timedelta(days=7)
        moved = []
        notes = []
        for goal in found.get("agents") or []:
            recent = goal.get("checked_at") and parse_iso(goal["checked_at"]) >= since
            if recent and goal.get("status") != "on_track":
                moved.append({"id": goal["id"], "title": goal["title"], "words": goal["words"]})
        for goal in found.get("yours") or []:
            full = self.rt.brain.goal(goal["id"])
            for entry in full.get("journal") or []:
                at = entry.get("at")
                if at and parse_iso(at) >= since and entry.get("kind") in ("check_in", "progress"):
                    notes.append(
                        {
                            "goal": goal["title"],
                            "at": at,
                            "line": entry.get("line") or entry.get("text") or "",
                        }
                    )
        steps = []
        table = schema.goal_boards
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table.c.goal_id, table.c.suggestions).where(
                    table.c.workspace_id == self.rt.workspace_id
                )
            )
        for row in rows:
            for s in row["suggestions"] or []:
                if s.get("status") == "waiting":
                    steps.append({"goal": row["goal_id"], "text": s["text"]})
        return {
            "goals": [
                {"id": g["id"], "title": g["title"], "words": g["words"], "flag": g.get("flag")}
                for g in found.get("yours") or []
            ],
            "agent_goals": moved,
            "notes": notes[:12],
            "next_steps": steps[:3],
        }
