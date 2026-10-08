"""Run the safeguard evaluations on the packaged demo Brains and print (or save) a report.

    uv run python scripts/safeguards_eval.py                    # as the engine is now
    uv run python scripts/safeguards_eval.py --relevance-only   # constraints compete on relevance
    uv run python scripts/safeguards_eval.py --models <dir>     # match by meaning too
    uv run python scripts/safeguards_eval.py --markdown docs/evals/report.md

`--models` is a folder holding a downloaded embedding model, as it sits in a vault's
`.brain/models` (for example a demo home's `brain/vault/.brain/models`). Every run works on
scratch copies and a throwaway session ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS = os.path.join(ROOT, "packages", "brain", "tests", "evals")
BRAINS = os.path.join(ROOT, "brains")


def detectors():
    """The disagreement detectors to grade: today's sentence heuristic, and the baseline
    check when this engine has it."""
    from brainkit import review
    out = {"sentence heuristic (review.contradiction)":
           lambda a, b: review.contradiction(b, a)}
    tension = getattr(review, "tension", None)
    if tension is not None:
        out["baseline check (review.tension, checks 1 and 2)"] = (
            lambda a, b: tension(b, a) is not None)
    return out


def main(argv=None) -> int:
    from brainkit import safeguards_eval as se

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--relevance-only", action="store_true",
                        help="set every target constraint to load: on-demand first")
    parser.add_argument("--models", help="a folder holding a downloaded embedding model")
    parser.add_argument("--json", help="write the full results here")
    parser.add_argument("--markdown", help="write a short report here")
    args = parser.parse_args(argv)

    must = se.run_must_holds(BRAINS, se.load_spec(os.path.join(EVALS, "must_holds.json")),
                             relevance_only=args.relevance_only, models_dir=args.models)
    pairs = se.load_spec(os.path.join(EVALS, "tension_pairs.json"))["pairs"]
    tension = {name: se.tension_eval(pairs, detect) for name, detect in detectors().items()}
    time = se.run_time_cases(BRAINS, se.load_spec(os.path.join(EVALS, "time_cases.json"))["cases"],
                             models_dir=args.models)
    results = {"settings": {"relevance_only": args.relevance_only,
                            "semantic": bool(args.models)},
               "must_holds": must, "tension": tension, "time": time}

    matching = "words and meaning" if args.models else "words only"
    filed = "relevance only (set to on-demand)" if args.relevance_only else "as filed"
    lines = ["# Safeguard evaluations", "",
             f"Matching: {matching}. Constraints: {filed}.",
             "", "## Must-hold recall", "",
             f"- In-domain requests: {must['requests']}, recall {must['recall']:.0%}",
             f"- Decoys: {must['decoys']}, constraint included {must['decoy_rate']:.0%}", "",
             "| Brain | Note | Recall | Decoys including it |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['brain']} | `{r['note']}` | {r['recall']:.0%} | {r['decoy_rate']:.0%} |"
              for r in must["by_note"]]
    if must["misses"]:
        lines += ["", "Missed requests:", ""]
        lines += [f"- `{m['note']}`: \"{m['request']}\"" + (" (listed under Also relevant)"
                                                            if m["listed"] else "")
                  for m in must["misses"]]
    lines += ["", "## Disagreement detection", "",
              f"{len(pairs)} labeled pairs, {next(iter(tension.values()))['contradictions']} "
              "of them contradictions.", "",
              "| Detector | Recall | Precision |", "| --- | --- | --- |"]
    lines += [f"| {name} | {r['recall']:.0%} | {r['precision']:.0%} |"
              for name, r in tension.items()]
    lines += ["", "## Dated values", "",
              f"Newest value delivered without an unmarked older one: {time['score']:.0%} "
              f"of {len(time['cases'])} cases.", ""]
    lines += [f"- {c['id']}: " + ("ok" if c["ok"] else
                                  ("newest missing" if not c["newest_delivered"] else
                                   "older value delivered unmarked: "
                                   + ", ".join(c["older_unmarked"])))
              for c in time["cases"]]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(results, handle, indent=1)
    if args.markdown:
        os.makedirs(os.path.dirname(os.path.abspath(args.markdown)), exist_ok=True)
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
