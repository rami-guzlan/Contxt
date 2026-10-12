"""Catch up: what waits for the owner, as a plan rather than a pile.

Everything that needs governance falls in one of three tiers:

- HANDLED FOR YOU: what went in on its own (the capture policy, the owner's own scope), shown
  with the undo point that takes each back. Nothing to do.
- QUICK YES: suggestions nothing disagrees with, grouped by what they are and where they go,
  kept with one tap.
- NEEDS YOUR JUDGMENT: one at a time, each with a recommendation and its reason: a suggestion
  that disagrees with a note or nearly repeats one, a change to a note or its retirement, a
  skill, a suggestion that carries private detail, anything the review cannot settle.

A suggestion that changes, retires or disagrees with a BASELINE (brainkit/baseline.py: a rule,
a must-hold, a standing note, a note the owner confirmed or AIs use a lot) gets a card of its
own: the old and new side by side with both dates, who approved the old one and how much AIs
use it, and for a rule or a must-hold the briefs it reached. It never joins a quick group, and
revising the baseline takes a reason of a few words. What went in on its own and a model then
read as disagreeing comes back as "Went in, but disagrees", with the undo point that takes it
back. A revision the owner scheduled (a day to think) is listed until it goes in, with a way
to cancel it.

Upkeep comes in small doses, never all at once: a few notes to confirm each week (the most
used first), a pair of possible duplicates, text to tidy, the notes no AI has used in two
months, and two "Still right?" spot checks on what went in on its own or was kept in a few
seconds. The share of approvals taken back within a month is shown with the health score, as
the sign that approvals drift. After a run of the same yes, an offer to decide once ("let
facts from your AI go straight in") turns repeated decisions into a rule; it is offered,
never imposed, and never under the Regulated preset.

"Later" hides an item for a few days; what the person set aside stays away. Their state (when
they last caught up, what is snoozed or set aside) is kept in the workspace's settings. What
upkeep they did this week is read from the Brain's undo points, which record the catch-up item
each decision came from (`source.catch_up`).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso, parse_iso
from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import ValidationFailed

from .brain import Brain, display_name
from .legacy import Legacy
from .loop import cards as loop_cards
from .onboarding import GOALS_ID
from .runtime import Runtime

SNOOZE_DAYS = 3
AWAY_DAYS = 3  # this long away, and the recap comes before the to-dos
RECAP_DAYS = 7  # the window for someone who never caught up
QUOTA = {
    "recheck": 3,
    "duplicate": 2,
    "tidy": 2,
    "musthold": 1,
    "spot": 2,
    "older": 2,
    "belief": 1,  # the cross-check's one belief to look at
}
CHALLENGER_BASELINES = 25  # this many baselines, and the external challenger is offered
QUICK_SECONDS = 4  # a judgment kept this fast is spot-checked later
SPOT_DAYS = 30  # what went in on its own, or was kept that fast, this recently
DRIFT_DAYS = 30  # an approval taken back within this long counts as drift
# The pace that earns a plain word on the next card: this many judgments kept, each this fast.
PACE = {"cards": 5, "seconds": 6}
# A rule that reads like safety, health, money, law or privacy is offered as a must-hold: one
# that goes into every brief whenever its area comes up, whatever the request's relevance.
MUST_CUES = re.compile(
    r"\b(allerg\w*|peanut\w*|epipen|asthma|diabet\w*|medication\w*|medical|safety|hazard\w*|"
    r"legal|lawyer\w*|compliance|regulat\w*|gdpr|hipaa|finra|confidential|privacy|"
    r"password\w*|secrets?|credential\w*|budget\w*|insurance)\b",
    re.IGNORECASE,
)
GENERIC_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "our",
    "your",
    "their",
    "this",
    "that",
    "every",
    "each",
    "rule",
    "rules",
    "note",
    "how",
    "what",
    "when",
    "who",
    "never",
    "always",
    "only",
}
UNUSED_DAYS = 60
UNUSED_MIN = 3
NUDGE_DAYS = 30  # captures read for the nudges
SUBJECT_MIN = 3  # this many captures about one subject no goal covers earn a nudge
KEEP_UNUSED_DAYS = 90  # "keep them": the unused notes are not offered again for this long
OFFER_RUN = 5  # this many of the same yes in a row earns an offer to decide once
OFFER_DAYS = 60
SECONDS = {
    "goal": 40,  # an agent goal that slipped: why, the trend, the suggested step
    "check": 60,  # a workflow's check: read what a step made, then go on, edit or stop
    "judgment": 40,
    "baseline": 60,
    "went_in": 30,
    "spot": 15,
    "older": 10,
    "challenge": 45,
    "belief": 30,
    "challenger": 15,
    "quick": 8,
    "recheck": 15,
    "duplicate": 30,
    "tidy": 25,
    "unused": 10,
    "offer": 5,
    "musthold": 20,
}
KEY = re.compile(r"^(?:[a-z_]+:[A-Za-z0-9_.:|@/-]{1,300}|unused)$")
MAX_BODY = 1500  # characters of a note or suggestion a card shows
LAYER_KINDS = {"rules": "rule", "facts": "fact", "identity": "identity", "state": "state"}
# How a plain-words card names what something is: (one, many).
KIND_WORDS = {
    "rule": ("rule", "rules"),
    "fact": ("fact", "facts"),
    "identity": ("note about you", "notes about you"),
    "state": ("status note", "status notes"),
    "file": ("file", "files"),
}
CAPTURE_WORDS = {
    "fact": "facts",
    "decision": "decisions",
    "progress": "progress notes",
    "preference": "preferences",
    "rule": "rules",
    "convention": "notes about who you are",
    "change": "changes to your notes",
    "file": "files",
}
ORIGIN_WORDS = {"chat": "your AI", "folder": "your folders", "app": "the app"}


def _clip(text: Any, limit: int = MAX_BODY) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def plural(count: int, kind: str) -> str:
    one, many = KIND_WORDS.get(kind, (kind, kind + "s"))
    return f"{count} {one if count == 1 else many}"


def note_kind(row: dict[str, Any]) -> str:
    """What a waiting note proposal is: rule, fact, identity or state."""
    target = row.get("target") or {}
    kind = str(target.get("kind") or "").strip().lower()
    if kind in KIND_WORDS:
        return kind
    area = str(target.get("area") or target.get("layer") or "")
    return LAYER_KINDS.get(area, "fact")


def source_label(row: dict[str, Any]) -> str:
    """Where a suggestion came from, as a person says it."""
    target = row.get("target") or {}
    origin = str(target.get("origin") or "")
    if row.get("kind") == "file.add":
        return "A file"
    if origin.startswith("import:"):
        return "Moved in"
    if str(row.get("session") or "").strip():
        return "A chat"
    raw = str(row.get("proposer") or "")
    if raw.startswith("human:"):
        return "You"
    if raw.startswith("model:"):
        return f"{display_name(raw)} (AI work)"
    return display_name(raw) if raw else "Someone"


def judgment_kind(row: dict[str, Any], analysis: dict[str, Any]) -> str | None:
    """Why a suggestion needs the person's judgment, or None when it is a quick yes."""
    kind = str(row.get("kind") or "")
    overlaps = analysis.get("overlaps") or []
    if kind == "note.challenge":
        return "challenge"
    if analysis.get("baseline"):
        return "baseline"
    if (
        analysis.get("conflicts")
        or any(o.get("may_contradict") for o in overlaps)
        or analysis.get("tensions")
    ):
        return "conflict"
    if analysis.get("problems"):
        return "problem"
    if any(o.get("close") for o in overlaps):
        return "close"
    if analysis.get("duplicates"):
        return "duplicate"
    if (row.get("target") or {}).get("private"):
        return "private"
    if kind == "note.update":
        return "change"
    if kind == "note.archive":
        return "retire"
    if kind.startswith("skill."):
        return "skill"
    if kind == "note.create" and analysis.get("replaces"):
        return "replace"
    return None


