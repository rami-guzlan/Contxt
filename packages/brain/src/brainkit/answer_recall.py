"""The answer-recall eval (v4 backend plan, 16.4): did every needed item reach the AI by the
end of its answer, from its packets plus what it fetched?

Scored by code from a headless Claude Code transcript (operating_eval.run_lines); no model
grades here. A packet counts as what the Brain delivers for the AI's own request, worked out
again in-process on the same words-only Brain. A fetch counts when it opened a note without an
error (notes get, gnomon open, skills get); a search hit alone is a pointer, not the note.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .operating_eval import PULLS, SERVER, canonical

FETCHES = PULLS + ("notes_related", "activity_timeline")
OPENS = {"notes_get": "id", "gnomon_open": "address", "skills_get": "id"}
PER_CASE_USD = 0.0055  # Haiku, from the operating eval's reruns ($0.051 for 10 cases)


@dataclass
class Session:
    requests: list[str] = field(default_factory=list)  # each gnomon_get_context request
    fetched: set[str] = field(default_factory=set)     # note ids opened without an error
    searches: list[str] = field(default_factory=list)
    fetches: int = 0
    answer: str = ""
    tokens: int = 0
    cost: float | None = None
    error: str = ""


def _base(address) -> str:
    return str(address or "").split("#", 1)[0].strip()


def parse(lines: list[str]) -> Session:
    """A `claude -p --output-format stream-json --verbose` transcript."""
    s = Session()
    pending: dict[str, tuple[str, dict]] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        kind = event.get("type")
        content = (message.get("content") if isinstance(message, dict) else None) or []
        if kind == "assistant":
            for part in content if isinstance(content, list) else []:
                tool = str(part.get("name") or "")
                if part.get("type") == "tool_use" and tool.startswith(f"mcp__{SERVER}__"):
                    args = part.get("input") or {}
                    name = canonical(tool, args)
                    pending[str(part.get("id"))] = (name, args)
                    if name == "gnomon_get_context":
                        s.requests.append(str(args.get("request") or ""))
                    elif name in FETCHES:
                        s.fetches += 1
                        if name == "notes_search":
                            s.searches.append(str(args.get("query") or ""))
        elif kind == "user":
            for part in content if isinstance(content, list) else []:
                if part.get("type") != "tool_result":
                    continue
                name, args = pending.pop(str(part.get("tool_use_id")), ("", {}))
                if name in OPENS and not part.get("is_error") and _base(args.get(OPENS[name])):
                    s.fetched.add(_base(args.get(OPENS[name])))
        elif kind == "result":
            s.answer = str(event.get("result") or "")
            usage = event.get("usage") or {}
            s.tokens = sum(int(usage.get(k) or 0) for k in (
                "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
                "output_tokens"))
            s.cost = event.get("total_cost_usd")
            if event.get("is_error"):
                s.error = s.answer or str(event.get("subtype") or "error")
    return s


def packet(brain, request: str) -> set[str]:
    """The note ids a packet for `request` puts in front of the AI whole, as the retrieval
    eval counts them (evaluate.py): its notes, standing and held items, and its must-holds
    (a must-hold's one line is its point); pointers are left out."""
    st = brain.state()
    data = brain.context(request, record=False).data
    chain = data.get("scope_chain") or []
    must = set(data.get("must_hold_ids") or []) | set(data.get("must_hold_listed") or [])
    standing = {n.id for n in st.index.notes.values() if n.standing and n.scope in chain}
    seen = set(data.get("note_ids") or []) | set(data.get("held_ids") or []) | set(
        data.get("standing_ids") or []) | standing
    return (seen - set(data.get("pointer_ids") or [])) | must


def score(case: dict, *, packet: set[str], fetched: set[str], must_holds: set[str],
          fetches: int, tokens: int, cost: float | None, error: str = "") -> dict:
    """One case. `must` is a list of groups, any one of which answers that need."""
    groups = [list(g) if isinstance(g, (list, tuple)) else [g] for g in case.get("must") or []]
    reached = packet | fetched
    expected = set(case.get("must_holds") or [])
    return {"id": case["id"], "needed": len(groups),
            "packet_hits": sum(1 for g in groups if packet & set(g)),
            "answer_hits": sum(1 for g in groups if reached & set(g)),
            "complete": all(reached & set(g) for g in groups),
            "missed": [g for g in groups if not reached & set(g)],
            "wrong_must_holds": sorted((must_holds - expected) & reached),
            # A labeled must-hold that never reached the answer: the costly miss.
            "missed_must_holds": sorted((expected & must_holds) - reached),
            "must_holds_expected": len(expected & must_holds),
            "must_hold_chances": len(must_holds - expected),
            "fetches": fetches, "tokens": tokens, "cost": cost, "error": error}


def _measures(rows: list[dict]) -> dict:
    needed = [r for r in rows if r["needed"]]
    n = len(rows) or 1
    return {
        "cases": len(rows),
        "answer_recall": [sum(r["answer_hits"] for r in rows), sum(r["needed"] for r in rows)],
        "packet_recall": [sum(r["packet_hits"] for r in rows), sum(r["needed"] for r in rows)],
        "complete": [sum(bool(r["complete"]) for r in needed), len(needed)],
        "fetches_per_answer": round(sum(r["fetches"] for r in rows) / n, 2),
        "tokens_per_answer": round(sum(r["tokens"] for r in rows) / n),
        "wrong_must_hold_cases": [sum(bool(r["wrong_must_holds"]) for r in rows), len(rows)],
        "wrong_must_holds": [sum(len(r["wrong_must_holds"]) for r in rows),
                             sum(r["must_hold_chances"] for r in rows)],
        "missed_must_holds": [sum(len(r.get("missed_must_holds") or []) for r in rows),
                              sum(r.get("must_holds_expected", 0) for r in rows)],
        "errors": sum(bool(r["error"]) for r in rows),
        # Why the misses missed (when the eval script records it).
        "searches_per_answer": round(sum(r.get("searches", 0) for r in rows) / n, 2),
        "missed_shown_by_search": sum(r.get("missed_shown_by_search", 0) for r in rows),
        "missed_pointed_in_packet": sum(r.get("missed_pointed_in_packet", 0) for r in rows),
        "cost_usd": round(sum(float(r["cost"] or 0) for r in rows), 4),
    }


def _rate(pair) -> float | None:
    return round(pair[0] / pair[1], 4) if pair[1] else None


def summary(brains: list[dict]) -> dict:
    """Every Brain's measures, all of them together, and the worst Brain on each rate."""
    each = {b["name"]: _measures(b["rows"]) for b in brains}
    out = {"brains": each, "all": _measures([r for b in brains for r in b["rows"]])}
    worst = {}
    for key in ("answer_recall", "packet_recall", "complete"):
        rated = [(name, _rate(m[key])) for name, m in each.items() if _rate(m[key]) is not None]
        if rated:
            worst[key] = list(min(rated, key=lambda x: x[1]))
    out["worst"] = worst
    return out
