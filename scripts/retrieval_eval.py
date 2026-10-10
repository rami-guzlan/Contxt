"""Score retrieval on the packaged demo Brains' labeled requests and print (or save) a report.

    uv run python scripts/retrieval_eval.py                     # as the engine is now, by words
    uv run python scripts/retrieval_eval.py --models <dir>      # match by meaning too
    uv run python scripts/retrieval_eval.py --markdown docs/evals/retrieval-baseline.md

The cases live in packages/brain/tests/evals/retrieval.json: each request names the notes it
must get (any one of a group), the ones that help and the ones that would be noise, and about a
third are held out. Needed-note recall counts notes the brief carried or the session already
held (standing notes included); precision is the share of delivered notes that were needed or
useful; noise is the share of brief tokens spent on notes labeled noise. Every run works on
scratch copies and a throwaway session ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import safeguards_eval  # noqa: E402

CASES = os.path.join(ROOT, "packages", "brain", "tests", "evals", "retrieval.json")
BRAINS = os.path.join(ROOT, "brains")


def report(result: dict, *, models: bool) -> str:
    lines = ["# Retrieval on the demo Brains", "",
             f"Matching: {'words and meaning' if models else 'words only'}. "
             f"Request type read right: {result['type_accuracy']:.0%}.", "",
             "| Set | Cases | Needed-note recall | Whole | Listed too | Precision | Noise (tokens) "
             "| Avg tokens |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name in ("tuning", "holdout", "all"):
        m = result[name]
        lines.append(f"| {name} | {m['cases']} | {m['must_recall']:.0%} | {m['body_recall']:.0%} "
                     f"| {m['reachable']:.0%} "
                     f"| {m['precision']:.0%} | {m['noise_share']:.0%} | {m['avg_tokens']} |")
    lines += ["", "| Brain | Cases | Recall | Precision | Noise | Avg tokens |",
              "| --- | --- | --- | --- | --- | --- |"]
    for name, m in result["by_brain"].items():
        lines.append(f"| {name} | {m['cases']} | {m['must_recall']:.0%} | {m['precision']:.0%} "
                     f"| {m['noise_share']:.0%} | {m['avg_tokens']} |")
    misses = [r for r in result["rows"] if r["missed"] or r["noise"]]
    if misses:
        lines += ["", "## Misses and noise", ""]
        for r in misses:
            tag = " (held out)" if r["holdout"] else ""
            parts = []
            if r["missed"]:
                parts.append("missed " + "; ".join(" or ".join(g) for g in r["missed"]))
            if r["noise"]:
                parts.append("noise " + ", ".join(r["noise"]))
            lines.append(f"- {r['brain']}, {r['id']}{tag}: {'; '.join(parts)}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--models", help="a folder holding a downloaded embedding model")
    parser.add_argument("--rerank", action="store_true",
                        help="let the local cross-encoder rescore (needs it in --models)")
    parser.add_argument("--markdown", help="write the report to this file too")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    with open(CASES, encoding="utf-8") as handle:
        spec = json.load(handle)
    result = safeguards_eval.run_retrieval(BRAINS, spec, models_dir=args.models,
                                           rerank=args.rerank)
    if args.json:
        print(json.dumps(result, indent=1, default=str))
        return 0
    text = report(result, models=bool(args.models))
    print(text)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