def health(
    inventory: list[dict[str, Any]], attention: dict[str, Any], today: datetime
) -> dict[str, Any]:
    """A score from three factors, each with its own fix: fresh (within its check date), tidy
    (no duplicates, text to move or disputes), used (reached an AI this month). A Brain with
    fewer than five notes is too new to score."""
    live = [
        r
        for r in inventory
        if r.get("type") == "note" and r.get("live") and r.get("kind") != "focus"
    ]
    if len(live) < 5:
        return {"score": None, "label": "new", "factors": []}
    due = sum(1 for r in live if r.get("stale"))
    fresh = 1 - due / len(live)
    disputed = sum(1 for r in live if r.get("confidence") == "disputed")
    issues = len(attention.get("twins") or []) + len(attention.get("flagged") or []) + disputed
    tidy = max(0.0, 1 - issues / max(5.0, len(live) * 0.25))
    cutoff = (today - timedelta(days=30)).date().isoformat()
    settled = [r for r in live if str(r.get("added") or "") < cutoff]
    used = (
        sum(1 for r in settled if (r.get("uses") or {}).get("d30")) / len(settled)
        if len(settled) >= 5
        else None
    )
    weights = [(fresh, 0.4), (tidy, 0.3)] + ([(used, 0.3)] if used is not None else [])
    score = round(100 * sum(v * w for v, w in weights) / sum(w for _, w in weights))
    factors = [
        {
            "key": "fresh",
            "label": "Fresh",
            "score": round(fresh, 3),
            "detail": f"{due} past their check date" if due else "every note within its check",
            "fix": {"label": "Check them", "to": "/review"} if due else None,
        },
        {
            "key": "tidy",
            "label": "Tidy",
            "score": round(tidy, 3),
            "detail": f"{issues} to tidy" if issues else "no duplicates or disputes",
            "fix": {"label": "Tidy up", "to": "/review"} if issues else None,
        },
    ]
    if used is not None:
        factors.append(
            {
                "key": "used",
                "label": "Used",
                "score": round(used, 3),
                "detail": f"{round(used * 100)}% reached an AI this month",
                "fix": {"label": "See unused", "to": "/brain/entries?view=unused"}
                if used < 0.6
                else None,
            }
        )
    label = "good" if score >= 80 else "fair" if score >= 60 else "low"
    return {"score": score, "label": label, "factors": factors}


def offers(
    events: list[dict[str, Any]], capture: dict[str, dict[str, str]], preset: str
) -> list[dict[str, Any]]:
    """Offers to decide once: a capture type from a chat or a folder the person kept
    `OFFER_RUN` times in a row (newest first, until a no) while it still waits. None under
    Regulated: there, nothing applies without approval."""
    if preset == "regulated":
        return []
    runs: dict[str, int] = {}
    stopped: set[str] = set()
    for event in events:  # newest first
        tag = str(event.get("capture") or "")
        kind, _, origin = tag.partition(":")
        if not kind or origin not in ("chat", "folder") or tag in stopped:
            continue
        if event.get("action") == "rejected":
            stopped.add(tag)
            continue
        if event.get("action") == "approved":
            runs[tag] = runs.get(tag, 0) + 1
    out = []
    for tag, count in sorted(runs.items(), key=lambda kv: -kv[1]):
        kind, _, origin = tag.partition(":")
        if count < OFFER_RUN or (capture.get(kind) or {}).get(origin) != "wait":
            continue
        words, place = CAPTURE_WORDS.get(kind, kind), ORIGIN_WORDS.get(origin, origin)
        out.append(
            {
                "key": f"offer:{tag}",
                "type": kind,
                "origin": origin,
                "kept": count,
                "title": f"Let {words} from {place} go straight in?",
                "detail": (
                    f"You kept the last {count} without a no. From now on they would go in on "
                    "their own, listed under Handled for you, and each could be taken back."
                ),
                "shapes": kind in ("preference", "rule", "convention", "change"),
            }
        )
    return out


