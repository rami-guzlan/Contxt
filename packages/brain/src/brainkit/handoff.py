"""Tasks and handoffs (goals plan 5): the built-in Tasks sheet, and `hand_off`, the one way a
task's ownership and progress move.

A task is a row of the Tasks sheet (state.py), so its history is the cell log: who did what and
when. Owner, Status, Evidence and Card change only here. The card is the working context's
resumption card made portable: done-when, done so far, next step, decisions, open questions,
what to load, the must-holds in play, the project's objective and the goal's line (code fills
those two), at about 250 tokens rendered, because it is pointers, not bodies.

Four moves, one call:

- TAKE (`claim`): status Working; the first claim wins.
- SAVE (no `to`): the card becomes the task's resumption card; the next session, or the same
  agent after a compaction, starts from it. A save identical to the last does nothing.
- PASS ON (`to`): the owner changes and the status becomes Handed off (Waiting for you when it
  is you). Done-when and Next step are required.
- FINISH (`status: done`): needs evidence, an output an AI recorded or a decided proposal. A
  task under a project writes a line to the project's journal; one under a goal of yours adds a
  line to its updates.

A `goal_note` can ride on any call, or `goal` alone can carry one: a line in the goal's journal
that never changes the goal or its status. Rules: only the owner, or you, passes on or
finishes; agents claim only what was handed to them or their tool; agents never open tasks for
your goals (they suggest); Blocked and Dropped need a reason. Text is masked for credentials and
is the agent's account, never evidence for a note and never an instruction.
"""
from __future__ import annotations

import json
import re

from . import state, util

SHEET = "tasks"
TOOLS = ("Claude Code", "Codex", "Cursor", "Claude app", "ChatGPT", "Gnomon run")
YOU = "you"
CARD_TOKENS = 250
FIELD_CHARS = 600
MAX_AGENT_TASKS = 5
STATUS_WORDS = {"open": "Open", "handed_off": "Handed off", "working": "Working",
                "waiting_for_you": "Waiting for you", "blocked": "Blocked", "done": "Done",
                "dropped": "Dropped"}
