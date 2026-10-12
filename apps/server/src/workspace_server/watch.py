"""Watch it work: one request drawn stage by stage, with its counts in and out.

The stages are the System Map's: gate, admission, wide search, relevance cut, second pass and
link loop, fit. A typed request runs read only: the Brain's `context` call with `record=False`,
so it writes no ledger row, no delivery and no usage count (it is marked as a test, with the
reserved client below, so nothing that ever lists it can mistake it for a real request).

What main can show is drawn from the routing trace it already keeps. A stage that needs the
local retrieval engine (build step 3b) is drawn as waiting, with the build step named; when the
engine is part of the install, its per-layer record in the brief's data (`engine`) fills those
stages, and only `engine_stages` changes. A runner's own record of a case (`view.stages`) is
drawn as it gives it.
"""

from __future__ import annotations

import time
from typing import Any

TEST_CLIENT = "contxt-test"  # the reserved app name of a request this page made
WAITS = "Waits for the retrieval engine (build step 3b)"

STAGES = (
    ("read", "Read the request"),
    ("gate", "Gate"),
    ("admission", "Admission"),
    ("search", "Wide search"),
    ("cut", "Relevance cut"),
    ("second", "Second pass and link loop"),
    ("fit", "Fit"),
)


def stage(
    stage_id: str,
    state: str,
    *,
    in_: int | None = None,
    out: int | None = None,
    ms: float | None = None,
    note: str = "",
    dropped: list[dict[str, str]] | None = None,
    added: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    names = dict(STAGES)
    return {
        "id": stage_id,
        "name": names.get(stage_id, stage_id),
        "state": state,  # done | waiting | skipped
        "in": in_,
        "out": out,
        "ms": ms,
        "note": note,
        "dropped": dropped or [],
        "added": added or [],
    }


def _waiting(stage_id: str, today: str = "") -> dict[str, Any]:
    return stage(stage_id, "waiting", note=WAITS + (f". {today}" if today else ""))


def _reason_rows(decisions: list[str], titles: dict[str, str], *words: str) -> list[dict[str, str]]:
    rows = []
    for line in decisions:
        item, _, why = line.partition(": ")
        if any(word in why for word in words):
            rows.append({"id": item, "title": titles.get(item, item), "why": why})
    return rows


def engine_stages(engine: Any) -> dict[str, dict[str, Any]]:
    """The stages the local engine's own record fills, by stage id; {} when it did not run.

    The engine writes a summary into the brief's data (`engine`): its mode, the gate's answer,
    the time of each layer (`timings`: gate, find, cut, second_pass, fit), the link loop's
    rounds, how many candidates it looked at and what became of them (`outcomes`)."""
    if not isinstance(engine, dict) or engine.get("mode") != "on":
        return {}
    timings = engine.get("timings") or {}
    outcomes = engine.get("outcomes") or {}
    total = int(engine.get("candidates") or sum(int(v) for v in outcomes.values()))
    kept = max(0, total - int(outcomes.get("out", 0)))
    gate = engine.get("gate") or {}
    out: dict[str, dict[str, Any]] = {}
    if "gate" in timings:
        passed = bool(gate.get("passed", True))
        said = (
            f" (probability {gate['yes']:.2f}, cut {gate['cut']:.2f})"
            if "yes" in gate and "cut" in gate
            else ""
        )
        out["gate"] = stage(
            "gate",
            "done",
            in_=1,
            out=1 if passed else 0,
            ms=timings["gate"],
            note=(
                "The Brain holds something for this request"
                if passed
                else "Nothing to send for this request"
            )
            + said
            + ".",
        )
    if "find" in timings:
        out["search"] = stage(
            "search", "done", out=total, ms=timings["find"], note=f"{total} candidate(s) looked at."
        )
    if "cut" in timings:
        out["cut"] = stage(
            "cut",
            "done",
            in_=total,
            out=kept,
            ms=timings["cut"],
            note=f"{kept} cleared the relevance cut.",
        )
    if "second_pass" in timings:
        rounds = int(engine.get("rounds") or 0)
        out["second"] = stage(
            "second",
            "done",
            in_=kept,
            out=kept,
            ms=timings["second_pass"],
            note=f"{rounds} round(s) of the link loop.",
        )
    if "fit" in timings:
        out["fit"] = stage("fit", "done", ms=timings["fit"])
    return out


def _fallback_note(engine: Any) -> str:
    """Why the engine, though installed, did not decide this brief."""
    if isinstance(engine, dict) and engine.get("mode") == "fallback":
        why = str(engine.get("reason") or "no verified model service is running")
        return f"The retrieval engine is part of this install but is not running here: {why}."
    return ""


def from_trace(
    data: dict[str, Any], *, titles: dict[str, str], live_notes: int, ms: float
) -> dict[str, Any]:
    """The stages of one routed request from the Brain's `context` data (explain=True)."""
    trace = data.get("trace") or {}
    signals = trace.get("signals") or {}
    note_scores = trace.get("note_scores") or []
    section_scores = trace.get("section_scores") or []
    decisions = [str(d) for d in trace.get("decisions") or []]
    must = list(data.get("must_hold_ids") or []) + list(data.get("must_hold_listed") or [])
    delivered_notes = list(data.get("note_ids") or [])
    delivered_sections = list(data.get("section_ids") or [])
    related = list(data.get("related_ids") or [])
    held = list(data.get("held_ids") or [])
    candidates = len(note_scores) + len(related) + len(section_scores)
    engine = engine_stages(data.get("engine"))
    titles = dict(titles)
    for part in section_scores:
        titles.setdefault(part["id"], part.get("title") or part["id"])

    read = stage(
        "read",
        "done",
        in_=1,
        out=len(data.get("topics") or []),
        note=(
            f"Read as {data.get('task_type') or 'a task'}"
            + (f", {data.get('scale')}" if data.get("scale") else "")
            + f". It routes to {len(data.get('topics') or [])} topic(s)."
        ),
    )
    admission = stage(
        "admission",
        "done",
        in_=len(data.get("scope_chain") or []),
        out=len(must),
        note=f"{len(must)} must-hold(s) in play for this request, whatever relevance says.",
    )
    search = stage(
        "search",
        "done",
        in_=live_notes,
        out=candidates,
        note=f"{candidates} candidate(s) scored from {live_notes} live notes.",
        added=[
            {"id": i, "title": titles.get(i, i), "why": "listed as also relevant"} for i in related
        ],
    )
    skipped = _reason_rows(decisions, titles, "skipped", "already delivered", "already given")
    fit = stage(
        "fit",
        "done",
        in_=len(note_scores) + len(section_scores),
        out=len(delivered_notes) + len(delivered_sections),
        note=(
            f"{data.get('token_count') or 0} tokens in the brief"
            + (
                f" of a {data.get('note_budget')} token budget for notes"
                if data.get("note_budget")
                else ""
            )
            + "."
        ),
        dropped=skipped,
    )
    out = {
        "read": read,
        "gate": _waiting("gate", f"Today the router answers: {data.get('mode') or 'unknown'}."),
        "admission": admission,
        "search": search,
        "cut": _waiting("cut", "Today the router's own scoring keeps the best notes."),
        "second": _waiting("second"),
        "fit": fit,
    }
    for stage_id, found in engine.items():  # the engine's record fills a waiting stage
        if out[stage_id]["state"] == "waiting":
            out[stage_id] = found
        else:  # a stage main already draws keeps its counts and gains the engine's time
            out[stage_id].update({k: v for k, v in found.items() if v not in (None, "", [])})
    reason = _fallback_note(data.get("engine"))
    if reason:
        for stage_id in ("gate", "cut", "second"):
            if out[stage_id]["state"] == "waiting":
                out[stage_id]["note"] = reason
    delivered = [
        {
            "id": i,
            "title": titles.get(i, i),
            "outcome": "delivered",
            "why": next((d.partition(": ")[2] for d in decisions if d.startswith(i + ":")), ""),
        }
        for i in delivered_notes
    ]
    delivered += [
        {
            "id": i,
            "title": titles.get(i, i),
            "outcome": "already held",
            "why": "given earlier in the session",
        }
        for i in held
    ]
    delivered += [
        {"id": i, "title": titles.get(i, i), "outcome": "must hold", "why": "a must-hold in play"}
        for i in data.get("must_hold_ids") or []
    ]
    return {
        "test": True,
        "client": TEST_CLIENT,
        "read_only": True,
        "mode": data.get("mode"),
        "tokens": data.get("token_count"),
        "ms": round(ms, 1),
        "engine": bool(engine),
        "signals": {k: v for k, v in signals.items() if v},
        "stages": [out[sid] for sid, _name in STAGES],
        "notes": delivered,
    }


def run_request(adapter: Any, text: str) -> dict[str, Any]:
    """Route one request on this app's own Brain and draw it. Nothing is recorded."""
    started = time.perf_counter()
    found = adapter.brain.context(text, explain=True, record=False, include_kernel=False)
    ms = (time.perf_counter() - started) * 1000
    if found.is_error:
        raise ValueError(found.text)
    state = adapter.brain.state()
    titles = {n.id: n.title for n in state.index.notes.values()}
    return from_trace(found.data, titles=titles, live_notes=len(state.index.notes), ms=ms)


def from_record(case: dict[str, Any]) -> dict[str, Any]:
    """A runner's own record of a case, drawn without running anything. A runner may give its
    stages (`view.stages`); else the delivered and missed notes of a retrieval case are shown."""
    view = case.get("view") or {}
    given = view.get("stages")
    if isinstance(given, list) and given:
        stages = []
        for item in given:
            if not isinstance(item, dict):
                continue
            stages.append(
                stage(
                    str(item.get("id") or item.get("name") or "stage"),
                    str(item.get("state") or "done"),
                    in_=item.get("in"),
                    out=item.get("out"),
                    ms=item.get("ms"),
                    note=str(item.get("note") or ""),
                    dropped=list(item.get("dropped") or []),
                    added=list(item.get("added") or []),
                )
            )
            stages[-1]["name"] = str(item.get("name") or stages[-1]["name"])
    else:
        notes = view.get("notes") or []
        delivered = [n for n in notes if n.get("form") in ("body", "pointer")]
        missed = [n for n in notes if n.get("label") == "needed_missed"]
        by_id = {
            "read": stage(
                "read", "done", in_=1, out=1, note="From the saved case; nothing was run again."
            ),
            "fit": stage(
                "fit",
                "done",
                in_=len(notes),
                out=len(delivered),
                note=f"{len(delivered)} delivered, {len(missed)} needed but missed.",
                dropped=[
                    {"id": n.get("id", ""), "title": n.get("title", ""), "why": n.get("why", "")}
                    for n in missed
                ],
            ),
        }
        stages = [
            by_id.get(sid) or stage(sid, "skipped", note="Not in this saved case's record.")
            for sid, _name in STAGES
        ]
    return {
        "test": True,
        "client": TEST_CLIENT,
        "read_only": True,
        "from_record": True,
        "stages": stages,
        "notes": [
            {
                "id": n.get("id", ""),
                "title": n.get("title", ""),
                "outcome": n.get("label", ""),
                "why": n.get("why", ""),
            }
            for n in view.get("notes") or []
        ],
    }