class CatchUp:
    def __init__(self, rt: Runtime, brain: Brain, legacy: Legacy | None = None) -> None:
        self.rt = rt
        self.brain = brain
        self.legacy = legacy
        self._project_titles: dict[str, str] = {}
        # Work's checks: workflow runs waiting for the owner (set once Workflows exists).
        self.checks: Any = None
        # Goals and Projects (set once Goals exists): agent goals that slipped, and the
        # suggested next steps for your goals.
        self.goals: Any = None

    # ---------------------------------------------------------------- the plan

    def plan(self, who: Principal) -> dict[str, Any]:
        """Everything the catch-up shows: the recap since last time, the health score, what
        was handled, the judgment cards, the quick groups, upkeep and offers, with a time
        estimate."""
        who.require("brain.read")
        now = self.rt.clock.now()
        state = self._state()
        hidden = self._hidden(state, now)
        seen_at = state.get("seen_at")
        since = seen_at or iso(now - timedelta(days=RECAP_DAYS))
        away = (now - parse_iso(seen_at)).days if seen_at else None
        port = self.rt.brain
        review = self.brain.review(who)
        attention = port.attention()
        inventory = port.inventory()
        policies = port.policies()
        catalog = port.catalog()
        rows = {r["id"]: r for r in inventory if r.get("type") == "note"}
        areas = {a.key: a.label for a in catalog.areas}
        projects = port.projects()
        self._project_titles = {p.id: p.title for p in projects}
        judgment, quick, scheduled = self._suggestions(review.proposals, rows, areas, hidden)
        judgment += self._went_in(attention, hidden)
        points = port.checkpoints(200)
        upkeep = self._upkeep(attention, inventory, rows, hidden, now, points, policies)
        events = port.activity(
            since=iso(now - timedelta(days=OFFER_DAYS)),
            actions=["approved", "rejected"],
            limit=1000,
        )
        offered = [
            o
            for o in offers(
                events, policies.get("capture") or {}, str(policies.get("preset") or "")
            )
            if o["key"] not in hidden
        ]
        recap = port.recap(since)
        handled = recap.get("went_in") or []
        # Offered once, until it is brought in or set aside: what the earlier workspace holds.
        legacy = self.legacy.offer(who) if self.legacy is not None else None
        if legacy is not None and legacy["key"] in hidden:
            legacy = None
        work = [
            {
                "run_id": run.id,
                "workflow_id": run.workflow_id,
                "workflow": run.workflow,
                "ask": run.waiting["ask"] if run.waiting else "A step waits for a person.",
                "started_at": run.started_at,
            }
            for run in (self.checks(who) if self.checks is not None else [])
        ]
        slipped = [c for c in port.goal_cards() if c["key"] not in hidden]
        steps = self._goal_steps(hidden)
        handed, unclaimed = self._tasks(now, hidden)
        state_waiting = [
            w
            for w in port.state_act("waiting").get("waiting") or []
            if f"state:{w['event']}" not in hidden
        ]
        # The updating loop's asks (BL 9): "Still true?", bent rules, approval health,
        # corroboration, the quarterly review, lessons and the agent's hand-ups.
        looped = loop_cards(port, iso(now), hidden)
        seconds = (
            SECONDS["quick"] * len(looped)
            + SECONDS["goal"] * len(slipped)
            + SECONDS["judgment"] * len(handed)
            + SECONDS["quick"] * (len(unclaimed) + len(state_waiting))
            + SECONDS["quick"] * len(steps)
            + SECONDS["check"] * len(work)
            + sum(SECONDS.get(card["type"], SECONDS["judgment"]) for card in judgment)
            + SECONDS["quick"] * len(quick)
            + sum(SECONDS.get(card["type"], 20) for card in upkeep)
            + SECONDS["offer"] * len(offered)
            + (legacy["seconds"] if legacy else 0)
        )
        return {
            "seen_at": seen_at,
            "since": since,
            "away_days": away,
            "recap_first": away is not None and away >= AWAY_DAYS,
            "seconds": seconds,
            "minutes": math.ceil(seconds / 60) if seconds else 0,
            "caught_up": not (
                judgment
                or quick
                or upkeep
                or offered
                or legacy
                or work
                or slipped
                or steps
                or handed
                or unclaimed
                or state_waiting
                or looped
            ),
            "counts": {
                "judgment": len(judgment),
                "quick": len(quick),
                "quick_items": sum(g["count"] for g in quick),
                "upkeep": len(upkeep),
                "offers": len(offered),
                "legacy": 1 if legacy else 0,
                "handled": recap.get("went_in_total", len(handled)),
                "snoozed": sum(1 for key in hidden if key in state.get("snoozed", {})),
                "checks": len(work),
                "goals": len(slipped),
                "goal_steps": sum(len(g["steps"]) for g in steps),
                "handed": len(handed),
                "unclaimed": len(unclaimed),
                "state_waiting": len(state_waiting),
                "loop": len(looped),
            },
            "loop": looped,
            "handed": handed,
            "unclaimed": unclaimed,
            "state_waiting": state_waiting,
            "work": work,
            "goals": slipped,
            "goal_steps": steps,
            "health": dict(
                health(inventory, attention, now),
                unsaved=port.unsaved(),
                drift=drift(points, now),
            ),
            "recap": recap,
            "handled": handled,
            "judgment": judgment,
            "quick": quick,
            "upkeep": upkeep,
            "scheduled": scheduled,
            "pace": PACE,
            "offers": offered,
            "legacy": legacy,
            "nudges": [n for n in self._nudges(now, projects) if n["key"] not in hidden],
            "preset": policies.get("preset"),
        }

    def _tasks(
        self, now: datetime, hidden: set[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Tasks handed to you (Needs your judgment), and handoffs nobody claimed for a day
        (a quick Remind or Take back)."""
        handed, unclaimed = [], []
        for task in self.rt.brain.tasks(open_only=True):
            key = f"task:{task['id']}:{task['status']}"
            if key in hidden:
                continue
            if task["status"] == "waiting_for_you":
                handed.append(dict(task, key=key))
            elif (
                task["status"] == "handed_off"
                and task.get("updated")
                and now - parse_iso(task["updated"]) >= timedelta(days=1)
            ):
                unclaimed.append(dict(task, key=key))
        return handed, unclaimed

    def _goal_steps(self, hidden: set[str]) -> list[dict[str, Any]]:
        """Suggested next steps for your goals, a quick yes grouped by goal."""
        if self.goals is None:
            return []
        table = schema.goal_boards
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table.c.goal_id, table.c.suggestions).where(
                    table.c.workspace_id == self.rt.workspace_id
                )
            )
        titles = {g["id"]: g["title"] for g in self.rt.brain.ladder().get("yours") or []}
        out = []
        for row in rows:
            waiting = [
                s
                for s in row["suggestions"] or []
                if s.get("status") == "waiting" and f"goalstep:{s['id']}" not in hidden
            ]
            if waiting and row["goal_id"] in titles:
                out.append(
                    {
                        "goal": row["goal_id"],
                        "title": titles[row["goal_id"]],
                        "steps": waiting,
                    }
                )
        return out

    def _suggestions(
        self,
        proposals: list[dict[str, Any]],
        rows: dict[str, dict[str, Any]],
        areas: dict[str, str],
        hidden: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        judgment: list[dict[str, Any]] = []
        scheduled: list[dict[str, Any]] = []
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in sorted(proposals, key=lambda r: str(r.get("created") or "")):
            key = f"proposal:{row['id']}"
            analysis = row.get("analysis") or {}
            if analysis.get("scheduled"):
                # Decided, going in later: listed with a way to cancel, never asked again.
                planned = analysis["scheduled"]
                scheduled.append(
                    {
                        "proposal_id": str(row["id"]),
                        "title": str(row.get("title") or row.get("summary") or row["id"]),
                        "at": planned.get("for"),
                        "reason": planned.get("reason") or "",
                        "baseline": (analysis.get("baseline") or {}).get("title"),
                    }
                )
                continue
            if key in hidden:
                continue
            why = judgment_kind(row, analysis)
            if why is None:
                kind = "file" if row.get("kind") == "file.add" else note_kind(row)
                route = str(analysis.get("route_key") or row.get("route_key") or "")
                groups.setdefault((kind, route.split("/")[0]), []).append(row)
                continue
            judgment.append(self._card(row, analysis, why, rows))
        quick: list[dict[str, Any]] = []
        for (kind, area), members in groups.items():
            ids = [str(r["id"]) for r in members]
            label = areas.get(area) or area.replace("-", " ").capitalize() or "the Brain"
            shapes = kind in ("rule", "identity")
            quick.append(
                {
                    "key": f"group:{kind}:{area}",
                    "kind": kind,
                    "area": area,
                    "title": f"{plural(len(ids), kind)} for {label}",
                    "detail": "nothing they disagree with",
                    "count": len(ids),
                    "proposal_ids": ids,
                    "shapes": shapes,
                    "items": [
                        {
                            "id": str(r["id"]),
                            "title": str(r.get("title") or r.get("summary") or r["id"]),
                            "summary": _clip(r.get("note_summary") or "", 200),
                            "source": source_label(r),
                            **self._serves(r),
                        }
                        for r in members
                    ],
                    "sources": sorted({source_label(r) for r in members}),
                }
            )
        quick.sort(key=lambda g: (-g["count"], g["title"]))
        # Baselines first: they are what an AI follows everywhere.
        judgment.sort(key=lambda card: card["type"] != "baseline")
        return judgment, quick, scheduled

    def _card(
        self,
        row: dict[str, Any],
        analysis: dict[str, Any],
        why: str,
        rows: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """One decision to make, in plain words, with what to recommend and why."""
        kind = str(row.get("kind") or "")
        overlaps = analysis.get("overlaps") or []
        tensions = analysis.get("tensions") or []
        other: dict[str, Any] | None = None
        detail = ""
        if why == "challenge":
            other = analysis.get("challenged")
            detail = str((analysis.get("challenge") or {}).get("claim") or "")
        elif why == "baseline":
            other = analysis.get("baseline")
            detail = str((other or {}).get("tension") or "")
            detail = detail[:1].upper() + detail[1:] + ("." if detail else "")
        elif why == "conflict":
            other = (
                (analysis.get("conflicts") or [None])[0]
                or next((o for o in overlaps if o.get("may_contradict")), None)
                or (tensions or [None])[0]
            )
            found = next((t for t in tensions if t.get("id") == (other or {}).get("id")), None)
            detail = str(
                (other or {}).get("contradiction")
                or (found or {}).get("why")
                or ((found or {}).get("model") or {}).get("settle")
                or ""
            )
            detail = detail[:1].upper() + detail[1:] + ("." if detail else "")
        elif why == "close":
            other = next((o for o in overlaps if o.get("close")), None)
        elif why in ("change", "retire", "replace"):
            other = (analysis.get("replaces") or [None])[0]
        source = source_label(row)
        recommend = self._recommend(row, analysis, why, other, rows, source)
        note = note_kind(row) if kind.startswith("note.") else kind.split(".")[0]
        shapes = note in ("rule", "identity") or why == "skill"
        verdict = next(
            (t.get("model") for t in tensions if t.get("id") == (other or {}).get("id")), None
        )
        actions = list(ACTIONS[why])
        if why == "baseline" and (other or {}).get("change") != "disagree":
            actions.remove("both_hold")  # a new version of the note itself: one or the other
        return {
            "key": f"proposal:{row['id']}",
            "proposal_id": str(row["id"]),
            **self._serves(row),
            "type": why,
            "kind": note,
            "tag": TAGS.get(why) or ("Changes how every AI works" if shapes else "New " + note),
            "shapes": shapes,
            "title": str(row.get("title") or row.get("summary") or row["id"]),
            "summary": _clip(row.get("note_summary") or "", 300),
            "body": _clip(row.get("body") or ""),
            "source": source,
            "at": row.get("created"),
            "topic": str(analysis.get("route_key") or row.get("route_key") or ""),
            "with": (
                {
                    "id": other.get("id"),
                    "title": other.get("title"),
                    "body": _clip(other.get("body") or ""),
                    "score": other.get("score"),
                }
                if other
                else None
            ),
            "duplicates": [d.get("id") for d in analysis.get("duplicates") or []],
            "why": " ".join(
                WHY.get(why, "")
                .format(
                    other=(other or {}).get("title") or "a note",
                    detail=detail,
                    problem=(analysis.get("problems") or [""])[0],
                    private=(row.get("target") or {}).get("private") or "private detail",
                    baseline_line=_baseline_line(other or {}),
                )
                .split()
            ),
            "recommend": recommend,
            "actions": actions,
            "baseline": dict(other, body=_clip((other or {}).get("body") or ""))
            if why == "baseline" and other
            else None,
            "check": {
                "model": (analysis.get("checks") or {}).get("model") or "none",
                "verdict": verdict,
            },
            "held": analysis.get("held"),
        }

    def _went_in(self, attention: dict[str, Any], hidden: set[str]) -> list[dict[str, Any]]:
        """What went in on its own and a model then read as disagreeing with a note: a card
        each, with the undo point that takes it back."""
        out: list[dict[str, Any]] = []
        for item in attention.get("went_in") or []:
            key = str(item.get("key") or "")
            if not key or key in hidden:
                continue
            note, other = item.get("note") or {}, item.get("with") or {}
            verdict = item.get("model") or {}
            settle = str(verdict.get("settle") or "")
            point = item.get("checkpoint")
            reason = (
                f"Your AI read both: they disagree. {settle}"
                if settle
                else "Your AI read both and found they disagree."
            )
            out.append(
                {
                    "key": key,
                    "proposal_id": None,
                    "entry_id": str(note.get("id") or ""),
                    "checkpoint": point,
                    "goal": None,
                    "project": None,
                    "type": "went_in",
                    "kind": "note",
                    "tag": TAGS["went_in"],
                    "shapes": False,
                    "title": str(note.get("title") or note.get("id") or ""),
                    "summary": _clip(note.get("summary") or "", 300),
                    "body": _clip(note.get("body") or ""),
                    "source": "Went in on its own",
                    "at": note.get("at"),
                    "topic": str(note.get("route_key") or ""),
                    "with": {
                        "id": other.get("id"),
                        "title": other.get("title"),
                        "body": _clip(other.get("body") or ""),
                        "score": None,
                    },
                    "duplicates": [],
                    "why": WHY["went_in"].format(other=other.get("title") or "a note"),
                    "recommend": _advice("undo" if point else "review", reason),
                    "actions": ["undo", "keep_both", "later"]
                    if point
                    else ["review", "keep_both", "later"],
                    "baseline": None,
                    "check": {"model": "done", "verdict": verdict or None},
                    "held": None,
                }
            )
        return out

    def _serves(self, row: dict[str, Any]) -> dict[str, Any]:
        """The goal and the project the knowledge agent tagged a suggestion with."""
        target = row.get("target") or {}
        project_id = str(target.get("project_id") or "")
        return {
            "goal": str(target.get("goal") or "") or None,
            "project": (
                {"id": project_id, "title": self._project_titles.get(project_id, project_id)}
                if project_id
                else None
            ),
        }

    def _nudges(self, now: datetime, projects: list[Any]) -> list[dict[str, Any]]:
        """What the captures of the last month say is missing: work that is not a project
        yet, and a subject several of them share that none of the goals covers."""
        since = iso(now - timedelta(days=NUDGE_DAYS))
        items = schema.context_items
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(items.c.id, items.c.title, items.c.provenance).where(
                    items.c.workspace_id == self.rt.workspace_id,
                    items.c.archived_at.is_(None),
                    items.c.updated_at >= since,
                )
            )
        names = {p.title.lower() for p in projects} | {
            a.lower() for p in projects for a in p.aliases
        }
        out: list[dict[str, Any]] = []
        started: set[str] = set()
        subjects: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            digest = (row["provenance"] or {}).get("digest") or {}
            if digest.get("state") != "ready":
                continue
            work = " ".join(str(digest.get("new_project") or "").split())
            if work and work.lower() not in names and work.lower() not in started:
                started.add(work.lower())
                out.append(
                    {
                        "key": f"nudge:project:{_slug(work)}",
                        "type": "start_project",
                        "name": work,
                        "capture": {"id": row["id"], "title": row["title"]},
                        "title": f"“{row['title']}” is about {work}. Start a project?",
                    }
                )
            subject = " ".join(str(digest.get("off_goal") or "").split())
            if subject:
                subjects.setdefault(subject.lower(), []).append(
                    {"id": row["id"], "title": row["title"], "subject": subject}
                )
        out += self._agent_goal_lines()
        for found in subjects.values():
            if len(found) >= SUBJECT_MIN:
                subject = found[0]["subject"]
                out.append(
                    {
                        "key": f"nudge:goal:{_slug(subject)}",
                        "type": "add_goal",
                        "subject": subject,
                        "count": len(found),
                        "captures": [{"id": f["id"], "title": f["title"]} for f in found[:10]],
                        "title": f"You brought in {len(found)} things about {subject} this "
                        "month. Add it to your goals?",
                    }
                )
        return out

    def _agent_goal_lines(self) -> list[dict[str, Any]]:
        """An agent's "Goals it serves" lines that name no goal: each offered once as a goal
        with a measure (goals plan 7). One that names a goal by its id or title is a link."""
        ladder = self.rt.brain.ladder()
        agents = self.rt.brain.agents()
        goals = (ladder.get("yours") or []) + (ladder.get("agents") or [])
        known = {g["id"].lower() for g in goals} | {g["title"].lower() for g in goals}
        known |= {"you-goals", "the brain's purpose", "purpose"}
        out: list[dict[str, Any]] = []
        for agent in agents:
            for line in agent.get("goals") or []:
                text = " ".join(str(line).split()).strip(" .")
                if not text or text.lower() in known:
                    continue
                out.append(
                    {
                        "key": f"nudge:agentgoal:{agent.get('name')}:{_slug(text)}",
                        "type": "agent_goal",
                        "agent": agent.get("name"),
                        "line": text,
                        "title": f"The {agent.get('name')} agent serves “{text}”. Make this a "
                        "goal with a measure?",
                    }
                )
        return out

    def _recommend(
        self,
        row: dict[str, Any],
        analysis: dict[str, Any],
        why: str,
        other: dict[str, Any] | None,
        rows: dict[str, dict[str, Any]],
        source: str,
    ) -> dict[str, str]:
        """What to do, and why, from what the Brain knows about the note involved: whether it
        is past its check date, when a person last confirmed it, how much AIs use it."""
        found = rows.get(str((other or {}).get("id") or "")) or {}
        stale = bool(found.get("stale")) or found.get("confidence") == "disputed"
        uses = int((found.get("uses") or {}).get("d30") or 0)
        verified = str(found.get("verified") or "")[:10]
        if why == "challenge":
            if found.get("checked") and verified:
                return _advice(
                    "keep_note",
                    f"You confirmed your note on {verified}; keep it unless the evidence is "
                    "newer than that.",
                )
            return _advice(
                "dispute",
                "It comes with evidence. Disputed, your note stays, flagged, with this view "
                "beside it in planning work, and you can revise it after.",
            )
        if why == "baseline":
            change = str((other or {}).get("change") or "")
            relation = next(
                (
                    str((t.get("model") or {}).get("relation") or "")
                    for t in analysis.get("tensions") or []
                    if t.get("id") == (other or {}).get("id")
                ),
                "",
            )
            if change == "retire":
                if uses:
                    return _advice(
                        "keep_mine",
                        f"AIs still used it in {uses} chat{'s' if uses != 1 else ''} this month.",
                    )
                return _advice("revise", "No AI has used it lately; say why it goes.")
            if relation == "narrows":
                return _advice(
                    "both_hold",
                    "Your AI read both: this one is a narrower case. Both can hold once each "
                    "says where it applies.",
                )
            if stale:
                return _advice(
                    "revise", "Your note is past its check date, so this may be the newer word."
                )
            if source == "You":
                return _advice("revise", "You wrote this more recently than your note.")
            if verified:
                return _advice("keep_mine", f"You confirmed your note on {verified}.")
            if uses:
                return _advice(
                    "keep_mine",
                    f"AIs used your note in {uses} chat{'s' if uses != 1 else ''} this month, "
                    "and nothing says it changed.",
                )
            return _advice(
                "keep_mine",
                "Nothing says your note changed. Keep it, unless this is the newer word.",
            )
        if why == "conflict":
            if stale:
                return _advice(
                    "use_this", "Your note is past its check date, so this may be the newer word."
                )
            if source == "You":
                return _advice("use_this", "You wrote this more recently than your note.")
            if verified:
                return _advice("keep_mine", f"You confirmed your note on {verified}.")
            if uses:
                return _advice(
                    "keep_mine",
                    f"AIs used your note in {uses} chat"
                    f"{'s' if uses != 1 else ''} this month, and nothing says it "
                    "changed.",
                )
            return _advice(
                "keep_mine",
                "Nothing says your note changed. Keep it, unless this is the newer word.",
            )
        if why == "close":
            score = float((other or {}).get("score") or 0)
            longer = len(str(row.get("body") or "")) > 1.3 * len(
                str((other or {}).get("body") or "")
            )
            if longer and not score >= 0.9:
                return _advice(
                    "use_this", "This says more than your note; keeping it retires yours."
                )
            return _advice(
                "keep_mine",
                f"Your note already says this ({round(score * 100)}% alike)."
                if score
                else "Your note already says this.",
            )
        if why == "duplicate":
            return _advice("keep_one", "Another suggestion says the same: keep one of them.")
        if why == "private":
            detail = str((row.get("target") or {}).get("private") or "private detail")
            if (row.get("target") or {}).get("secret"):
                return _advice(
                    "not_this",
                    "It holds a password or a key. Keep those in a "
                    "password manager, never in the Brain.",
                )
            return _advice("not_this", f"It holds {detail}, and every AI you connect would see it.")
        if why == "retire":
            if uses:
                return _advice(
                    "not_this",
                    f"AIs still used this note in {uses} chat"
                    f"{'s' if uses != 1 else ''} this month.",
                )
            return _advice("keep", "No AI has used this note lately.")
        if why in ("change", "replace"):
            if stale:
                return _advice("keep", "The note it changes is past its check date.")
            if source == "You":
                return _advice("keep", "You made this change yourself.")
            return _advice("compare", "Compare the two: only you know which is current.")
        if why == "skill":
            return _advice(
                "review", "A skill changes how your AI works: read it once before keeping it."
            )
        return _advice("review", str((analysis.get("problems") or ["Look at it in full."])[0]))

    def _upkeep(
        self,
        attention: dict[str, Any],
        inventory: list[dict[str, Any]],
        rows: dict[str, dict[str, Any]],
        hidden: set[str],
        now: datetime,
        points: list[dict[str, Any]] | None = None,
        policies: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """This week's dose of upkeep: notes to confirm (most used first), possible duplicates,
        text to tidy, spot checks on quick approvals, and the notes no AI has used in two
        months, within the weekly quotas."""
        points = self.rt.brain.checkpoints(200) if points is None else points
        done = self._done_this_week(now, points)
        out: list[dict[str, Any]] = []

        def uses(entry_id: str) -> int:
            return int(((rows.get(entry_id) or {}).get("uses") or {}).get("d30") or 0)

        recheck = sorted(
            (r for r in attention.get("recheck") or [] if f"recheck:{r['id']}" not in hidden),
            key=lambda r: (-uses(r["id"]), str(r.get("title") or "")),
        )
        for item in recheck[: max(0, QUOTA["recheck"] - done.get("recheck", 0))]:
            found = rows.get(item["id"]) or {}
            out.append(
                {
                    "key": f"recheck:{item['id']}",
                    "type": "recheck",
                    "id": item["id"],
                    "title": item.get("title") or item["id"],
                    "summary": _clip(found.get("summary") or "", 300),
                    "why": str(item.get("why") or ""),
                    "uses": uses(item["id"]),
                    "last_used": (found.get("uses") or {}).get("last"),
                }
            )
        twins = [
            t
            for t in attention.get("twins") or []
            if f"twin:{t['a']}|{t['b']}" not in hidden and f"twin:{t['b']}|{t['a']}" not in hidden
        ]
        for twin in twins[: max(0, QUOTA["duplicate"] - done.get("twin", 0))]:
            keep, drop = (
                (twin["a"], twin["b"])
                if uses(twin["a"]) >= uses(twin["b"])
                else (twin["b"], twin["a"])
            )
            out.append(
                {
                    "key": f"twin:{twin['a']}|{twin['b']}",
                    "type": "duplicate",
                    "score": twin.get("score"),
                    "a": self._side(twin["a"], twin.get("a_title"), rows, uses(twin["a"])),
                    "b": self._side(twin["b"], twin.get("b_title"), rows, uses(twin["b"])),
                    "recommend": _advice(
                        f"keep:{keep}",
                        "Keep the one AIs use more; archiving the other can be undone."
                        if uses(keep) != uses(drop)
                        else "They say much the same: keep one, and undo it if you change "
                        "your mind.",
                    ),
                }
            )
        flagged = [f for f in attention.get("flagged") or [] if f"tidy:{f['id']}" not in hidden]
        for item in flagged[: max(0, QUOTA["tidy"] - done.get("tidy", 0))]:
            out.append(
                {
                    "key": f"tidy:{item['id']}",
                    "type": "tidy",
                    "id": item["id"],
                    "title": item.get("title") or item["id"],
                    "why": str(item.get("why") or ""),
                }
            )
        if done.get("musthold", 0) < QUOTA["musthold"]:
            offer = self._must_hold_offer(inventory, hidden)
            if offer is not None:
                out.append(offer)
        out += self._spot_checks(rows, hidden, now, points, QUOTA["spot"] - done.get("spot", 0))
        policies = policies or {}
        # The weekly cross-check: one belief something in the Brain says otherwise about.
        if policies.get("cross_check", True) and done.get("belief", 0) < QUOTA["belief"]:
            for finding in self.rt.brain.cross_check():
                if finding["key"] in hidden:
                    continue
                out.append(
                    {
                        "key": finding["key"],
                        "type": "belief",
                        "id": finding["id"],
                        "title": str(finding.get("title") or finding["id"]),
                        "summary": _clip(finding.get("body") or "", 300),
                        "why": str(finding.get("why") or ""),
                        "found_by": str(finding.get("found_by") or ""),
                        "baseline": str(finding.get("baseline") or ""),
                        "evidence": finding.get("evidence") or {},
                    }
                )
                break
        # The external challenger, offered once the Brain has many baselines or a stale one.
        if not policies.get("challenger") and "offer:challenger" not in hidden:
            baselines = sum(
                1
                for r in inventory
                if r.get("type") == "note" and r.get("live") and r.get("baseline")
            )
            stale = any(
                (rows.get(r["id"]) or {}).get("baseline") for r in attention.get("recheck") or []
            )
            if baselines >= CHALLENGER_BASELINES or stale:
                out.append(
                    {
                        "key": "offer:challenger",
                        "type": "challenger",
                        "baselines": baselines,
                        "stale": stale,
                    }
                )
        # A value and its newer value: briefs already carry the newer; retiring the older
        # keeps the Brain tidy.
        dated = [d for d in attention.get("dated") or [] if d["key"] not in hidden]
        for pair in dated[: max(0, QUOTA["older"] - done.get("older", 0))]:
            out.append(
                {
                    "key": pair["key"],
                    "type": "older",
                    "older": self._side(
                        pair["older"]["id"],
                        pair["older"].get("title"),
                        rows,
                        uses(pair["older"]["id"]),
                    ),
                    "newer": self._side(
                        pair["newer"]["id"],
                        pair["newer"].get("title"),
                        rows,
                        uses(pair["newer"]["id"]),
                    ),
                    "older_as_of": pair.get("older_as_of"),
                    "newer_as_of": pair.get("newer_as_of"),
                }
            )
        if "unused" not in hidden:
            idle = self._unused(inventory, now)
            if len(idle) >= UNUSED_MIN:
                out.append(
                    {
                        "key": "unused",
                        "type": "unused",
                        "count": len(idle),
                        "days": UNUSED_DAYS,
                        "items": idle[:50],
                    }
                )
        return out

    @staticmethod
    def _must_hold_offer(
        inventory: list[dict[str, Any]], hidden: set[str]
    ) -> dict[str, Any] | None:
        """One rule a week that reads like a constraint to never miss (an allergy, a budget,
        a legal or privacy line) and still competes on relevance: offered as a must-hold for
        its area, with a few words from it to start its triggers. The most used goes first."""
        candidates = [
            row
            for row in inventory
            if row.get("type") == "note"
            and row.get("live")
            and row.get("kind") == "rule"
            and row.get("load") == "on-demand"
            and f"musthold:{row['id']}" not in hidden
            and MUST_CUES.search(f"{row.get('title') or ''} {row.get('summary') or ''}")
        ]
        if not candidates:
            return None
        row = max(
            candidates,
            key=lambda r: (int(((r.get("uses") or {}).get("d30")) or 0), str(r.get("id"))),
        )
        words = re.findall(
            r"[a-z][a-z'-]{2,}", f"{row.get('title') or ''} {row.get('summary') or ''}".lower()
        )
        triggers = [w for w in dict.fromkeys(words) if w not in GENERIC_WORDS][:6]
        area = str(row.get("area") or "")
        return {
            "key": f"musthold:{row['id']}",
            "type": "musthold",
            "id": row["id"],
            "title": str(row.get("title") or row["id"]),
            "summary": _clip(row.get("summary") or "", 300),
            "area": area,
            "area_label": str(row.get("area_label") or area),
            "triggers": triggers,
            "recommend": _advice(
                "make_must_hold",
                f"It reads like a rule that should never be missed. As a must-hold it goes "
                f"into every brief whenever {row.get('area_label') or area} comes up, even "
                "when a request does not mention it.",
            ),
        }

    def _spot_checks(
        self,
        rows: dict[str, dict[str, Any]],
        hidden: set[str],
        now: datetime,
        points: list[dict[str, Any]],
        left: int,
    ) -> list[dict[str, Any]]:
        """ "Still right?" for what nobody looked at closely: notes that went in on their own,
        or were kept in a few seconds, in the last month and not confirmed since. The most
        used first, `left` of them."""
        if left <= 0:
            return []
        since = iso(now - timedelta(days=SPOT_DAYS))
        found: dict[str, tuple[str, str]] = {}  # note: (when, why)
        for event in self.rt.brain.activity(since=since, actions=["auto-applied"], limit=200):
            note_id = str(event.get("note") or "")
            at = str(event.get("at") or "")
            if note_id and at >= since and event.get("action") == "auto-applied":
                found.setdefault(note_id, (at, f"It went in on its own on {at[:10]}."))
        for point in points:
            seconds = _source(point).get("seconds")
            at = str(point.get("at") or "")
            if at < since or point.get("undone_by") or not isinstance(seconds, (int, float)):
                continue
            if seconds >= QUICK_SECONDS:
                continue
            for decision in point.get("decisions") or []:
                if decision.get("action") == "approved" and decision.get("note"):
                    found.setdefault(
                        str(decision["note"]),
                        (at, f"You kept it in {max(1, round(seconds))} seconds on {at[:10]}."),
                    )
        out: list[dict[str, Any]] = []
        for note_id, (at, why) in found.items():
            row = rows.get(note_id) or {}
            if not row.get("live") or f"spot:{note_id}" in hidden:
                continue
            if row.get("checked") and str(row.get("verified") or "") >= at[:10]:
                continue  # confirmed since
            out.append(
                {
                    "key": f"spot:{note_id}",
                    "type": "spot",
                    "id": note_id,
                    "title": str(row.get("title") or note_id),
                    "summary": _clip(row.get("summary") or "", 300),
                    "why": why,
                    "uses": int((row.get("uses") or {}).get("d30") or 0),
                    "last_used": (row.get("uses") or {}).get("last"),
                }
            )
        out.sort(key=lambda r: (-int(r["uses"]), str(r["title"])))
        return out[:left]

    @staticmethod
    def _side(
        entry_id: str, title: Any, rows: dict[str, dict[str, Any]], used: int
    ) -> dict[str, Any]:
        found = rows.get(entry_id) or {}
        return {
            "id": entry_id,
            "title": str(title or found.get("title") or entry_id),
            "summary": _clip(found.get("summary") or "", 300),
            "uses": used,
            "added": found.get("added"),
        }

    @staticmethod
    def _unused(inventory: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
        """Live notes no AI used in `UNUSED_DAYS` days, old enough to have had the chance;
        standing notes (in every conversation) and the Brain's goals stay out."""
        cutoff = (now - timedelta(days=UNUSED_DAYS)).date().isoformat()
        out = []
        for row in inventory:
            if row.get("type") != "note" or not row.get("live") or row.get("kind") == "focus":
                continue
            if row.get("load") in ("standing", "manual") or row.get("id") == GOALS_ID:
                continue
            last = str((row.get("uses") or {}).get("last") or "")
            if last >= cutoff or str(row.get("added") or "9999") >= cutoff:
                continue
            out.append(
                {
                    "id": row["id"],
                    "title": row.get("title") or row["id"],
                    "last_used": last or None,
                    "topic": row.get("topic_label") or row.get("topic"),
                }
            )
        out.sort(key=lambda r: (str(r["last_used"] or ""), str(r["title"])))
        return out

    def _done_this_week(
        self, now: datetime, points: list[dict[str, Any]] | None = None
    ) -> dict[str, int]:
        """Upkeep done in the last seven days, by kind, from the undo points' sources."""
        since = iso(now - timedelta(days=7))
        done: dict[str, int] = {}
        for point in self.rt.brain.checkpoints(200) if points is None else points:
            if str(point.get("at") or "") < since or point.get("undone_by"):
                continue
            key = str(_source(point).get("catch_up") or "")
            kind = key.split(":")[0]
            if kind in ("recheck", "twin", "tidy", "musthold", "spot", "older", "belief"):
                done[kind] = done.get(kind, 0) + 1
        return done

    # ---------------------------------------------------------------- the person's state

    def seen(self, who: Principal) -> dict[str, Any]:
        """The person caught up: the next recap starts from now."""
        who.require("brain.govern")
        with self.rt.write() as tx:
            stored = self._update(tx, lambda state: state.update(seen_at=tx.now))
        return stored

    def snooze(self, who: Principal, key: str, *, days: int = SNOOZE_DAYS) -> dict[str, Any]:
        """Later: hide an item for a few days."""
        who.require("brain.govern")
        key = _key(key)
        days = max(1, min(int(days), 90))
        with self.rt.write() as tx:
            until = iso(tx.moment + timedelta(days=days))
            return self._update(
                tx, lambda state: state.setdefault("snoozed", {}).update({key: until})
            )

    def dismiss(self, who: Principal, key: str, *, days: int | None = None) -> dict[str, Any]:
        """Set an item aside: for good, or for `days` (an offer turned down, the unused notes
        kept for now, two notes that only look alike)."""
        who.require("brain.govern")
        key = _key(key)
        if key == "unused" and days is None:
            days = KEEP_UNUSED_DAYS
        with self.rt.write() as tx:
            until = iso(tx.moment + timedelta(days=int(days))) if days else "always"
            return self._update(
                tx, lambda state: state.setdefault("dismissed", {}).update({key: until})
            )

    def _state(self) -> dict[str, Any]:
        with self.rt.read() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        return dict((row["settings"] or {}).get("catch_up") or {})

    @staticmethod
    def _hidden(state: dict[str, Any], now: datetime) -> set[str]:
        moment = iso(now)
        out = {k for k, until in (state.get("snoozed") or {}).items() if str(until) > moment}
        out |= {
            k
            for k, until in (state.get("dismissed") or {}).items()
            if until == "always" or str(until) > moment
        }
        return out

    def _update(self, tx: Any, change: Any) -> dict[str, Any]:
        row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        settings = dict(row["settings"] or {})
        state = dict(settings.get("catch_up") or {})
        moment = tx.now
        for name in ("snoozed", "dismissed"):  # what ran out goes
            kept = {
                k: v for k, v in (state.get(name) or {}).items() if v == "always" or str(v) > moment
            }
            state[name] = kept
        change(state)
        settings["catch_up"] = state
        tx.update(schema.workspaces, row, {"settings": settings})
        return state


TAGS = {
    "challenge": "A challenge to your note",
    "baseline": "Changes a baseline",
    "went_in": "Went in, but disagrees",
    "conflict": "Might disagree with your note",
    "close": "Close to a note you have",
    "duplicate": "Said twice",
    "private": "Private detail",
    "change": "Changes a note",
    "retire": "Retires a note",
    "replace": "Replaces a note",
    "skill": "A skill",
    "problem": "Needs a closer look",
}
WHY = {
    "challenge": "Says your note “{other}” is wrong or out of date: {detail}",
    "baseline": "{baseline_line} {detail}",
    "went_in": "It went in on its own, and your AI then read it as disagreeing with “{other}”.",
    "conflict": "Disagrees with your note “{other}”. {detail}",
    "close": "Very close to your note “{other}”.",
    "duplicate": "Another suggestion says much the same.",
    "private": "It holds {private}.",
    "change": "A new version of your note “{other}”.",
    "retire": "Takes “{other}” out of every AI's context.",
    "replace": "Keeping it retires your note “{other}”.",
    "skill": "A procedure your AI would follow.",
    "problem": "{problem}",
}
# The choices a card offers, the recommended one moved first by the page.
ACTIONS = {
    "challenge": ["dispute", "keep_note", "revise_note", "later"],
    "baseline": ["revise", "keep_mine", "both_hold", "later"],
    "went_in": ["undo", "keep_both", "later"],
    "conflict": ["keep_mine", "use_this", "keep_both", "edit", "later"],
    "close": ["keep_mine", "use_this", "keep_both", "edit", "later"],
    "duplicate": ["keep_one", "not_this", "later"],
    "private": ["not_this", "keep", "edit", "later"],
    "change": ["keep", "not_this", "edit", "later"],
    "retire": ["keep", "not_this", "later"],
    "replace": ["keep", "keep_both", "not_this", "edit", "later"],
    "skill": ["review", "keep", "not_this", "later"],
    "problem": ["review", "not_this", "later"],
}


def _baseline_line(baseline: dict[str, Any]) -> str:
    """What a baseline card is about, in one sentence."""
    title, why = baseline.get("title") or "a note", baseline.get("why") or "a baseline"
    change = baseline.get("change")
    if change == "retire":
        return f"Retires “{title}”, a baseline: {why}."
    if change == "revise":
        return f"A new version of “{title}”, a baseline: {why}."
    return f"May disagree with “{title}”, a baseline: {why}."


def drift(points: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """How many approvals of the last two months were taken back within DRIFT_DAYS: the sign
    that approvals drift. Only undo points that approved something count."""
    since = iso(now - timedelta(days=2 * DRIFT_DAYS))
    approvals = undone = 0
    for point in points:
        at = str(point.get("at") or "")
        if at < since or point.get("undoes"):
            continue
        if not any(d.get("action") == "approved" for d in point.get("decisions") or []):
            continue
        approvals += 1
        back = str(point.get("undone_at") or "")
        if back and parse_iso(back) - parse_iso(at) <= timedelta(days=DRIFT_DAYS):
            undone += 1
    return {
        "approvals": approvals,
        "undone": undone,
        "share": round(undone / approvals, 3) if approvals else None,
        "days": DRIFT_DAYS,
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "item"


def _advice(action: str, reason: str) -> dict[str, str]:
    return {"action": action, "reason": " ".join(reason.split())}


def _key(value: Any) -> str:
    key = str(value or "").strip()
    if not KEY.match(key):
        raise ValidationFailed("Name the catch-up item.", field="key")
    return key


def _source(point: dict[str, Any]) -> dict[str, Any]:
    """What an undo point says about where it came from, when it says it as fields (Catch up's
    own decisions do); older points and other apps name their source in a line of text."""
    source = point.get("source")
    return source if isinstance(source, dict) else {}
