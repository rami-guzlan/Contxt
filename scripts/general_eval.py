"""Score retrieval across many Brains, zero-config first (general-retrieval plan, stage 0).

    uv run python scripts/general_eval.py --models <dir>                 # tuning and validation
    uv run python scripts/general_eval.py --models <dir> --demos --misses
    uv run python scripts/general_eval.py --models <dir> --private <vault> --configured
    uv run python scripts/general_eval.py --models <dir> --sealed        # once per stage
    uv run python scripts/general_eval.py --scale 50,500,5000 --models <dir>

The generated Brains are in packages/brain/tests/evals/general (splits.json says which are
tuning, validation and sealed). Every Brain runs on a scratch copy as a new person's Brain
starts (no routing.json, no topics.md lines, no must-hold trigger words) unless --configured
adds the run as configured beside it. Every Brain is also asked the off-topic scoring set;
--null asks the calibration bank too. A --private vault (one with its own eval.json) is
reported as numbers only. Without --models, matching is by words only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import evalkit  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402

GENERAL = os.path.join(ROOT, "packages", "brain", "tests", "evals", "general")
RETRIEVAL = os.path.join(ROOT, "packages", "brain", "tests", "evals", "retrieval.json")
BRAINS = os.path.join(ROOT, "brains")
QUICK = ("dental", "bistro")


def suite(args) -> list[dict]:
    splits = ["tuning", "validation"] + (["sealed"] if args.sealed else [])
    entries = evalkit.generated_brains(GENERAL, splits)
    if args.quick:
        entries = [e for e in entries if e["name"] in QUICK]
    if args.only:
        wanted = set(args.only.split(","))
        entries = [e for e in entries if e["name"] in wanted]
    if args.demos or args.quick:
        entries += evalkit.demo_brains(BRAINS, se.load_spec(RETRIEVAL))
    for index, vault in enumerate(args.private or []):
        entries.append(evalkit.private_brain(vault, name=f"private-{index + 1}"))
    return entries


def scale(args) -> str:
    sources = [e["vault"] for e in evalkit.generated_brains(GENERAL)]
    sources += [os.path.join(BRAINS, n, "vault") for n in se.DEMO_BRAINS]
    requests = [c["request"] for c in evalkit.generated_brains(GENERAL)[0]["cases"]]
    lines = ["## Latency by Brain size", "",
             f"Matching: {'words and meaning' if args.models else 'words only'}. "
             f"{len(requests)} requests per size, each in its own conversation, after one "
             "warm-up request.", "",
             "| Notes | First brief (index built) ms | p50 ms | p95 ms |",
             "| --- | --- | --- | --- |"]
    for size in (int(s) for s in args.scale.split(",")):
        found = evalkit.latency_at(sources, size, requests, models_dir=args.models)
        lines.append(f"| {found['notes']} | {round(found['build_ms'])} | "
                     f"{round(found['p50'])} | {round(found['p95'])} |")
        print(lines[-1], flush=True)
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--models", help="a folder holding the embedding model (by meaning)")
    parser.add_argument("--demos", action="store_true", help="the demo Brains too")
    parser.add_argument("--private", action="append",
                        help="a private vault with its own eval.json (numbers only)")
    parser.add_argument("--sealed", action="store_true",
                        help="the sealed Brains too: read once, at the end of a stage")
    parser.add_argument("--configured", action="store_true",
                        help="also run each Brain as configured, beside zero-config")
    parser.add_argument("--null", action="store_true", help="ask the calibration bank too")
    parser.add_argument("--no-enrichment", action="store_true",
                        help="score each Brain as without a model: no enrichment fields")
    parser.add_argument("--quick", action="store_true", help="the CI quick set")
    parser.add_argument("--only", help="comma-separated generated Brain names")
    parser.add_argument("--misses", action="store_true",
                        help="list misses (never for sealed or private Brains)")
    parser.add_argument("--markdown", help="write the report to this file too")
    parser.add_argument("--json", help="write the numbers (no private rows) to this file")
    parser.add_argument("--scale", help="measure latency at these Brain sizes, e.g. 50,500")
    parser.add_argument("--minimums", help="write each Brain's zero-config rates to this "
                        "file, as the quick set's floor (tests/evals/general/minimums.json)")
    args = parser.parse_args(argv)
    if args.scale:
        text = scale(args)
        if args.markdown:
            with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        return 0
    entries = suite(args)
    off_topic = evalkit.off_topic_cases(os.path.join(GENERAL, "off_topic.json"))
    matching = "words and meaning" if args.models else "words only"
    sections = [f"# Retrieval across Brains ({matching})", ""]
    saved = {}
    modes = [("zero-config", False)] + ([("configured", True)] if args.configured else [])
    for label, configured in modes:
        started = time.perf_counter()
        # A generated Brain has no configuration to keep: configured is zero-config there.
        chosen = [e for e in entries if not configured or e["split"] in ("demo", "private")]
        if not chosen:
            continue
        results = evalkit.run_suite(
            chosen, models_dir=args.models, configured=configured, off_topic=off_topic,
            null_bank=args.null, enriched=not args.no_enrichment,
            progress=lambda name, label=label: print(f"  {label}: {name}", file=sys.stderr,
                                                     flush=True))
        took = time.perf_counter() - started
        sections.append(evalkit.markdown(results, title=f"{label.capitalize()} "
                                         f"({took:.0f} s)"))
        if args.misses:
            sections += [f"### Misses, {label}", "", evalkit.misses(results)]
        saved[label] = [evalkit.public(r) for r in results]
    text = "\n".join(sections)
    print(text)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(saved, handle, indent=1, default=str)
    if args.minimums:
        floors = {r["name"]: {m: round(evalkit.rate(pair), 3)
                              for m, pair in r["counts"].items() if pair[1]}
                  for r in saved["zero-config"] if not r.get("private")}
        with open(args.minimums, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"about": "The quick set's last measured zero-config rates, by meaning "
                       "(test_general_eval.py). Written by scripts/general_eval.py --quick "
                       "--null --models <dir> --minimums <this file>.",
                       "brains": floors}, handle, indent=1)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
