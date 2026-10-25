"""Heartbeat learning (docs/dev/plans/heartbeat-learning-plan.md): every change a beat reads goes
into a staging buffer, scored for relevance and checked against the owner's filters by code,
with no model call; the distill learns from the buffer later.

At capture, a filter that matches an item the goal doesn't make relevant drops it (counted on the
beat, kept in the buffer as dropped, with "Bring back"). A filter that matches an item the goal
makes relevant is unclear: it is kept, marked `filter?`, for the distill to judge. Entries are
archived with their outcome, never deleted until the retention runs out (30 days by default).
"""

from __future__ import annotations

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
            status = "dropped" if d.dropped else "staged"
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
                    "outcome": {"route": outcome} if outcome and status == "staged" else None,
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
