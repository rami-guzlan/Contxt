"""Context-usefulness evaluation: does the packet carry the notes the task needs, and little else?

The cases live in the vault (`eval.json`) because what counts as a useful note is knowledge
about this brain, not about the engine. Each case names, from the content of the notes:

    must     any-of groups a good packet has to deliver (standing notes count: the kernel
             already carries them)
    useful   notes that are welcome but not required
    noise    notes that are clearly off-task

and may pin a mode or a Focus. `style_ok` counts the house style (`style_topics` and
`style_notes`, the owner's list of what every piece of writing needs) as useful for a writing
task. Metrics are must-recall, precision (delivered notes that are must or useful)
and noise hits, reported separately for tuning cases and held-out cases. "Listed" recall also
counts notes the packet names under "Also relevant", which the agent can open with notes_get. Old note ids are
resolved through aliases.json, so renaming notes does not break a case.

Runs on a throwaway session ledger; it never touches real conversation history, and the
throwaway one (the requests and the briefs built from this brain) is removed when the run ends.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time

from .sessions import Ledger


def _resolve(ids, aliases):
    return [aliases.get(i, i) for i in ids]


def run(brain, path=None, holdout=None, verbose=False):
    path = path or os.path.join(brain.vault.root, "eval.json")
    with open(path, encoding="utf-8") as handle:
        spec = json.load(handle)
    st = brain.state()
    aliases = dict(st.config.aliases)
    style_topics = set(spec.get("style_topics") or st.config.routing.house_style_topics)
    style_notes = set(spec.get("style_notes") or [])
    # A throwaway ledger for the run; the brain's own comes back after, so a running app
    # that evaluates keeps its real history.
    real = brain._ledger
    scratch = tempfile.mkdtemp(prefix="brain-eval-")
    brain._ledger = Ledger(os.path.join(scratch, "sessions.sqlite"), 30)
    try:
        rows = _cases(brain, st, spec, holdout, verbose, aliases, style_topics, style_notes)
    finally:
        brain._ledger.close()
        brain._ledger = real
        shutil.rmtree(scratch, ignore_errors=True)
    return summarize(rows, spec.get("thresholds") or {})


def _cases(brain, st, spec, holdout, verbose, aliases, style_topics, style_notes):
    owner = st.config.owner
    rows = []
    for ordinal, case in enumerate(spec.get("cases") or []):
        if holdout is not None and bool(case.get("holdout")) != holdout:
            continue
        user = case.get("user") or owner
        session = f"sess-eval-{ordinal:02d}"
        setup_ids = set()
        if case.get("setup"):
            setup = brain.context(case["setup"], principal=user, session_id=session)
            setup_ids = set(setup.data.get("note_ids") or [])
        started = time.perf_counter()
        res = brain.context(case["request"], principal=user, session_id=session,
                            partition=case.get("partition") or None, explain=verbose)
        ms = (time.perf_counter() - started) * 1000
        data = res.data
        chain = data.get("scope_chain") or []
        standing = {n.id for n in st.index.notes.values() if n.standing and n.scope in chain}
        delivered = set(data.get("note_ids") or [])
        # A must-hold in the brief's "Must hold" section was delivered: its one line is the
        # point of the note, and the model can open the rest.
        must_held = set(data.get("must_hold_ids") or []) | set(data.get("must_hold_listed") or [])
        seen = delivered | must_held | set(data.get("held_ids") or []) | set(
            data.get("standing_ids") or []) | standing
        groups = [_resolve(g, aliases) for g in case.get("must") or []]
        hits = sum(1 for g in groups if seen & set(g))
        whole = seen - set(data.get("pointer_ids") or [])
        body_hits = sum(1 for g in groups if whole & set(g))
        must_ids = {i for g in groups for i in g}
        useful = must_ids | set(_resolve(case.get("useful") or [], aliases))
        if case.get("style_ok"):
            useful |= {n.id for n in st.index.notes.values() if n.route_key in style_topics}
            useful |= set(_resolve(sorted(style_notes), aliases))
        focus_id = data.get("focus_id")
        if focus_id:
            useful.add(focus_id)
        noise = set(_resolve(case.get("noise") or [], aliases)) & delivered
        good = len(delivered & useful)
        problems = []
        if case.get("mode") and data.get("mode") != case["mode"]:
            problems.append(f"mode {data.get('mode')!r}, expected {case['mode']!r}")
        if case.get("focus") and focus_id != aliases.get(case["focus"], case["focus"]):
            problems.append(f"focus {focus_id!r}, expected {case['focus']!r}")
        if case.get("no_repeats") and delivered & setup_ids:
            problems.append(f"repeated {sorted(delivered & setup_ids)}")
        missed = [g for g in groups if not seen & set(g)]
        reachable = seen | set(data.get("related_ids") or [])
        reach = sum(1 for g in groups if reachable & set(g))
        sizes = data.get("note_tokens") or {}
        rows.append({
            "id": case["id"], "holdout": bool(case.get("holdout")), "request": case["request"],
            "must": len(groups), "hits": hits, "body_hits": body_hits, "reach": reach,
            "delivered": len(delivered),
            "good": good,
            "noise": sorted(noise), "missed": missed, "problems": problems,
            "tokens": data.get("token_count"), "ms": round(ms, 1), "mode": data.get("mode"),
            "request_type": data.get("request_type"), "expected_type": case.get("type"),
            "noise_tokens": sum(int(sizes.get(i) or 0) for i in noise),
            "notes": data.get("note_ids"), "extra": sorted(delivered - useful),
            "must_holds": sorted(must_held),
            # Labeled "should get nothing", and whether the brief brought nothing (one line).
            "nothing_expected": bool(case.get("nothing")),
            # The local engine's mode and each layer's time, for the comparison of setups.
            "engine": {k: (data.get("engine") or {}).get(k)
                       for k in ("mode", "timings", "ceiling_hit")},
            "got_nothing": not delivered and not data.get("section_ids"),
            "trace": data.get("trace") if verbose else None,
        })
    return rows


def summarize(rows, thresholds):
    def agg(subset):
        must = sum(r["must"] for r in subset)
        hits = sum(r["hits"] for r in subset)
        # Precision and noise are measured on the requests that need something; a request
        # that should get nothing is measured by correct nothing and false nothing instead.
        scored = [r for r in subset if not r.get("nothing_expected")]
        delivered = sum(r["delivered"] for r in scored)
        good = sum(r["good"] for r in scored)
        scored_tokens = sum(r["tokens"] or 0 for r in scored)
        reach = sum(r.get("reach", r["hits"]) for r in subset)
        tokens = sum(r["tokens"] or 0 for r in subset)
        whole = sum(r.get("body_hits", r["hits"]) for r in subset)
        nothing = [r for r in subset if r.get("nothing_expected")]
        needed = [r for r in subset if r["must"]]
        return {
            "cases": len(subset),
            "must_recall": round(hits / must, 3) if must else 1.0,
            # Needed notes the brief carried whole (not only in short).
            "body_recall": round(whole / must, 3) if must else 1.0,
            "reachable": round(reach / must, 3) if must else 1.0,
            "precision": round(good / delivered, 3) if delivered else 1.0,
            "noise_hits": sum(len(r["noise"]) for r in subset),
            # The share of brief tokens spent on notes labeled noise (target 15% or less).
            "noise_share": round(sum(r.get("noise_tokens") or 0 for r in scored)
                                 / scored_tokens, 3) if scored_tokens else 0.0,
            "problems": sum(len(r["problems"]) for r in subset),
            "avg_tokens": round(tokens / len(subset)) if subset else 0,
            # Requests that should get nothing and got one line (target 95% or more), and
            # requests that needed something but got nothing (target 2% or less).
            "nothing_cases": len(nothing),
            "correct_nothing": round(sum(bool(r.get("got_nothing")) for r in nothing)
                                     / len(nothing), 3) if nothing else None,
            "false_nothing": round(sum(bool(r.get("got_nothing")) for r in needed)
                                   / len(needed), 3) if needed else 0.0,
        }
    tuning = [r for r in rows if not r["holdout"]]
    held = [r for r in rows if r["holdout"]]
    result = {"tuning": agg(tuning), "holdout": agg(held), "all": agg(rows), "rows": rows}
    failures = []
    t = thresholds
    if tuning and result["tuning"]["must_recall"] < t.get("must_recall", 0):
        failures.append(f"tuning must-recall {result['tuning']['must_recall']} "
                        f"< {t['must_recall']}")
    if tuning and result["tuning"]["precision"] < t.get("precision", 0):
        failures.append(f"tuning precision {result['tuning']['precision']} < {t['precision']}")
    if tuning and "max_noise" in t and result["tuning"]["noise_hits"] > t["max_noise"]:
        failures.append(f"tuning noise {result['tuning']['noise_hits']} > {t['max_noise']}: "
                        + ", ".join(f"{r['id']} {r['noise']}" for r in tuning if r["noise"]))
    if held and result["holdout"]["must_recall"] < t.get("holdout_must_recall", 0):
        failures.append(f"holdout must-recall {result['holdout']['must_recall']} "
                        f"< {t['holdout_must_recall']}")
    if held and result["holdout"]["precision"] < t.get("holdout_precision", 0):
        failures.append(f"holdout precision {result['holdout']['precision']} "
                        f"< {t['holdout_precision']}")
    for r in rows:
        failures += [f"{r['id']}: {p}" for p in r["problems"]]
    result["failures"] = failures
    return result


def report(result, show_holdout_detail=True) -> str:
    lines = []
    for name in ("tuning", "holdout", "all"):
        m = result[name]
        lines.append(f"{name:8s} cases {m['cases']:2d}  must-recall {m['must_recall']:.3f}  "
                     f"(listed {m['reachable']:.3f})  precision {m['precision']:.3f}  "
                     f"noise {m['noise_hits']:2d} ({m['noise_share']:.1%} of tokens)  "
                     f"avg tokens {m['avg_tokens']}")
    for r in result["rows"]:
        if r["holdout"] and not show_holdout_detail:
            continue
        if r["missed"] or r["noise"] or r["problems"]:
            tag = " [holdout]" if r["holdout"] else ""
            lines.append(f"- {r['id']}{tag}: recall {r['hits']}/{r['must']}, "
                         f"{r['good']}/{r['delivered']} useful, {r['tokens']} tokens")
            for group in r["missed"]:
                lines.append(f"    missed any of {group}")
            if r["noise"]:
                lines.append(f"    noise {r['noise']}")
            for problem in r["problems"]:
                lines.append(f"    {problem}")
    for failure in result["failures"]:
        if ":" not in failure.split(" ")[0]:
            lines.append("FAIL " + failure)
    return "\n".join(lines)
