"""Catch up: what waits for the owner, as a plan rather than a pile.

Everything that needs governance falls in one of three tiers:

- HANDLED FOR YOU: what went in on its own (the capture policy, the owner's own scope), shown
  with the undo point that takes each back. Nothing to do.
- QUICK YES: suggestions nothing disagrees with, grouped by what they are and where they go,
  kept with one tap.
- NEEDS YOUR JUDGMENT: one at a time, each with a recommendation and its reason: a suggestion
  that disagrees with a note or nearly repeats one, a change to a note or its retirement, a
  skill, a suggestion that carries private detail, anything the review cannot settle.

Upkeep comes in small doses, never all at once: a few notes to confirm each week (the most
used first), a pair of possible duplicates, text to tidy, and the notes no AI has used in two
months. After a run of the same yes, an offer to decide once ("let facts from your AI go
straight in") turns repeated decisions into a rule; it is offered, never imposed, and never
under the Regulated preset.

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
from .onboarding import GOALS_ID
from .runtime import Runtime

SNOOZE_DAYS = 3
AWAY_DAYS = 3  # this long away, and the recap comes before the to-dos
RECAP_DAYS = 7  # the window for someone who never caught up
QUOTA = {"recheck": 3, "duplicate": 2, "tidy": 2}  # upkeep per rolling week
UNUSED_DAYS = 60
UNUSED_MIN = 3
NUDGE_DAYS = 30  # captures read for the nudges
SUBJECT_MIN = 3  # this many captures about one subject no goal covers earn a nudge
KEEP_UNUSED_DAYS = 90  # "keep them": the unused notes are not offered again for this long
OFFER_RUN = 5  # this many of the same yes in a row earns an offer to decide once
OFFER_DAYS = 60
SECONDS = {
    "judgment": 40,
    "quick": 8,
    "recheck": 15,
    "duplicate": 30,
    "tidy": 25,
    "unused": 10,
    "offer": 5,
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
    if analysis.get("conflicts") or any(o.get("may_contradict") for o in overlaps):
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
    def __init__(self, rt: Runtime, brain: Brain) -> None:
        self.rt = rt
        self.brain = brain
        self._project_titles: dict[str, str] = {}

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
        judgment, quick = self._suggestions(review.proposals, rows, areas, hidden)
        upkeep = self._upkeep(attention, inventory, rows, hidden, now)
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
        seconds = (
            SECONDS["judgment"] * len(judgment)
            + SECONDS["quick"] * len(quick)
            + sum(SECONDS.get(card["type"], 20) for card in upkeep)
            + SECONDS["offer"] * len(offered)
        )
        return {
            "seen_at": seen_at,
            "since": since,
            "away_days": away,
            "recap_first": away is not None and away >= AWAY_DAYS,
            "seconds": seconds,
            "minutes": math.ceil(seconds / 60) if seconds else 0,
            "caught_up": not (judgment or quick or upkeep or offered),
            "counts": {
                "judgment": len(judgment),
                "quick": len(quick),
                "quick_items": sum(g["count"] for g in quick),
                "upkeep": len(upkeep),
                "offers": len(offered),
                "handled": recap.get("went_in_total", len(handled)),
                "snoozed": sum(1 for key in hidden if key in state.get("snoozed", {})),
            },
            "health": health(inventory, attention, now),
            "recap": recap,
            "handled": handled,
            "judgment": judgment,
            "quick": quick,
            "upkeep": upkeep,
            "offers": offered,
            "nudges": [n for n in self._nudges(now, projects) if n["key"] not in hidden],
            "preset": policies.get("preset"),
        }

    def _suggestions(
        self,
        proposals: list[dict[str, Any]],
        rows: dict[str, dict[str, Any]],
        areas: dict[str, str],
        hidden: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        judgment: list[dict[str, Any]] = []
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in sorted(proposals, key=lambda r: str(r.get("created") or "")):
            key = f"proposal:{row['id']}"
            if key in hidden:
                continue
            analysis = row.get("analysis") or {}
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
        return judgment, quick

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
        other: dict[str, Any] | None = None
        detail = ""
        if why == "conflict":
            other = (analysis.get("conflicts") or [None])[0] or next(
                (o for o in overlaps if o.get("may_contradict")), None
            )
            detail = str((other or {}).get("contradiction") or "")
            detail = detail[:1].upper() + detail[1:] + ("." if detail else "")
        elif why == "close":
            other = next((o for o in overlaps if o.get("close")), None)
        elif why in ("change", "retire", "replace"):
            other = (analysis.get("replaces") or [None])[0]
        source = source_label(row)
        recommend = self._recommend(row, analysis, why, other, rows, source)
        note = note_kind(row) if kind.startswith("note.") else kind.split(".")[0]
        shapes = note in ("rule", "identity") or why == "skill"
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
            "why": WHY.get(why, "").format(
                other=(other or {}).get("title") or "a note",
                detail=detail,
                problem=(analysis.get("problems") or [""])[0],
                private=(row.get("target") or {}).get("private") or "private detail",
            ),
            "recommend": recommend,
            "actions": ACTIONS[why],
        }

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
    ) -> list[dict[str, Any]]:
        """This week's dose of upkeep: notes to confirm (most used first), possible duplicates,
        text to tidy, and the notes no AI has used in two months, within the weekly quotas."""
        done = self._done_this_week(now)
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

    def _done_this_week(self, now: datetime) -> dict[str, int]:
        """Upkeep done in the last seven days, by kind, from the undo points' sources."""
        since = iso(now - timedelta(days=7))
        done: dict[str, int] = {}
        for point in self.rt.brain.checkpoints(200):
            if str(point.get("at") or "") < since or point.get("undone_by"):
                continue
            key = str((point.get("source") or {}).get("catch_up") or "")
            kind = key.split(":")[0]
            if kind in ("recheck", "twin", "tidy"):
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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "item"


def _advice(action: str, reason: str) -> dict[str, str]:
    return {"action": action, "reason": " ".join(reason.split())}


def _key(value: Any) -> str:
    key = str(value or "").strip()
    if not KEY.match(key):
        raise ValidationFailed("Name the catch-up item.", field="key")
    return key
