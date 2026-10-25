"""The recorded day (docs/dev/plans/heartbeat-learning-plan.md, 14.7): a labelled day of changes
run through the real capture and distill code, scored against the ship gates.

A day file (scripts/heartbeat_day.json) holds the goal, the filters, the expected cross-item
patterns, and items: each with its source, its value before today (when it had one), today's
changes in order, and its correct route, labelled before any tuning. `run` stages yesterday's
values, captures each change as a beat would (relevance and filters, by code), runs one distill
on the heartbeat's own model, and scores what came out.
"""

from __future__ import annotations

import json
import statistics
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso
from workspace_core.db import schema

from . import learning

ACCURACY_GATE = 0.85


def load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        day: dict[str, Any] = json.load(handle)
    return day


def _item(entry: dict[str, Any], text: str, at: str) -> dict[str, Any]:
    cid = f"day:{entry['source']}"
    return {
        "id": entry["id"],
        "key": f"connector:{cid}:{entry['id']}",
        "title": entry["title"],
        "text": text,
        "at": at,
        "url": "",
        "speaker": "",
        "private": False,
        "connector_id": cid,
        "connector_name": entry["source"],
        "cli": "day",
        "feeds": [],
    }


def run(
    hb: Any, day: dict[str, Any], *, judge_tokens: int = 3700, beats_with_news: int = 20
) -> dict[str, Any]:
    """Run the day through capture and one distill; return the report with the gates."""
    owner = hb.ws.owner()
    hb.configure_learning(
        owner, goal=day["goal"], filters=day["filters"], learn="nightly", buffer_days=30
    )
    settings = hb.settings()
    now = hb.ws.rt.clock.now()
    yesterday = iso(now - timedelta(days=1))
    table = schema.staged_changes
    # Yesterday: each item's value before today, as an earlier distill left it.
    with hb.ws.rt.write() as tx:
        for entry in day["items"]:
            if entry.get("before") is None:
                continue
            item = _item(entry, entry["before"], yesterday)
            tx.insert(
                table,
                {
                    "id": tx.new_id("stg"),
                    "workspace_id": tx.workspace_id,
                    "connector_id": item["connector_id"],
                    "item_id": item["id"],
                    "field": "text",
                    "title": item["title"],
                    "url": "",
                    "old_value": None,
                    "new_value": entry["before"],
                    "changed_at": yesterday,
                    "seen_at": yesterday,
                    "beat_id": "day-yesterday",
                    "filter": "",
                    "unclear": False,
                    "status": "distilled",
                    "outcome": {"route": "short", "reason": "yesterday"},
                },
            )
    # Today: each change captured as a beat would, one beat per round of changes.
    rounds = max(len(e["steps"]) for e in day["items"])
    for k in range(rounds):
        at = iso(now - timedelta(minutes=15 * (rounds - k)))
        items = [_item(e, e["steps"][k], at) for e in day["items"] if k < len(e["steps"])]
        decisions = learning.decide(items, settings, hb.ws.rt.brain.relevance)
        learning.stage(hb.ws, f"day-beat-{k}", decisions)
    record = hb.beat(owner, "distill")
    return score(hb, day, record, judge_tokens=judge_tokens, beats_with_news=beats_with_news)


def _final(rows: list[dict[str, Any]]) -> dict[str, Any]:
    today = [r for r in rows if r["beat_id"] != "day-yesterday"]
    if any(r["status"] == "dropped" for r in today):
        return {
            "route": "dropped",
            "reason": next(r["filter"] for r in today if r["status"] == "dropped"),
        }
    last = today[-1] if today else rows[-1]
    return dict(last["outcome"] or {"route": last["status"]})


def score(
    hb: Any, day: dict[str, Any], record: dict[str, Any], *, judge_tokens: int, beats_with_news: int
) -> dict[str, Any]:
    table = schema.staged_changes
    with hb.ws.rt.read() as tx:
        rows = tx.rows(sa.select(table).order_by(table.c.seen_at, table.c.id))
        lines = tx.rows(
            sa.select(schema.heartbeat_lines).where(
                schema.heartbeat_lines.c.beat_id == record["id"]
            )
        )
    by_item: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_item.setdefault(r["item_id"], []).append(r)
    applied = {w["item_id"].rsplit(":", 1)[-1] for w in lines if w["status"] == "applied"}
    results = []
    for entry in day["items"]:
        final = _final(by_item.get(entry["id"]) or [])
        wanted = set(entry["expect"].split("|"))
        results.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "expect": entry["expect"],
                "got": final.get("route"),
                "reason": final.get("reason", ""),
                # Something that must wait is right when it waits, whatever the route said.
                "ok": final.get("route") in wanted
                or (entry.get("must_wait", False) and entry["id"] not in applied),
                "must_wait": entry.get("must_wait", False),
                "written_without_review": entry.get("must_wait", False) and entry["id"] in applied,
                "why": entry["why"],
            }
        )
    undone = [r for r in results if r["why"] == "undone the same day"]
    dropped = [r for r in results if r["got"] == "dropped"]
    accuracy = sum(r["ok"] for r in results) / len(results)
    caught = sum(r["reason"] == "undone the same day" for r in undone)
    budget = judge_tokens * beats_with_news
    tokens = record.get("tokens")
    lessons = [d for d in record.get("details") or [] if d.startswith("Proposed a lesson")]
    report = {
        "items": len(results),
        "changes": sum(len(e["steps"]) for e in day["items"]),
        "route_accuracy": round(accuracy, 3),
        "net_zero_caught": f"{caught} of {len(undone)}",
        "filter_precision": round(sum(r["expect"] == "dropped" for r in dropped) / len(dropped), 3)
        if dropped
        else None,
        "tokens": tokens,
        "tokens_budget": budget,
        "lessons": len(lessons),
        "patterns_expected": len(day.get("patterns") or []),
        "gates": {
            "route_accuracy_85": accuracy >= ACCURACY_GATE,
            "nothing_must_wait_written": not any(r["written_without_review"] for r in results),
            "tokens_within_budget": tokens is not None and tokens <= budget,
        },
        "misses": [r for r in results if not r["ok"]],
        "by_route": {
            route: statistics.mean([r["ok"] for r in results if r["expect"] == route] or [1])
            for route in sorted({r["expect"] for r in results})
        },
    }
    return report
