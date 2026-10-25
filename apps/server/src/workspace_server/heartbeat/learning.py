"""Heartbeat learning (docs/dev/plans/heartbeat-learning-plan.md): every change a beat reads goes
into a staging buffer, scored for relevance and checked against the owner's filters by code,
with no model call; the distill learns from the buffer later.

At capture, a filter that matches an item the goal doesn't make relevant drops it (counted on the
beat, kept in the buffer as dropped, with "Bring back"). A filter that matches an item the goal
makes relevant is unclear: it is kept, marked `filter?`, for the distill to judge. Entries are
archived with their outcome, never deleted until the retention runs out (30 days by default).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso, parse_iso
from workspace_core.db import schema

RELEVANT = 0.35  # a meaning (or words) score at or over this: the goal makes it relevant
BUFFER_DAYS = 30
COMMON = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "have",
        "will",
        "your",
        "about",
        "into",
        "what",
        "when",
        "which",
        "their",
        "there",
        "been",
        "were",
        "they",
        "them",
        "then",
        "than",
        "also",
        "just",
        "more",
        "some",
        "only",
        "over",
        "very",
    ]
)


@dataclass
class Filter:
    """A negative filter: a pattern (words, or a /regex/) and, optionally, the source and the
    field it is limited to."""

    pattern: str
    source: str = ""
    field: str = ""
    why: str = ""

    def matches(self, item: dict[str, Any], fld: str) -> bool:
        if self.source and self.source not in (
            item.get("connector_id"),
            item.get("connector_name"),
        ):
            return False
        if self.field and self.field != fld:
            return False
        text = f"{item.get('title') or ''}\n{item.get('text') or ''}"
        if len(self.pattern) > 2 and self.pattern.startswith("/") and self.pattern.endswith("/"):
            try:
                return re.search(self.pattern[1:-1], text, re.I) is not None
            except re.error:
                return False
        words = [w for w in re.split(r"\s+", self.pattern.strip().lower()) if w]
        lowered = text.lower()
        return bool(words) and all(re.search(rf"\b{re.escape(w)}\b", lowered) for w in words)


def filters_of(settings: dict[str, Any]) -> list[Filter]:
    out = []
    for raw in settings.get("filters") or []:
        if isinstance(raw, dict) and str(raw.get("pattern") or "").strip():
            out.append(
                Filter(
                    pattern=str(raw["pattern"]).strip(),
                    source=str(raw.get("source") or ""),
                    field=str(raw.get("field") or ""),
                    why=str(raw.get("why") or ""),
                )
            )
    return out


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower()) if w not in COMMON}


def words_score(goal: str, text: str) -> float | None:
    """The share of the goal's words the item says (None without a goal)."""
    wanted = content_words(goal)
    if not wanted:
        return None
    return len(wanted & content_words(text)) / len(wanted)


@dataclass
class Decision:
    item: dict[str, Any]
    field: str = "text"
    score: float | None = None  # meaning, else words, against the goal; None without a goal
    words: float | None = None
    dropped: str = ""  # the filter's reason, when it dropped the item at capture
    unclear: str = ""  # a filter matched an item the goal makes relevant: the distill judges


def decide(
    items: list[dict[str, Any]],
    settings: dict[str, Any],
    meaning: Any = None,
) -> list[Decision]:
    """For each new item: its relevance to the goal and what the filters say, by code.
    `meaning(goal, texts)` gives a meaning score per text, or None (no meaning model here)."""
    goal = str(settings.get("goal") or "").strip()
    texts = [f"{i.get('title') or ''}. {i.get('text') or ''}" for i in items]
    scores = meaning(goal, texts) if goal and meaning is not None and items else None
    rules = filters_of(settings)
    out = []
    for n, item in enumerate(items):
        words = words_score(goal, texts[n]) if goal else None
        score = scores[n] if scores is not None and scores[n] is not None else words
        decision = Decision(item=item, score=score, words=words)
        hit = next((f for f in rules if f.matches(item, decision.field)), None)
        if hit is not None:
            reason = hit.why or f"your filter: {hit.pattern}"
            if score is not None and score >= RELEVANT:
                decision.unclear = reason  # filtered, yet the goal says it matters
            else:
                decision.dropped = reason
        out.append(decision)
    return out


