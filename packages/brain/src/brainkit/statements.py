"""One vocabulary for what a statement in the Brain is (brain-logic plan 6).

A statement is one thing the Brain holds: who someone is (identity), how to behave (a rule, or
its subtypes a convention or a preference), what is so (a fact), what was decided (a decision),
how something is done (a procedure), a current value (a value, the State tier), a project, or a
goal. The kinds a note is filed as, the capture types the presets govern, the kinds the
workspace, distillation and the knowledge agent propose, and the choices the MCP tools and the
command line offer all come from here.

Older words keep reading: a note of kind `state` is a value and a `focus` is a project, and a
note is never rewritten for it. Who said a statement (`said_by`), when the Brain learned it, when
it was last confirmed, when it should be checked again (a shelf life by kind) and its tier are
read from what a note already records, unless it says.
"""
from __future__ import annotations

import datetime as dt

from . import util

KINDS = ("identity", "rule", "fact", "decision", "procedure", "value", "project", "goal")
RULE_SUBTYPES = ("convention", "preference")
# The word a note of each kind is filed under (`kind:` in its front matter). Values and projects
# keep the words vaults already use, so every note and the kernel's headings stay as they are.
FILED = {"value": "state", "project": "focus"}
# Older words, and the rule subtypes, for the kinds they name.
ALIASES = {"state": "value", "focus": "project", "convention": "rule", "preference": "rule",
           "correction": "rule", "progress": "project"}
# What a note may be proposed as (a project is made with `create_focus`, never proposed).
NOTE_KINDS = ("fact", "rule", "identity", "state", "decision", "procedure", "goal")
# What the workspace, distillation and the knowledge agent may propose, in a person's words.
PROPOSAL_KINDS = ("fact", "rule", "preference", "convention", "decision", "procedure",
                  "identity", "state", "goal")
# What a capture is, as the presets govern it: a file, a fact, a decision, a project's progress,
# a preference, a rule, a convention, or a change to something already kept.
CAPTURE_TYPES = ("file", "fact", "decision", "progress", "preference", "rule", "convention",
                 "change")
# Who said it: the owner; the owner's AI, by inference from a conversation; another person (in a
# meeting or an email); a document; a synced system; an agent's run.
SAID_BY = ("owner", "owner-ai", "person", "document", "system", "agent")
# Where a note came from (inventory.origin_of's kinds), as who said it.
ORIGIN_SAID_BY = {"you": "owner", "workspace": "owner", "conversation": "owner-ai",
                  "chat": "owner-ai", "meeting": "person", "file": "document",
                  "doc": "document", "capture": "document", "upload": "document",
                  "library": "document", "folder": "document", "movein": "document",
                  "import": "document", "sync": "system", "work": "agent", "run": "agent",
                  "skill": "agent", "output": "agent", "agent": "agent"}
# Days a statement holds before it is checked again, by kind, unless it sets `review_by`
# (brain.json `statements.shelf_life` changes any of them). A decision also ends when it is
# replaced; a procedure when it is used after a change (the updating loop, step 7).
SHELF_LIFE = {"project": 30, "fact": 180, "decision": 365, "rule": 365, "identity": 365,
              "procedure": 180, "goal": 90, "value": 30}
TIERS = ("alignment", "state", "knowledge")
# A goal (goals plan 3.1): the Brain's purpose, one of yours, or one an agent keeps true. Its
# fields ride in its front matter; it is loaded `manual`, so no goal ever changes what a request
# receives.
GOAL_LEVELS = ("purpose", "yours", "agent")
GOAL_STATUSES = ("on_track", "at_risk", "off_track", "needs_attention", "no_data", "paused",
                 "met", "missed", "retired")
GOAL_FIELDS = ("owner", "level", "serves", "progress", "measure", "due", "cadence", "goal_status",
               "why", "started", "review_by")
OBJECTIVE_WORDS = 60  # a project's objective: a sentence or two


def kind(raw: str | None) -> str:
    """The vocabulary's kind for a filed or proposed word (`state` is a value, `focus` a
    project, a preference a rule); an unknown word is a fact."""
    word = str(raw or "").strip().lower()
    word = ALIASES.get(word, word)
    return word if word in KINDS else "fact"


