"""Run the recorded day (scripts/heartbeat_day.json) through heartbeat learning for real: the
real capture code and one distill on the heartbeat's own CLI and ingest model (Claude Haiku by
default), then score it against the ship gates (docs/dev/plans/heartbeat-learning-plan.md, 14.7).

It writes proposals into the Brain it runs on: use a scratch Brain, never your own.

    uv run python scripts/heartbeat_day_eval.py --env <scratch home>/.env [--out report.json]

It spends real tokens: one distill call per 60 items (the day has 50).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from workspace_server.app import open_runtime
from workspace_server.heartbeat import day_eval
from workspace_server.settings import Settings

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", required=True, help="the scratch home's .env")
    parser.add_argument("--day", default=os.path.join(HERE, "heartbeat_day.json"))
    parser.add_argument("--out", help="write the report here as JSON")
    parser.add_argument("--judge-tokens", type=int, default=3700, help="median beat judge cost")
    parser.add_argument("--beats-with-news", type=int, default=20)
    args = parser.parse_args()
    runtime = open_runtime(Settings.from_env(args.env))
    try:
        if runtime.heartbeat is None:
            print("This home has no heartbeat.", file=sys.stderr)
            return 2
        report = day_eval.run(
            runtime.heartbeat,
            day_eval.load(args.day),
            judge_tokens=args.judge_tokens,
            beats_with_news=args.beats_with_news,
        )
    finally:
        runtime.close()
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "misses"}, indent=1))
    print(f"{len(report['misses'])} misses" + (f"; see {args.out}" if args.out else ""))
    return 0 if all(report["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