def stage(ws: Any, beat_id: str, decisions: list[Decision], outcome: str = "") -> int:
    """Put a beat's decisions into the buffer: each change with its old value (what the buffer
    last held for that item and field), its new one, when it changed and was seen."""
    if not decisions:
        return 0
    table = schema.staged_changes
    with ws.rt.write() as tx:
        for d in decisions:
            item = d.item
            previous = tx.conn.execute(
                sa.select(table.c.new_value)
                .where(
                    table.c.workspace_id == tx.workspace_id,
                    table.c.connector_id == item["connector_id"],
                    table.c.item_id == item["id"],
                    table.c.field == d.field,
                )
                .order_by(table.c.seen_at.desc(), table.c.id.desc())
                .limit(1)
            ).scalar()
            # A beat that judged it already (learning per beat) archives it as distilled.
            status = "dropped" if d.dropped else ("distilled" if outcome else "staged")
            tx.insert(
                table,
                {
                    "id": tx.new_id("stg"),
                    "workspace_id": tx.workspace_id,
                    "connector_id": item["connector_id"],
                    "item_id": item["id"],
                    "field": d.field,
                    "title": str(item.get("title") or "")[:300],
                    "url": str(item.get("url") or "")[:500],
                    "old_value": previous,
                    "new_value": str(item.get("text") or ""),
                    "changed_at": item.get("at") or None,
                    "seen_at": tx.now,
                    "beat_id": beat_id,
                    "score": d.score,
                    "filter": d.dropped or d.unclear,
                    "unclear": bool(d.unclear),
                    "status": status,
                    "outcome": {"route": outcome} if status == "distilled" else None,
                    "proposal_id": None,
                },
            )
    return len(decisions)


def purge(ws: Any, days: int = BUFFER_DAYS) -> int:
    """Remove buffer entries older than the retention (archived ones too)."""
    since = iso(ws.rt.clock.now() - timedelta(days=max(1, int(days))))
    table = schema.staged_changes
    with ws.rt.write() as tx:
        result = tx.conn.execute(
            table.delete().where(table.c.workspace_id == tx.workspace_id, table.c.seen_at < since)
        )
    return int(result.rowcount or 0)


def view(row: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "connector_id": row["connector_id"],
        "connector": names.get(row["connector_id"], row["connector_id"]),
        "item_id": row["item_id"],
        "field": row["field"],
        "title": row["title"],
        "url": row["url"],
        "old_value": row["old_value"],
        "new_value": row["new_value"],
        "changed_at": row["changed_at"],
        "seen_at": row["seen_at"],
        "score": row["score"],
        "filter": row["filter"],
        "unclear": bool(row["unclear"]),
        "status": row["status"],
        "outcome": row["outcome"],
    }


def age_days(ws: Any, row: dict[str, Any]) -> float:
    seen = parse_iso(row["seen_at"])
    return (ws.rt.clock.now() - seen).total_seconds() / 86400


# ---------------------------------------------------------------------- the distill

CONFIDENT = 0.7  # under this, a route goes to Catch up
STALE_DAYS = 14  # a Catch up item waiting this long joins the "still waiting" card
BATCH = 60  # netted items per model call
DISTILL_AT = "19:00"  # nightly, at the start of quiet hours, unless the owner chooses
ROUTES = ("short", "long", "catch_up", "discard")


@dataclass
class Net:
    """One item's day, netted by code: the first old value against the last new one."""

    connector_id: str
    item_id: str
    field: str
    rows: list[dict[str, Any]]
    old: str | None
    new: str | None
    edits: int
    deleted: bool
    unclear: str
    score: float | None

    @property
    def net_zero(self) -> bool:
        return not self.deleted and self.old is not None and (self.old or "") == (self.new or "")


