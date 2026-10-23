"""What the brain's context costs, in tokens and dollars, on the lines of the brain-logic plan
(section 4.1):

    fixed     what sits in front of every model call of a session that uses the brain: the
              server's instructions, its tool definitions (only their names where the client
              loads the rest on use, as Claude Code does) and, in the brain's own repository,
              the kernel
    briefs    each brain answer (a brief, a note, a search) written into the conversation once
    rereads   the same answers read again from the cache on every later call, until the
              conversation is compacted
    rewrites  brain content written to the cache again after a pause longer than the cache's
              life
    jobs      background calls the app makes to a model: checks, the knowledge agent, runs

(The plan counts briefs and their re-reads as one line; they are shown apart here because the
re-reads usually cost more than the first write.)

Claude Code keeps a transcript of every session on this computer. `claude_code` reads them,
only when asked, for exact figures: each API call's usage and model, which brain answers each
call held, and when the cache was written again. Only token counts come out; nothing a
conversation said is kept. Without transcripts, re-reads are estimated from a typical number of
later calls, and the report says so.

Token counts of brain text are estimates (`util.tokens`: characters / 4, or tiktoken's o200k
when it is installed; both are made for other models). A calibration factor measured against
Claude (`factor`, set by `set_factor`) multiplies them. Usage read from transcripts and from
model calls is exact.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import statistics
from dataclasses import dataclass, field

from . import util

# Dollars per million tokens: input, output, cache read, cache write (5 minutes), cache write
# (1 hour). Anthropic's list prices as of October 2026; the owner can override any model in
# brain.json (`costs.prices`). Haiku 5.5's cache read is not listed: 10% of input is assumed.


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    write_5m: float
    write_1h: float


def _price(inp: float, out: float, read: float | None = None) -> Price:
    return Price(inp, out, inp * 0.1 if read is None else read, inp * 1.25, inp * 2.0)


PRICES: dict[str, Price] = {
    "claude-fable-5-1": _price(10.0, 50.0, 0.25),
    "claude-mythos-5-1": _price(10.0, 50.0, 0.25),
    "claude-fable-5": _price(10.0, 50.0),
    "claude-opus-5-5": _price(4.0, 20.0, 0.20),
    "claude-opus-5": _price(5.0, 25.0),
    "claude-opus-4-8": _price(5.0, 25.0),
    "claude-opus-4-7": _price(5.0, 25.0),
    "claude-opus-4-6": _price(5.0, 25.0),
    "claude-sonnet-5-5": _price(2.0, 10.0, 0.20),
    "claude-sonnet-5": _price(2.0, 10.0),
    "claude-sonnet-4-6": _price(3.0, 15.0),
    "claude-haiku-5-5": _price(0.10, 0.50),
    "claude-haiku-4-5": _price(1.0, 5.0),
}
FREE = Price(0.0, 0.0, 0.0, 0.0, 0.0)
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_LATER_CALLS = 20  # later model calls that re-read a brief, when no transcript says
LINES = ("fixed", "briefs", "rereads", "rewrites", "jobs")
PAUSE_5M = 5 * 60
PAUSE_1H = 60 * 60


def price_for(model: str | None, overrides: dict | None = None) -> Price | None:
    """The price of a model, by the longest known id it starts with; free for a local model;
    None when unknown."""
    name = str(model or "").strip().lower().split("[", 1)[0]
    if not name:
        return None
    if name.startswith(("ollama:", "local:")):
        return FREE
    table = dict(PRICES)
    for key, value in (overrides or {}).items():
        try:
            table[str(key).lower()] = Price(*[float(v) for v in value])
        except (TypeError, ValueError):
            continue
    best = max((k for k in table if name.startswith(k)), key=len, default=None)
    return table[best] if best else None


def call_cost(model, tokens_in=0, tokens_out=0, cache_read=0, cache_write=0, *,
              ttl: str = "5m") -> float:
    """Dollars for one call at list price; 0.0 when the model is unknown or local."""
    price = price_for(model)
    if price is None:
        return 0.0
    write = price.write_1h if ttl == "1h" else price.write_5m
    return (int(tokens_in or 0) * price.input + int(tokens_out or 0) * price.output
            + int(cache_read or 0) * price.cache_read + int(cache_write or 0) * write) / 1e6


# ------------------------------------------------------------------ calibration

def factor(ledger) -> float:
    """How many Claude tokens one estimated token is, as last measured (1.0 until then)."""
    try:
        value = float(ledger.meta("token_factor") or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return value if 0.3 <= value <= 3.0 else 1.0


def calibration(ledger) -> dict:
    """The factor and how it was measured, for the report."""
    raw = ledger.meta("token_factor_detail")
    try:
        detail = json.loads(raw) if raw else {}
    except ValueError:
        detail = {}
    return {"factor": factor(ledger), "measured": bool(raw), **detail}


def set_factor(ledger, pairs, *, method: str) -> dict:
    """Store the factor from (estimated, measured) token counts of the same texts."""
    pairs = [(int(e), int(m)) for e, m in pairs if int(e) > 0 and int(m) > 0]
    if not pairs:
        raise ValueError("no samples to calibrate with")
    estimated = sum(e for e, _m in pairs)
    measured = sum(m for _e, m in pairs)
    value = round(measured / estimated, 3)
    detail = {"method": method, "samples": len(pairs), "estimated": estimated,
              "claude": measured, "at": util.now_iso(),
              "estimator": util.tokenizer_status()["implementation"]}
    ledger.set_meta("token_factor", str(value))
    ledger.set_meta("token_factor_detail", json.dumps(detail))
    return {"factor": value, **detail}


def calibration_samples(brain, limit: int = 6) -> list[dict]:
    """Texts the brain really sends, for a calibration: the kernel and recent briefs."""
    out = []
    kernel = brain.kernel()
    if not kernel.is_error and kernel.text:
        out.append({"label": "kernel", "text": kernel.text})
    since = (util.now() - _dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with brain.ledger._connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, text FROM packets WHERE at >= ? AND tokens > 120 ORDER BY at DESC "
            "LIMIT ?", (since, max(1, limit - len(out))))]
    out += [{"label": f"brief {r['id']}", "text": r["text"]} for r in rows if r.get("text")]
    return out[:limit]


# ------------------------------------------------------------------ the fixed overhead

def overhead(brain) -> dict:
    """Tokens in front of every call of a session that uses the brain, by part, as estimated
    (multiply by `factor` for Claude)."""
    from . import mcp_server
    tools = mcp_server.AGENT_TOOLS
    kernel = brain.kernel()
    names = sum(util.tokens(t["name"]) + 2 for t in tools)
    out = {
        "instructions": util.tokens(mcp_server.INSTRUCTIONS),
        "tool_definitions": util.tokens(json.dumps(tools, ensure_ascii=False)),
        "tool_names": names,
        "tools": len(tools),
        "kernel": 0 if kernel.is_error else int(kernel.data.get("tokens") or 0),
    }
    # Claude Code loads an MCP server's tool definitions on use, so only names stay in front;
    # clients that load them all carry every definition on every call.
    out["per_call_claude_code"] = out["instructions"] + out["tool_names"]
    out["per_call_other"] = out["instructions"] + out["tool_definitions"]
    return out


# ------------------------------------------------------------------ Claude Code transcripts

def default_transcripts() -> str | None:
    """Where Claude Code keeps transcripts on this computer, if it does."""
    folder = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    return folder if os.path.isdir(folder) else None


@dataclass
class Line:
    tokens: int = 0
    usd: float = 0.0

    def add(self, tokens: float, usd: float) -> None:
        self.tokens += int(round(tokens))
        self.usd += usd

    def as_dict(self) -> dict:
        return {"tokens": self.tokens, "usd": round(self.usd, 4)}


@dataclass
class Day:
    lines: dict = field(default_factory=lambda: {name: Line() for name in LINES})
    calls: int = 0           # model calls in sessions that used the brain
    sessions: set = field(default_factory=set)
    all_usd: float = 0.0     # what those calls cost in all, brain or not
    briefs: int = 0          # brain answers written into conversations

    def as_dict(self) -> dict:
        return {"lines": {k: v.as_dict() for k, v in self.lines.items()},
                "calls": self.calls, "sessions": len(self.sessions),
                "all_usd": round(self.all_usd, 4), "briefs": self.briefs}


def _day(stamp: str) -> str:
    return str(stamp or "")[:10]


def _when(stamp: str) -> _dt.datetime | None:
    text = str(stamp or "").strip()
    if not text:
        return None
    try:
        moment = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=_dt.UTC)


def _tool_result_text(block) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text") or "") for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return ""


def _entries(path: str):
    """The lines of one transcript that matter for cost, parsed; the rest are skipped unread."""
    wanted = ('"assistant"', '"tool_result"', "compact_boundary", '"summary"')
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not any(mark in line for mark in wanted):
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and not entry.get("isSidechain"):
                yield entry


def _brain_prefixes(path: str) -> set[str]:
    """The MCP servers in this session that are brains: those with a gnomon_get_context tool."""
    found = set()
    for entry in _entries(path):
        if entry.get("type") != "assistant":
            continue
        for block in (entry.get("message") or {}).get("content") or []:
            name = str(block.get("name") or "") if isinstance(block, dict) else ""
            for tool in ("__gnomon_get_context", "__get_task_context"):  # new name, old one
                if block.get("type") == "tool_use" and name.endswith(tool):
                    found.add(name[: -len(tool) + 2])
    return found


def claude_code(folder: str, since_day: str, *, until_day: str | None = None,
                fixed_tokens: int = 0, kernel_tokens: int = 0, repo_root: str | None = None,
                token_factor: float = 1.0) -> dict:
    """Exact figures from Claude Code's transcripts for sessions that used a brain, by day.

    Every API call (one per assistant message id) is priced at its own model's rates. Brain
    answers held in the conversation count as re-read on each later call, or as rewritten when
    the call came after a pause longer than the cache's life; a compaction drops them."""
    days: dict[str, Day] = {}
    later_calls: list[int] = []
    sessions = 0
    since = str(since_day)[:10]
    until = str(until_day or "9999-12-31")[:10]
    cutoff = _dt.datetime.fromisoformat(since).replace(tzinfo=_dt.UTC).timestamp()
    root = os.path.normcase(os.path.abspath(repo_root)) if repo_root else None
    for base, _dirs, files in os.walk(folder):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(base, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    continue
                prefixes = _brain_prefixes(path)
            except OSError:
                continue
            if not prefixes:
                continue
            sessions += 1
            _session(path, prefixes, days, later_calls, since=since, until=until,
                     fixed=fixed_tokens, kernel=kernel_tokens, root=root,
                     token_factor=token_factor)
    return {"days": {d: days[d].as_dict() for d in sorted(days)}, "sessions": sessions,
            "later_calls": later_calls,
            "median_later_calls": (statistics.median(later_calls) if later_calls else None)}


def _session(path, prefixes, days, later_calls, *, since, until, fixed, kernel, root,
             token_factor):
    tools: dict[str, str] = {}       # tool_use id -> tool name
    held: list[list] = []            # [tokens, later calls] of brain answers in the context
    pending: list[float] = []        # brain answers not yet written to the cache
    seen: set[str] = set()
    last: _dt.datetime | None = None
    ttl = PAUSE_5M
    session_id = os.path.splitext(os.path.basename(path))[0]
    for entry in _entries(path):
        kind = entry.get("type")
        if kind == "summary" or entry.get("subtype") == "compact_boundary":
            later_calls.extend(n for _t, n in held)
            held, pending = [], []
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        if kind == "user" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                name = tools.get(str(block.get("tool_use_id") or ""), "")
                if any(name.startswith(p) for p in prefixes):
                    pending.append(util.tokens(_tool_result_text(block)) * token_factor)
            continue
        if kind != "assistant":
            continue
        for block in content or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[str(block.get("id") or "")] = str(block.get("name") or "")
        message_id = str(message.get("id") or "")
        usage = message.get("usage") or {}
        if not message_id or message_id in seen or not usage:
            continue
        seen.add(message_id)
        moment = _when(entry.get("timestamp"))
        day = _day(entry.get("timestamp"))
        if (usage.get("cache_creation") or {}).get("ephemeral_1h_input_tokens"):
            ttl = PAUSE_1H
        paused = bool(last and moment and (moment - last).total_seconds() > ttl)
        last = moment or last
        if not (since <= day <= until) or not (held or pending):
            # Calls before the first brain answer carry no brain content to count.
            for item in held:
                item[1] += 1
            held += [[t, 0] for t in pending]
            pending = []
            continue
        price = price_for(message.get("model")) or price_for(DEFAULT_MODEL)
        write = price.write_1h if ttl == PAUSE_1H else price.write_5m
        bucket = days.setdefault(day, Day())
        bucket.calls += 1
        bucket.sessions.add(session_id)
        bucket.all_usd += (int(usage.get("input_tokens") or 0) * price.input
                           + int(usage.get("output_tokens") or 0) * price.output
                           + int(usage.get("cache_read_input_tokens") or 0) * price.cache_read
                           + int(usage.get("cache_creation_input_tokens") or 0) * write) / 1e6
        here = fixed + (kernel if root and os.path.normcase(
            os.path.abspath(str(entry.get("cwd") or ""))).startswith(root) else 0)
        here *= token_factor
        held_tokens = sum(t for t, _n in held)
        if paused:
            bucket.lines["rewrites"].add(held_tokens + here, (held_tokens + here) * write / 1e6)
        else:
            bucket.lines["rereads"].add(held_tokens, held_tokens * price.cache_read / 1e6)
            bucket.lines["fixed"].add(here, here * price.cache_read / 1e6)
        for item in held:
            item[1] += 1
        if pending:
            fresh = sum(pending)
            bucket.lines["briefs"].add(fresh, fresh * write / 1e6)
            bucket.briefs += len(pending)
            held += [[t, 0] for t in pending]
            pending = []
    later_calls.extend(n for _t, n in held)


# ------------------------------------------------------------------ the report

def _since_day(days: int) -> str:
    return (util.now() - _dt.timedelta(days=max(1, int(days)) - 1)).strftime("%Y-%m-%d")


def daily(brain, days: int = 7, *, transcripts: str | None = None,
          model: str | None = None) -> dict:
    """What context cost each day, by line, with where each figure came from.

    Briefs come from the ledger (what the brain sent) and jobs from its model calls. With
    `transcripts` (Claude Code's folder), the fixed overhead, the first writes, the re-reads and
    the rewrites of Claude Code sessions are exact; other clients' re-reads are estimated."""
    ledger = brain.ledger
    k = factor(ledger)
    since_day = _since_day(days)
    over = overhead(brain)
    chosen = model or ((brain.config.data.get("costs") or {}).get("model")) or DEFAULT_MODEL
    price = price_for(chosen) or price_for(DEFAULT_MODEL)
    rows = ledger.packet_rows(since_day + "T00:00:00Z")
    found = None
    if transcripts:
        found = claude_code(transcripts, since_day, fixed_tokens=over["per_call_claude_code"],
                            kernel_tokens=over["kernel"], repo_root=brain.repo_root,
                            token_factor=k)
    later = (found or {}).get("median_later_calls") or DEFAULT_LATER_CALLS
    out: dict[str, dict] = {}

    def bucket(day: str) -> dict:
        return out.setdefault(day, {
            "lines": {name: Line() for name in LINES}, "sources": {}, "packets": 0,
            "brief_tokens": 0, "by_type": {}})

    for row in rows:
        day = _day(row["at"])
        b = bucket(day)
        tokens = (int(row["tokens"] or 0) + int(row.get("kernel_tokens") or 0)) * k
        b["packets"] += 1
        b["brief_tokens"] += int(round(tokens))
        kind = str((row.get("data") or {}).get("request_type") or "unknown")
        b["by_type"].setdefault(kind, []).append(int(round(tokens)))
        client = str(row.get("client") or "")
        if found is not None and "claude-code" in client.lower().replace(" ", "-"):
            continue  # exact figures for this one come from its transcript
        b["lines"]["briefs"].add(tokens, tokens * price.write_5m / 1e6)
        b["lines"]["rereads"].add(tokens * later, tokens * later * price.cache_read / 1e6)
        b["sources"]["rereads"] = "estimated"
    if found is not None:
        for day, figures in found["days"].items():
            b = bucket(day)
            for name in ("fixed", "briefs", "rereads", "rewrites"):
                line = figures["lines"][name]
                b["lines"][name].add(line["tokens"], line["usd"])
                b["sources"].setdefault(name, "claude code")
            b["claude_code"] = {"calls": figures["calls"], "sessions": figures["sessions"],
                                "all_usd": figures["all_usd"]}
    for row in ledger.model_usage(since_day):
        b = bucket(row["day"])
        b["lines"]["jobs"].add(int(row["tokens_in"]) + int(row["tokens_out"])
                               + int(row["cache_read"]) + int(row["cache_write"]),
                               float(row["cost"] or 0.0))
        b["sources"]["jobs"] = "measured"
        b.setdefault("jobs", []).append({k2: row[k2] for k2 in (
            "job", "model", "calls", "tokens_in", "tokens_out", "cost")})
    result = []
    for day in sorted(out):
        b = out[day]
        lines = {name: line.as_dict() for name, line in b["lines"].items()}
        result.append({
            "day": day, "lines": lines,
            "total_usd": round(sum(v["usd"] for v in lines.values()), 4),
            "total_tokens": sum(v["tokens"] for v in lines.values()),
            "sources": b["sources"], "packets": b["packets"],
            "brief_tokens": b["brief_tokens"],
            "median_brief_by_type": {t: int(statistics.median(v))
                                     for t, v in sorted(b["by_type"].items())},
            **({"claude_code": b["claude_code"]} if "claude_code" in b else {}),
            **({"jobs": b["jobs"]} if "jobs" in b else {}),
        })
    return {"days": result, "factor": calibration(ledger), "overhead": over,
            "model": chosen, "later_calls": later,
            "later_calls_source": "claude code" if found and found.get("median_later_calls")
            else "assumed",
            "transcripts": bool(found), "sessions_read": (found or {}).get("sessions", 0)}
