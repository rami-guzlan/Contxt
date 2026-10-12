"""Score the knowledge agent on its labeled set (brain-logic plan 17.9).

    python scripts/agent_eval.py                 # the stand-in oracle: checks the harness
    python scripts/agent_eval.py --model local   # the shared model service's agent model
    python scripts/agent_eval.py --model claude  # Claude Code on this computer

Prints one line a case and the bars: agreement with the labels, valid answers, no direct
writes, impact lines that match a reference count, and hand-ups.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import agent_eval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="oracle", choices=sorted(agent_eval.MODELS))
    parser.add_argument("--only", default="", help="an action, to run its cases only")
    args = parser.parse_args()
    brains = os.path.join(ROOT, "brains")
    rows = []
    for case in agent_eval.load(brains):
        if args.only and case["action"] != args.only:
            continue
        row = agent_eval.run_case(brains, case, args.model)
        rows.append(row)
        print(f"{row['id']:<12} {row['action']:<16} candidates {row['candidates']:>2}  "
              f"right {row['right']}/{row['labeled']}  valid {row['valid']}  "
              f"ending {row['ending']}")
    print(json.dumps(agent_eval.score(rows), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