OPEN = ("open", "handed_off", "working", "waiting_for_you", "blocked")
CARD_FIELDS = ("done_when", "done_so_far", "next_step", "decisions", "open_questions", "load")
# What never reaches a task's log: credentials a session may paste (the run streams' patterns).
SECRETS = (
    re.compile(r"\b(wst|sk|pk|rk|ghp|gho|ghs|github_pat|xox[abpr])[-_][A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"(?i)\b(bearer)(\s+)[A-Za-z0-9._~+/\-]{12,}=*"),
    re.compile(r"(?i)\b(token|api[-_]?key|password|passwd|secret)(\s*[:=]\s*)[^\s\"',;]{6,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)


def mask(text: str) -> str:
    out = str(text or "")
    for pattern in SECRETS:
        out = pattern.sub("[hidden]", out)
    return out


def _result(message, data=None, is_error=False):
    from .governance import _result as result
    return result(message, data, is_error)


def _clean(value, limit=FIELD_CHARS) -> str:
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(v) for v in value if str(v).strip())
    return mask(" ".join(str(value or "").split()))[:limit]


def owner_label(owner: str) -> str:
    if owner == YOU:
        return "You"
    if owner.startswith("agent:"):
        name = owner.split(":", 1)[1]
        return "Knowledge agent" if name == "knowledge-agent" else f"{name} agent"
    return owner


def normal_owner(raw: str) -> str:
    """`you`, `agent:<name>`, or a tool queue ("Claude Code", "Claude Code, repo contxt")."""
    text = " ".join(str(raw or "").split())
    low = text.lower()
    if low in ("", "you", "me", "owner", "the owner"):
        return YOU
    if low in ("knowledge agent", "knowledge-agent", "agent:knowledge-agent"):
        return "agent:knowledge-agent"
    if low.startswith("agent:"):
        return "agent:" + util.slugify(text.split(":", 1)[1], 60)
    for tool in TOOLS:
        if low == tool.lower() or low.startswith(tool.lower() + ","):
            return tool + text[len(tool):]
    return "agent:" + util.slugify(text, 60)


def next_id(brain) -> str:
    numbers = [int(m.group(1)) for r in state.rows(brain, SHEET, with_computed=False)
               for m in [re.match(r"^T-(\d+)$", r.key)] if m]
    return f"T-{max(numbers, default=0) + 1}"


def _card(row) -> dict:
    try:
        found = json.loads(str(row.value("Card") or "") or "{}")
    except ValueError:
        found = {}
    return found if isinstance(found, dict) else {}


def view(brain, row, *, st=None) -> dict:
    """A task as the app and the tool return it."""
    card = _card(row)
    status = str(row.value("Status") or "open")
    owner = str(row.value("Owner") or YOU)
    return {"id": row.key, "row": row.id, "task": str(row.value("Task") or ""),
            "goal": str(row.value("Goal") or "") or None,
            "project": str(row.value("Project") or "") or None,
            "for": str(row.value("For") or "") or None,
            "milestone": str(row.value("Milestone") or "") == "yes",
            "owner": owner, "owner_label": owner_label(owner),
            "tool": str(row.value("Tool") or "") or None,
            "status": status, "status_words": STATUS_WORDS.get(status, status),
            "due": str(row.value("Due") or "") or None,
            "evidence": [e for e in str(row.value("Evidence") or "").split("; ") if e],
            "card": card, "created": row.created, "updated": row.updated,
            "days_open": row.computed.get("Days open"),
            "since_update": row.computed.get("Since update")}


def tasks(brain, *, owner: str = "", status: str = "", goal: str = "", project: str = "",
          open_only: bool = False) -> list[dict]:
    found = state.sheet(brain, SHEET)
    if found is None:
        return []
    out = []
    for row in state.rows(brain, SHEET):
        item = view(brain, row)
        if owner and item["owner"] != normal_owner(owner):
            continue
        if status and item["status"] != status:
            continue
        if goal and item["goal"] != goal:
            continue
        if project and item["project"] != project:
            continue
        if open_only and item["status"] not in OPEN:
            continue
        out.append(item)
    return sorted(out, key=lambda t: int(t["id"].split("-")[1]) if t["id"].startswith("T-")
                  else 0)


def task(brain, task_id: str) -> dict | None:
    row = state.find_row(brain, SHEET, task_id)
    if row is None:
        return None
    row = next(r for r in state.rows(brain, SHEET) if r.id == row.id)
    item = view(brain, row)
    item["log"] = [e for e in state.history(brain, SHEET, row.id)
                   if e.get("kind") in ("cell", "row")][:60]
    return item


def _must_holds(brain, text: str) -> list[str]:
    st = brain.state()
    low = text.lower()
    out = []
    for note in st.index.notes.values():
        if not note.must_hold or not note.live:
            continue
        words = [w.lower() for w in (note.triggers or []) + (note.applies_to or []) if w]
        if any(w and w in low for w in words):
            out.append(note.must_text or util.excerpt(note.body, 120))
    return out[:3]


def render(brain, item: dict) -> str:
    """The card as a model reads it, about 250 tokens at most: pointers, not bodies."""
    st = brain.state()
    card = item.get("card") or {}
    lines = [f"Task {item['id']}: {item['task']} ({item['status_words']}, owner "
             f"{item['owner_label']})"]
    focus = st.index.focuses.get(item["project"] or "") if item.get("project") else None
    if focus is not None and focus.objective:
        lines.append(f"Objective ({focus.title}): {util.excerpt(focus.objective, 300)}")
    if item.get("goal"):
        goal = st.index.note(item["goal"])
        if goal is not None:
            lines.append(f"Goal: {goal.title}")
    labels = {"done_when": "Done when", "done_so_far": "Done so far",
              "next_step": "Next step", "decisions": "Decisions made",
              "open_questions": "Open questions", "load": "What to load"}
    for key in CARD_FIELDS:
        if card.get(key):
            lines.append(f"{labels[key]}: {card[key]}")
    holds = _must_holds(brain, " ".join([item["task"], *[str(v) for v in card.values()]]))
    if holds:
        lines.append("Must-holds in play: " + " | ".join(holds))
    text = "\n".join(lines)
    while util.tokens(text) > CARD_TOKENS and len(lines) > 3:
        lines.pop()
        text = "\n".join(lines + [f"(the rest is in the task's log: get_state tasks "
                                  f"{item['id']})"])
    return text


def _evidence_ok(brain, evidence: list[str]) -> list[str]:
    """Evidence that exists: an output an AI recorded, or a decided proposal."""
    from .activity import normal_path
    decided: set[str] = set()
    for record in brain.vault.decisions():
        if record.get("action") in ("approved", "rejected"):
            decided.update(str(record.get(k) or "") for k in ("proposal", "proposal_id", "note"))
    decided.discard("")
    good = []
    for item in evidence:
        text = str(item or "").strip()
        if not text:
            continue
        if text in decided or brain.ledger.output(normal_path(text)) is not None:
            good.append(text)
    return good


def hand_off(brain, *, task: str = "", new_task: dict | None = None, goal: str = "",
             to: str = "", claim: bool = False, status: str = "", done_so_far="",
             next_step="", done_when="", decisions="", open_questions="", load=None,
             evidence=None, goal_note: str = "", reason: str = "", caller: str = YOU,
             tool: str = "", session: str = "", acting_for: str = ""):
    """Take, save, pass on or finish a task, or add a goal note (module docstring). `caller`
    is who is calling: `you` (the app, or a session acting for you), or `agent:<name>`."""
    from . import ladder
    who = acting_for or brain.principal()
    caller = normal_owner(caller) if caller != YOU else YOU
    said_by = "agent" if caller.startswith("agent:") else (
        "owner" if not tool else "owner-ai")
    source = f"hand_off ({tool or owner_label(caller)})"
    notes = []
    # A goal note with no task.
    if goal and not task and not new_task:
        if not goal_note:
            return _result("Say the goal note in a line.", {"status": "invalid"}, True)
        done = ladder.journal_note(brain, goal, _clean(goal_note), kind="progress",
                                   by=owner_label(caller), actor=who)
        return done
    state.ensure_tasks(brain, actor=who)
    if new_task:
        made = _open(brain, new_task, caller=caller, who=who, said_by=said_by, source=source,
                     session=session, tool=tool)
        if made.is_error:
            return made
        task = made.data["id"]
        notes.append(f"Opened {task}.")
    row = state.find_row(brain, SHEET, task)
    if row is None:
        return _result(f"No task {task!r}. Open one with new_task, or check its id "
                       "(get_state tasks).", {"status": "missing"}, True)
    row = next(r for r in state.rows(brain, SHEET) if r.id == row.id)
    item = view(brain, row)
    owner = item["owner"]
    queue = owner.split(",")[0]
    mine = caller == YOU or caller == owner or (tool and queue == tool)
    values: dict = {}
    card = dict(item["card"])
    for key, value in (("done_so_far", done_so_far), ("next_step", next_step),
                       ("done_when", done_when), ("decisions", decisions),
                       ("open_questions", open_questions), ("load", load)):
        if value:
            card[key] = _clean(value)
    if claim:
        if item["status"] == "working" and owner not in (caller, tool) and caller != YOU \
                and not (tool and queue == tool):
            return _result(f"{owner_label(owner)} already has {item['id']}.",
                           {"status": "taken", "owner": owner}, True)
        if caller.startswith("agent:") and owner not in (caller,) and not (
                tool and queue == tool):
            return _result(f"{item['id']} was not handed to you.", {"status": "refused"}, True)
        values["Status"] = "working"
        if tool:
            values["Tool"] = tool
        if caller.startswith("agent:"):
            values["Owner"] = caller
        notes.append(f"{item['id']} is yours now: working.")
    if to:
        if not mine:
            return _result("Only the task's owner, or you, passes it on.",
                           {"status": "refused"}, True)
        if not card.get("done_when") or not card.get("next_step"):
            return _result("Passing a task on needs done_when and next_step, so the next "
                           "owner can start at once.", {"status": "invalid"}, True)
        target = normal_owner(to)
        values["Owner"] = target
        values["Status"] = "waiting_for_you" if target == YOU else "handed_off"
        notes.append(f"Passed to {owner_label(target)}.")
    if status:
        if status not in state.TASK_STATUSES or status in ("open", "handed_off"):
            return _result("status is working, blocked, waiting_for_you, done or dropped.",
                           {"status": "invalid"}, True)
        if status in ("done", "dropped") and not mine:
            return _result("Only the task's owner, or you, finishes or drops it.",
                           {"status": "refused"}, True)
        if status in ("blocked", "dropped") and not str(reason or "").strip():
            return _result(f"{STATUS_WORDS[status]} needs a reason.",
                           {"status": "invalid"}, True)
        if status == "done":
            given = [e for e in (evidence if isinstance(evidence, list)
                                 else [evidence] if evidence else [])]
            good = _evidence_ok(brain, given)
            if not good:
                return _result("Done needs evidence: an output an AI recorded "
                               "(record_output) or a decided proposal's id.",
                               {"status": "invalid"}, True)
            values["Evidence"] = "; ".join(dict.fromkeys(item["evidence"] + good))
        if reason:
            card["reason"] = _clean(reason)
        values["Status"] = status
    card_text = json.dumps({**card, "by": owner_label(caller), "at": util.now_iso()},
                           sort_keys=True)
    if card != item["card"]:
        values["Card"] = card_text
    if not values and not goal_note:
        return _result("That save says nothing new; nothing changed.",
                       {"status": "unchanged", "task": item, "card": render(brain, item)})
    if values:
        done = state.write(brain, SHEET, row.id, values, who=who, said_by=said_by,
                           source=source, session=session, ai=said_by != "owner",
                           handoff=True)
        if done.is_error:
            return done
    row = next(r for r in state.rows(brain, SHEET) if r.id == row.id)
    item = view(brain, row)
    after = _after(brain, item, values, caller=caller, who=who, goal_note=goal_note)
    notes += after
    if decisions:
        notes.append("If a decision here should last, propose it with propose_note.")
    receiver = render(brain, item)
    return _result(" ".join(notes) or f"Saved {item['id']}.",
                   {"status": "saved", "task": item, "card": receiver,
                    "owner": item["owner"], "task_status": item["status"]})


def _open(brain, spec: dict, *, caller, who, said_by, source, session, tool):
    from . import ladder
    title = _clean(spec.get("title") or spec.get("task"), 300)
    if not title:
        return _result("new_task needs a title.", {"status": "invalid"}, True)
    goal = str(spec.get("goal") or "").strip()
    st = brain.state()
    if goal:
        note = st.index.note(goal)
        if not ladder.is_goal(note):
            return _result(f"No goal {goal!r}.", {"status": "invalid"}, True)
        if caller.startswith("agent:") and str(note.meta.get("level") or "yours") == "yours":
            return _result("Agents do not open tasks for the owner's goals: suggest a next "
                           "step on the goal instead.", {"status": "refused"}, True)
    if caller.startswith("agent:"):
        mine = [t for t in tasks(brain, owner=caller, open_only=True)]
        if len(mine) >= MAX_AGENT_TASKS:
            return _result(f"An agent keeps at most {MAX_AGENT_TASKS} open tasks.",
                           {"status": "refused"}, True)
        if goal and any(t["goal"] == goal for t in mine):
            return _result("This goal already has an open task.", {"status": "refused"},
                           True)
    project = str(spec.get("project") or "").strip()
    if project and project not in st.index.focuses:
        match = next((f for f in st.index.focuses.values()
                      if f.title.lower() == project.lower()), None)
        project = match.id if match else ""
    task_id = next_id(brain)
    values = {"Task": title, "Owner": caller, "Status": "working" if caller != YOU else "open"}
    if tool:
        values["Tool"] = tool
    if goal:
        values["Goal"] = goal
    if project:
        values["Project"] = project
    if spec.get("for"):
        values["For"] = _clean(spec.get("for"), 200)
    if spec.get("due"):
        values["Due"] = str(spec.get("due"))
    if spec.get("milestone"):
        values["Milestone"] = "yes"
    made = state.add_row(brain, SHEET, task_id, values, who=who, said_by=said_by,
                         source=source, session=session, ai=said_by != "owner",
                         row_id=task_id.lower(), handoff=True)
    if made.is_error:
        return made
    return _result(f"Opened {task_id}.", {"status": "opened", "id": task_id})


def _after(brain, item: dict, values: dict, *, caller, who, goal_note) -> list[str]:
    """What a move touches: the goal's journal, the project's journal."""
    from . import focus, ladder
    notes = []
    if goal_note and item.get("goal"):
        ladder.journal_note(brain, item["goal"], f"{item['id']}: {_clean(goal_note, 300)}",
                            kind="progress", by=owner_label(caller), actor=who)
    if values.get("Status") == "done":
        if item.get("project"):
            focus.record_update(brain, item["project"],
                                f"{item['id']} done: {util.excerpt(item['task'], 120)}",
                                principal=who)
            notes.append("The project's journal has a line.")
        if item.get("goal") and not goal_note:
            ladder.journal_note(brain, item["goal"], f"{item['id']} done: {item['task']}",
                                kind="progress", by=owner_label(caller), actor=who)
    return notes


def pending_lines(brain, *, limit: int = 5) -> list[str]:
    """Tasks waiting to be picked up, one line each, for a session's first brief."""
    found = [t for t in tasks(brain, open_only=True)
             if t["status"] in ("handed_off", "waiting_for_you")]
    return [f"- {t['id']} {t['task']} ({t['status_words']}, for {t['owner_label']}): say "
            f"\"pick up {t['id']}\"" for t in found[:limit]]


def open_for_slipped_goal(brain, goal_id: str) -> str | None:
    """An agent opens a task when its goal slips: one open task per goal, five per agent."""
    from . import ladder
    note = brain.state().index.note(goal_id)
    if not ladder.is_goal(note) or str(note.meta.get("level") or "") != "agent":
        return None
    keeper = str(note.meta.get("kept_by") or "")
    if not keeper:
        return None
    done = hand_off(brain, new_task={"title": f"Bring back on track: {note.title}",
                                     "goal": goal_id},
                    caller=f"agent:{keeper}",
                    next_step="Run the check that serves this goal and suggest the fixes.")
    return None if done.is_error else done.data["task"]["id"]
