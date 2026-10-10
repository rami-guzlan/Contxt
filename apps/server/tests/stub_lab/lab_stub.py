"""A tiny stand-in for a test Lab, for Test the Brain's tests (invented content).

It keeps the results contract (docs/test-the-brain.md) the way a real runner would, and does
nothing else: no Brain, no models. It lives at <lab>/bin/lab_stub.py, with a one-line launcher
beside it, and writes under <lab>/results:

    status.json                       rewritten after every run
    runs/<run>/summary.json           the run's metrics, cost and failing cases
    runs/<run>/cases.jsonl            one case of each kind (retrieval, outcome, world, ...)
    runs/<run>/progress.jsonl         the events of the run (also appended to the --progress file)

Commands:  run <kind> [--suite <suite>] --progress <file>   |   cancel <run>   |   status --json

Run kinds: fast (quick, free), smoke (quick, paid), slow (runs until cancelled and leaves a
child process behind, to check cleanup), crash (stops with an error after it starts).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import subprocess
import sys
import time

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(LAB, "results")
STATUS = os.path.join(RESULTS, "status.json")
DELAY = float(os.environ.get("LAB_STUB_DELAY", "0.02"))

KINDS = [
    {
        "id": "fast",
        "name": "Fast check",
        "covers": "Retrieval and briefs on the saved cases; no model calls.",
        "paid": False,
    },
    {
        "id": "smoke",
        "name": "Outcomes smoke",
        "covers": "Ten cases with and without the Brain, three runs each.",
        "paid": True,
        "estimate": {"usd": 4.5, "seconds": 900},
    },
    {"id": "slow", "name": "Slow check", "covers": "Runs until cancelled.", "paid": False},
    {"id": "crash", "name": "Broken check", "covers": "Stops with an error.", "paid": False},
]
GATES = [
    {
        "id": "retrieval.needed_recall.heldout",
        "name": "Needed-note recall, held out",
        "bar": {"op": ">=", "value": 0.9},
        "kind": "hard",
        "source": "BL 5.9",
    },
    {
        "id": "retrieval.noise_share",
        "name": "Noise share of brief tokens",
        "bar": {"op": "<=", "value": 0.15},
        "kind": "hard",
        "source": "BL 5.9",
    },
    {
        "id": "briefs.tokens_vs_a",
        "name": "Brief tokens against setup A",
        "bar": {"op": "<=", "value": 1.0},
        "kind": "hard",
        "source": "BL 5.11.13",
    },
    {
        "id": "agent.precision",
        "name": "Knowledge agent precision",
        "bar": {"op": ">=", "value": 0.8},
        "kind": "watch",
        "source": "new",
    },
]


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    os.replace(temp, path)


def read_status() -> dict:
    try:
        with open(STATUS, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {
            "updated": now(),
            "engine_ref": "stub0001",
            "machine_setup": "laptop",
            "brain": "Stub Lab Brain",
            "run_kinds": KINDS,
            "ready": [
                {"suite": "retrieval", "setup": "laptop", "state": "ready"},
                {"suite": "briefs", "setup": "laptop", "state": "ready"},
                {
                    "suite": "outcomes",
                    "setup": "laptop",
                    "state": "waiting_step",
                    "note": "step 3b",
                },
                {"suite": "agent", "setup": "pc", "state": "pc_only"},
            ],
            "gates": GATES,
            "labels": {"labeled": 40, "total": 80, "sitting": {"state": "ready", "minutes": 20}},
            "qualification": [
                {
                    "step": "The gate",
                    "model": "small",
                    "state": "on",
                    "speed_ms": 40,
                    "budget_ms": 100,
                    "peak_ram_mb": 900,
                },
                {
                    "step": "The second pass",
                    "model": "small",
                    "state": "fallback",
                    "fallback": "Skipped",
                    "speed_ms": 400,
                    "budget_ms": 150,
                    "peak_ram_mb": 1100,
                },
            ],
            "lock": None,
        }


def save_status(status: dict) -> None:
    status["updated"] = now()
    write_json(STATUS, status)


class Run:
    def __init__(self, kind: str, suite: str | None, progress_file: str) -> None:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H-%M-%S")
        self.id = f"{stamp}_{kind}_A_stub_{random.randrange(16**6):06x}"
        self.kind = kind
        self.suite = suite
        self.dir = os.path.join(RESULTS, "runs", self.id)
        os.makedirs(self.dir, exist_ok=True)
        self.files = [os.path.join(self.dir, "progress.jsonl"), progress_file]
        self.done = 0
        self.failures = 0
        self.started = now()

    def event(self, name: str, **data) -> None:
        line = json.dumps({"event": name, "at": now(), "run": self.id, **data}) + "\n"
        for path in self.files:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)

    def cancelled(self) -> bool:
        return os.path.exists(os.path.join(self.dir, "cancel"))


def cases(run: Run) -> list[dict]:
    seen = sorted(name for name in os.environ)
    return [
        {
            "id": "RT-demo-1",
            "suite": "retrieval",
            "kind": "retrieval",
            "title": "Invite for the autumn open day",
            "sensitive": False,
            "pass": False,
            "measures": {"needed_recall": 0.5, "noise_share": 0.1},
            "view": {
                "request": "Write an invite for the autumn open day.",
                "brief": "# Task context\n\nHouse style: short, warm.\n",
                "notes": [
                    {
                        "id": "n-style",
                        "title": "House style",
                        "label": "needed_delivered",
                        "form": "body",
                        "scores": {"keyword": 0.8, "meaning": 0.7, "reranker": 0.9},
                        "why": "Names the tone to use.",
                        "tokens": 120,
                    },
                    {
                        "id": "n-dates",
                        "title": "Open day dates",
                        "label": "needed_missed",
                        "form": "none",
                        "scores": {"keyword": 0.2, "meaning": 0.4, "reranker": 0.3},
                        "why": "Below the cut.",
                        "tokens": 0,
                    },
                    {
                        "id": "n-menu",
                        "title": "Canteen menu",
                        "label": "noise",
                        "form": "pointer",
                        "scores": {"keyword": 0.3, "meaning": 0.2, "reranker": 0.2},
                        "why": "Matched the word open.",
                        "tokens": 20,
                    },
                ],
                "standards": [
                    {"id": "S1", "name": "Every note has a reason", "pass": True},
                    {"id": "S2", "name": "Under budget", "pass": False},
                ],
            },
        },
        {
            "id": "OC-demo-1",
            "suite": "outcomes",
            "kind": "outcome",
            "title": "Reply to a supplier",
            "sensitive": False,
            "pass": True,
            "measures": {"key_points_with": 3, "key_points_without": 1},
            "view": {
                "request": "Reply to the supplier about the late delivery.",
                "with": {"text": "Dear Sam, we agreed Tuesday delivery in the March note..."},
                "without": {"text": "Dear supplier, please send the delivery as soon as possible."},
                "key_points": [
                    {"text": "Mentions the agreed Tuesday date", "with": True, "without": False},
                    {"text": "Polite", "with": True, "without": True},
                ],
                "violations": [
                    {"rule": "No exclamation marks", "arm": "without", "text": "Please!"}
                ],
            },
        },
        {
            "id": "WL-demo-1",
            "suite": "worlds",
            "kind": "world",
            "title": "A changed price in the second month",
            "sensitive": False,
            "pass": False,
            "measures": {"found": 1, "missed": 1},
            "view": {
                "plants": [
                    {"id": "p1", "what": "Price rose from 10 to 12", "found": True},
                    {"id": "p2", "what": "Supplier changed", "found": False},
                ],
                "false_alarms": [{"what": "Flagged a spelling change"}],
                "suggestions": [
                    {"text": "Update the price note", "impact": ["1 note", "2 briefs"]}
                ],
            },
        },
        {
            "id": "SS-demo-1",
            "suite": "sessions",
            "kind": "session",
            "title": "A week of small requests",
            "sensitive": False,
            "pass": True,
            "measures": {"turns": 4},
            "view": {
                "turns": [
                    {"role": "user", "text": "What did we decide about the venue?"},
                    {"role": "brain", "text": "Brief: the hall, booked for the 12th."},
                ],
                "checks": [{"name": "Held the decision", "pass": True}],
            },
        },
        {
            "id": "TB-env",
            "suite": "doctor",
            "kind": "table",
            "title": "What the runner could see",
            "sensitive": False,
            "pass": True,
            "measures": {},
            "view": {
                "columns": ["Variable", "Value"],
                "rows": [
                    {
                        "label": name,
                        "expected": "",
                        "got": os.environ.get(name, "") if name == "LAB_CONFIG" else "(set)",
                        "pass": True,
                    }
                    for name in seen
                ],
                "env_names": seen,
            },
        },
    ]


def finish(run: Run, status: dict) -> None:
    rows = cases(run)
    with open(os.path.join(run.dir, "cases.jsonl"), "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    failing = [r for r in rows if r["pass"] is False]
    summary = {
        "run": run.id,
        "kind": run.kind,
        "started": run.started,
        "ended": now(),
        "config": {"engine_ref": "stub0001", "setup": "A", "machine_setup": "laptop"},
        "valid": True,
        "metrics": [
            {
                "id": "retrieval.needed_recall",
                "split": "heldout",
                "n": 45,
                "value": 0.78,
                "ci": [0.69, 0.86],
                "gate": "retrieval.needed_recall.heldout",
                "met": False,
                "met_confident": False,
            },
            {
                "id": "retrieval.noise_share",
                "n": 45,
                "value": 0.1,
                "ci": [0.06, 0.14],
                "gate": "retrieval.noise_share",
                "met": True,
                "met_confident": True,
            },
            {
                "id": "briefs.tokens_vs_a",
                "n": 45,
                "value": 0.92,
                "ci": [0.88, 0.97],
                "gate": "briefs.tokens_vs_a",
                "met": True,
                "met_confident": True,
            },
            {"id": "outcome.brain_effect", "n": 10, "value": 0.21, "ci": [0.05, 0.36]},
        ],
        "cost": {"usd_estimate": 4.5 if run.kind == "smoke" else 0.0, "tokens": 0, "seconds": 3},
        "failing_cases": [
            {"id": r["id"], "title": r["title"], "why": "see the case"} for r in failing
        ],
    }
    write_json(os.path.join(run.dir, "summary.json"), summary)
    for kind in status["run_kinds"]:
        if kind["id"] == run.kind:
            kind["last"] = {
                "run": run.id,
                "at": now(),
                "seconds": 3,
                "usd": summary["cost"]["usd_estimate"],
            }
    status["lock"] = None
    save_status(status)


def do_run(args: list[str]) -> int:
    if not args:
        print("run needs a kind", file=sys.stderr)
        return 2
    kind, suite, progress = args[0], None, os.path.join(RESULTS, "progress.jsonl")
    rest = args[1:]
    while rest:
        flag = rest.pop(0)
        if flag == "--suite" and rest:
            suite = rest.pop(0)
        elif flag == "--progress" and rest:
            progress = rest.pop(0)
        else:
            print(f"Unknown option {flag}", file=sys.stderr)
            return 2
    status = read_status()
    if kind not in {k["id"] for k in status["run_kinds"]}:
        print(f"No run kind {kind}.", file=sys.stderr)
        return 2
    holder = status.get("lock")
    if holder:
        print(
            f"The run lock is held by {holder['run'] if isinstance(holder, dict) else holder}.",
            file=sys.stderr,
        )
        return 3
    run = Run(kind, suite, progress)
    print(run.id, flush=True)
    status["lock"] = {"run": run.id, "since": now()}
    save_status(status)
    run.event("start", kind=kind, total=3)
    if kind == "crash":
        print("The stub broke on purpose.", file=sys.stderr)
        status["lock"] = None
        save_status(status)
        return 1
    if kind == "slow":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        write_json(os.path.join(run.dir, "pids.json"), {"runner": os.getpid(), "child": child.pid})
        run.event("suite_start", suite="slow", total=1000)
        for step in range(1200):
            if run.cancelled():
                run.event("cancelled", message="Stopped on request.")
                child.kill()
                status["lock"] = None
                save_status(status)
                return 0
            time.sleep(0.1)
            if step % 10 == 0:
                run.done += 1
                run.event("case_done", suite="slow", done=run.done, total=1000)
        return 0
    for suite_name, count in (("retrieval", 2), ("outcomes", 1)):
        if suite and suite != suite_name:
            continue
        run.event("suite_start", suite=suite_name, total=count)
        for index in range(count):
            time.sleep(DELAY)
            run.done += 1
            run.event(
                "case_done",
                suite=suite_name,
                done=index + 1,
                total=count,
                case=f"{suite_name}-{index}",
            )
        if suite_name == "retrieval":
            run.failures += 1
            run.event(
                "failure", suite=suite_name, case="RT-demo-1", message="Missed Open day dates"
            )
        run.event("suite_end", suite=suite_name, done=count, total=count, failures=run.failures)
    finish(run, status)
    run.event("end", done=run.done, failures=run.failures)
    return 0


def do_cancel(args: list[str]) -> int:
    if not args:
        print("cancel needs a run", file=sys.stderr)
        return 2
    folder = os.path.join(RESULTS, "runs", args[0])
    if not os.path.isdir(folder):
        print(f"No run {args[0]}.", file=sys.stderr)
        return 2
    with open(os.path.join(folder, "cancel"), "w", encoding="utf-8") as handle:
        handle.write("cancel\n")
    print(f"Cancelling {args[0]}.")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: lab (run <kind> | cancel <run> | status --json)", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    if command == "run":
        return do_run(rest)
    if command == "cancel":
        return do_cancel(rest)
    if command == "status":
        print(json.dumps(read_status()))
        return 0
    print(f"Unknown command {command}.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
