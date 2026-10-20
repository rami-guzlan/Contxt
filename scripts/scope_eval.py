"""Measure project-scoped requests and current values (Release 1 plan, M00 baseline).

    uv run python scripts/scope_eval.py --models <dir> [--markdown out.md] [--json out.json]

Without --models, matching is by words only. The spec is
packages/brain/tests/evals/scope.json (invented content); see brainkit/scope_eval.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import scope_eval  # noqa: E402

SPEC = os.path.join(ROOT, "packages", "brain", "tests", "evals", "scope.json")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--models", help="a folder holding the embedding model (by meaning)")
    parser.add_argument("--markdown", help="write the report to this file too")
    parser.add_argument("--json", help="write the rows to this file")
    args = parser.parse_args(argv)
    result = scope_eval.run(ROOT, scope_eval.load(SPEC), models_dir=args.models)
    matching = "words and meaning" if args.models else "words only"
    text = scope_eval.markdown(result, f"Project scope and current values ({matching})")
    print(text)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