def subtype(raw: str | None) -> str:
    """A rule's subtype named by a proposal's word (`preference`, `convention`), or ""."""
    word = str(raw or "").strip().lower()
    return word if word in RULE_SUBTYPES else ""


def filed(raw: str | None) -> str:
    """The word a note of this kind is filed under."""
    found = kind(raw)
    return FILED.get(found, found)


def capture_type(note_kind: str | None, note_subtype: str = "", decision: bool = False) -> str:
    """What a note is, as the capture policy names it: a rule (or its subtype), a convention
    (who someone is, a goal: what steers every AI), progress (where things stand), a decision
    or a fact."""
    found = kind(note_kind)
    if found in ("rule", "procedure"):
        return subtype(note_subtype) or "rule"
    if found in ("identity", "goal"):
        return "convention"
    if found in ("value", "project"):
        return "progress"
    if found == "decision" or decision:
        return "decision"
    return "fact"


def said_by(meta: dict, origin_kind: str = "") -> str:
    """Who said a statement: its own `said_by`, else what its origin says, else ""."""
    own = str((meta or {}).get("said_by") or "").strip().lower()
    if own in SAID_BY:
        return own
    return ORIGIN_SAID_BY.get(str(origin_kind or "").strip().lower(), "")


def tier(note_kind: str | None, load: str = "") -> str:
    """Alignment (rules, identity, must-holds, goals), state (values) or knowledge."""
    found = kind(note_kind)
    if found in ("rule", "identity", "goal") or load == "domain":
        return "alignment"
    if found == "value":
        return "state"
    return "knowledge"


def shelf_life(config, note_kind: str | None) -> int:
    """Days a statement of this kind holds before it is checked again."""
    custom = ((getattr(config, "data", None) or {}).get("statements") or {}).get(
        "shelf_life") or {}
    found = kind(note_kind)
    try:
        return int(custom.get(found, SHELF_LIFE.get(found, 180)))
    except (TypeError, ValueError):
        return SHELF_LIFE.get(found, 180)


def review_by(note, config) -> str:
    """When a statement should be checked again: its own `review_by`, else its last check
    (or approval) plus its kind's shelf life; "" without a date to count from."""
    own = util.parse_date(note.meta.get("review_by"))
    if own:
        return own.isoformat()
    since = util.parse_date(note.verified)
    if since is None:
        return ""
    return (since + dt.timedelta(days=shelf_life(config, note.kind))).isoformat()


def goal_problems(fields: dict) -> list[str]:
    """What keeps a goal's fields from being kept as they are."""
    problems = []
    level = str(fields.get("level") or "").strip()
    if level and level not in GOAL_LEVELS:
        problems.append(f"a goal's level is one of {', '.join(GOAL_LEVELS)}")
    status = str(fields.get("goal_status") or "").strip()
    if status and status not in GOAL_STATUSES:
        problems.append(f"a goal's status is one of {', '.join(GOAL_STATUSES)}")
    for name in ("due", "started", "review_by"):
        if str(fields.get(name) or "").strip() and util.parse_date(fields.get(name)) is None:
            problems.append(f"{name} is a date (YYYY-MM-DD)")
    return problems


def objective_problem(text: str) -> str:
    """Why a project's objective cannot be kept as written, or ""."""
    words = len(str(text or "").split())
    if words > OBJECTIVE_WORDS:
        return (f"an objective is a sentence or two, about {OBJECTIVE_WORDS} words at most "
                f"(this one has {words})")
    return ""


def describe(note, config, origin_kind: str = "") -> dict:
    """A note as a statement: its kind and subtype, who said it, when the Brain learned it,
    when it was last confirmed, when to check it again, and its tier."""
    approved = str(note.meta.get("approved_at") or "").strip()[:10]
    return {"kind": kind(note.kind),
            "subtype": subtype(note.meta.get("subtype")),
            "said_by": said_by(note.meta, origin_kind),
            "learned": approved or note.added or None,
            "confirmed": str(note.meta.get("verified") or "").strip()[:10] or None,
            "review_by": review_by(note, config) or None,
            "tier": tier(note.kind, note.load)}
