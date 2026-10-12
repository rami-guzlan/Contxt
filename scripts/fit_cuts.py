"""Fit a cut on the tuning part of the demo set (brain-logic plan 5.11.10): the defaults.

    uv run python scripts/fit_cuts.py --models <embedding models folder> [--setup B]
        [--cut relevance] [--values 0.02,0.05,0.1,...] [--fixed gate=0.4] [--markdown <file>]

Runs one setup (engine_compare.py's A to E) at each value of one cut, on the labeled requests
and the must-hold decoys, and judges each value on the tuning part only: the most gates of
5.11.13 cleared (needed-note recall 90%, noise 15%, decoys 2%, correct nothing 95%, false
nothing 2%), then the highest needed-note recall, then the fewest tokens. The held-out part is
looked at once, for the chosen value only. A person's Brain keeps its own cuts, fitted on its
own labels; the defaults in `engine.CUTS` change from this by hand, as a reviewed change.
Needs a verified local model service.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine_compare

VALUES = "0.02,0.05,0.1,0.15,0.2,0.3,0.4,0.5"


def gates(stats: dict, decoys: float | None) -> list[str]:
    """The gates a split's numbers miss."""
    g = engine_compare.GATES
    missed = []
    if (stats.get("must_recall") or 0) < g["held_out_recall"]:
        missed.append("recall")
    if (stats.get("noise_share") or 0) > g["noise"]:
        missed.append("noise")
    if decoys is not None and decoys > g["decoys"]:
        missed.append("decoys")
    if stats.get("correct_nothing") is not None and stats["correct_nothing"] < g[
            "correct_nothing"]:
        missed.append("correct nothing")
    if (stats.get("false_nothing") or 0) > g["false_nothing"]:
        missed.append("false nothing")
    return missed


def choose(rows: list[dict]) -> dict:
    """The value that clears the most gates on tuning, then recalls most, then costs least."""
    return min(rows, key=lambda r: (len(r["missed"]), -(r["tuning"].get("must_recall") or 0),
                                    r["tuning"].get("avg_tokens") or 0))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", help="a folder holding the bge-small embedding model")
    parser.add_argument("--setup", default="B", choices=sorted(engine_compare.SETUPS))
    parser.add_argument("--cut", default="relevance")
    parser.add_argument("--values", default=VALUES)
    parser.add_argument("--fixed", default="", help="other cuts held fixed: gate=0.4")
    parser.add_argument("--markdown", help="write the report to this file too")
    args = parser.parse_args(argv)
    fixed = engine_compare.parse_cuts(args.fixed)
    rows = []
    for value in [float(v) for v in args.values.split(",") if v.strip()]:
        cuts = dict(fixed, **{args.cut: value})
        found = engine_compare.run_setup(args.setup, engine_compare.EMBEDDINGS[0], args.models,
                                         cuts)
        if "skipped" in found:
            print(f"Skipped: {found['skipped']}")
            return 1
        found["value"] = value
        found["missed"] = gates(found["tuning"], found["decoys"])
        rows.append(found)
        t = found["tuning"]
        print(f"{args.cut} {value:g}: tuning recall {t['must_recall']:.0%}, noise "
              f"{t['noise_share']:.0%}, correct nothing {pct(t.get('correct_nothing'))}, "
              f"false nothing {pct(t.get('false_nothing'))}, tokens {t['avg_tokens']}", flush=True)
    best = choose(rows)
    text = report(args, fixed, rows, best)
    print(text)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return 0


def pct(value) -> str:
    return "-" if value is None else f"{value:.0%}"


def report(args, fixed: dict, rows: list[dict], best: dict) -> str:
    held = f", with {', '.join(f'{k} {v:g}' for k, v in fixed.items())}" if fixed else ""
    lines = [f"# Fitting the {args.cut} cut, setup {args.setup}{held} (brain-logic plan 5.11.10)",
             "", "Judged on the tuning part only; the held-out part is read once, for the chosen "
             "value.", "",
             f"| {args.cut} | Tuning recall | Noise | Decoys | Correct nothing | False nothing "
             "| Tokens | Brief ms p50 / p95 | Tuning gates missed |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        t = r["tuning"]
        p50, p95 = r["brief_ms"]
        lines.append(f"| {r['value']:g} | {t['must_recall']:.0%} | {t['noise_share']:.0%} "
                     f"| {pct(r['decoys'])} | {pct(t.get('correct_nothing'))} "
                     f"| {pct(t.get('false_nothing'))} | {t['avg_tokens']} | {p50} / {p95} "
                     f"| {', '.join(r['missed']) or 'none'} |")
    lines += ["", f"Chosen: {args.cut} {best['value']:g}. Held out, read once: needed-note recall "
              f"{best['held_out_recall']:.0%}; over all requests: recall {best['recall']:.0%}, "
              f"correct nothing {pct(best['correct_nothing'])}, false nothing "
              f"{pct(best['false_nothing'])}, {best['tokens']} tokens a brief."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
