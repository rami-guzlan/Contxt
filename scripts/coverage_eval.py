"""How well packets' coverage lines point (v4 backend plan 16.1 and 16.7), without a model.

    uv run python scripts/coverage_eval.py                  # tuning Brains
    uv run python scripts/coverage_eval.py --split validation

For every labeled request on each generated Brain, zero-config and words only: how many
packets carry a coverage line, how many lines name a note the request needs or can use (the
rest cry wolf), and how many needed items the packet missed that a line names.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import answer_recall as ar  # noqa: E402
from brainkit import evalkit  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402

GENERAL = os.path.join(ROOT, "packages", "brain", "tests", "evals", "general")


def run(entry: dict) -> dict:
    vault = se.copy_vault(entry["vault"])
    out = {"packets": 0, "with_lines": 0, "note_lines": 0, "good_lines": 0, "time_lines": 0,
           "missed": 0, "named_missed": 0}
    try:
        evalkit.zero_config(vault)
        brain = se.open_brain(vault)
        try:
            for case in entry["cases"]:
                if not case.get("labeled", True):
                    continue
                data = brain.context(case["request"], record=False).data
                held = ar.packet(brain, case["request"])
                groups = [g if isinstance(g, list) else [g] for g in case.get("must") or []]
                wanted = {i for g in groups for i in g} | set(case.get("useful") or [])
                rows = (data.get("coverage") or {}).get("not_covered") or []
                named = {r["likely"].split("#", 1)[0] for r in rows
                         if r["fetch"].startswith("notes(")}
                out["packets"] += 1
                out["with_lines"] += bool(rows)
                out["note_lines"] += len(named)
                out["good_lines"] += len(named & wanted)
                out["time_lines"] += sum(r["fetch"].startswith("activity(") for r in rows)
                missed = [g for g in groups if not held & set(g)]
                out["missed"] += len(missed)
                out["named_missed"] += sum(1 for g in missed if named & set(g))
        finally:
            brain.close()
    finally:
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="tuning", choices=("tuning", "validation"))
    parser.add_argument("--set", action="append", default=[],
                        help="try a setting: NAME=VALUE (coverage.py constants)")
    args = parser.parse_args()
    from brainkit import coverage
    for pair in args.set:
        name, _, value = pair.partition("=")
        setattr(coverage, name, json.loads(value))
    total: dict = {}
    for entry in evalkit.generated_brains(GENERAL, [args.split]):
        found = run(entry)
        print(entry["name"], json.dumps(found))
        for key, value in found.items():
            total[key] = total.get(key, 0) + value
    print("all", json.dumps(total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