def net(rows: list[dict[str, Any]]) -> list[Net]:
    """Each (source, item, field): repeated edits collapse to one with its count; equal first
    and last values are net-zero (undone the same day); a delete wins over earlier edits."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in sorted(rows, key=lambda r: (r["seen_at"], r["id"])):
        groups.setdefault((row["connector_id"], row["item_id"], row["field"]), []).append(row)
    out = []
    for (cid, item_id, fld), group in groups.items():
        scores = [r["score"] for r in group if r["score"] is not None]
        out.append(
            Net(
                connector_id=cid,
                item_id=item_id,
                field=fld,
                rows=group,
                old=group[0]["old_value"],
                new=group[-1]["new_value"],
                edits=len(group),
                deleted=any(r["new_value"] is None for r in group),
                unclear=next((r["filter"] for r in group if r["unclear"]), ""),
                score=max(scores) if scores else None,
            )
        )
    return out


def distill_prompt(
    items: list[dict[str, Any]], brain: dict[str, Any], settings: dict[str, Any]
) -> str:
    """One distill call: the day's netted changes, with the goal, the filters and the Brain's
    alignment (its rules, must-holds, regions, projects and sheets), routed one by one."""
    shown = {
        "goal": settings.get("goal") or "",
        "filters": [f.get("pattern") for f in settings.get("filters") or []],
        "brain": brain,
        "items": [
            {
                "item": i["key"],
                "connector": i["connector_name"],
                "title": i["title"],
                "now": i["text"],
                "before": i.get("before"),
                "changed": i.get("edits", 1),
                "deleted": bool(i.get("deleted")),
                "filter_unclear": i.get("unclear") or None,
                "at": i["at"],
            }
            for i in items
        ],
    }
    return (
        "You distill a day of changes into a person's Brain. Below, as JSON: their goal, their "
        "negative filters, the Brain (its rules and must-holds first, then regions, projects "
        "and context sheets) and each item's net change today (before, now, how many times it "
        "changed). The Brain's rules and must-holds win over the goal. For each item choose one "
        'route: "short" (a value that will change again: a context sheet cell, project '
        'progress or a task), "long" (a durable fact about their world: a person, an approval, '
        'how something runs, a decision: a note), "catch_up" (unsure, or it conflicts with '
        'what the Brain holds or a must-hold) or "discard" (not relevant, already known, or a '
        "filter applies). An item marked filter_unclear was matched by a filter yet looks "
        "relevant: settle it, or choose catch_up. Give each a confidence from 0 to 1 and a "
        "plain reason, its region and project, a one-line summary, and its writes in the "
        'heartbeat\'s write shapes: {"kind": "sheet", "sheet": id, "row": key, "column": name, '
        '"value": text}, {"kind": "progress", "project": id, "text": what moved, "next_up": '
        'text}, {"kind": "task", "project": id, "text": the task, "due": "YYYY-MM-DD" or ""}, '
        '{"kind": "note", "area": region id, "topic": a short lowercase-hyphenated name, "text": '
        "the fact}. Write only what the items say; never invent. Also name up to three "
        'patterns across items worth a lesson. Reply with one JSON object only: {"items": '
        '[{"item": key, "route": ..., "confidence": 0.0, "reason": text, "region": id, '
        '"project": id or null, "line": text, "protected_by": id or null, "writes": [...]}], '
        '"patterns": [{"title": text, "pattern": text, "story": text}], "headlines": {region '
        'id: text}, "projects": {project id: text}}.\n\n' + json.dumps(shown, ensure_ascii=False)
    )


def route_of(verdict: dict[str, Any], item: dict[str, Any]) -> tuple[str, str]:
    """(route, reason) after code's rules: low confidence and unsettled filter matches go to
    Catch up; an unknown route is Catch up too."""
    route = str(verdict.get("route") or "")
    reason = str(verdict.get("reason") or "")[:300]
    try:
        confidence = float(verdict.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if route not in ROUTES:
        return "catch_up", reason or "the distill gave no route"
    if route != "discard" and confidence < CONFIDENT:
        return "catch_up", f"not sure ({confidence:.2f}): {reason}".strip()
    if item.get("unclear") and route == "discard" and confidence < CONFIDENT:
        return "catch_up", f"a filter matched, unclear: {reason}".strip()
    return route, reason
