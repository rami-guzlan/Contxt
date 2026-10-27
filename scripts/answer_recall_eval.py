"""Run the answer-recall eval (brainkit/answer_recall.py, v4 backend plan 16.4) on real CLI models.

    uv run python scripts/answer_recall_eval.py --model claude-haiku-5-5 --out F:/tmp/recall
    uv run python scripts/answer_recall_eval.py --split validation --model ... --out ...
    uv run python scripts/answer_recall_eval.py --private <vault> --model ... --out F:/tmp/x

Each generated Brain (packages/brain/tests/evals/general) runs on a scratch copy as a new
person's Brain starts (zero-config), with its startup files written. Every labeled request goes
through Claude Code headless in the Brain's folder with only the Brain's MCP server, words only;
code scores what reached the model. One worker per Brain. A --private vault (with its own
eval.json) runs as its owner has it set up, is reported as numbers only, and its results stay
out of the repository.

It runs a real model on this computer's Claude Code sign-in. It prints an estimate first,
refuses to start past --max-usd, and stops once the run's cost passes it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import answer_recall as ar  # noqa: E402
from brainkit import evalkit  # noqa: E402
from brainkit import operating_eval as oe  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402
from brainkit.api import Brain  # noqa: E402

GENERAL = os.path.join(ROOT, "packages", "brain", "tests", "evals", "general")
STRIP = ("CLAUDE", "ANTHROPIC", "MCP_", "CONTXT_", "WORKSPACE_", "BRAIN_")


class Budget:
    def __init__(self, limit: float):
        self.limit, self.spent, self.lock = limit, 0.0, threading.Lock()

    def add(self, cost) -> None:
        with self.lock:
            self.spent += float(cost or 0)

    def over(self) -> bool:
        with self.lock:
            return self.spent > self.limit


def _config(vault: str, folder: str) -> str:
    path = os.path.join(folder, "mcp.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"mcpServers": {oe.SERVER: {
            "command": sys.executable, "args": ["-m", "brainkit", "--vault", vault, "mcp"],
            "env": {"BRAIN_EMBEDDINGS": "0", "BRAIN_MODEL_SERVICE": "off",
                    "PYTHONPATH": os.path.join(ROOT, "packages", "brain", "src")}}}}, handle)
    return path


def run_brain(entry: dict, cases: list[dict], *, model: str, env: dict,
              budget: Budget, scopes: dict | None = None) -> dict:
    vault = se.copy_vault(entry["vault"])
    scratch = os.path.dirname(vault)
    try:
        if not entry["private"]:  # a person's own Brain runs as they have it set up
            evalkit.zero_config(vault)
        for note_id, scope in (scopes or {}).items():  # drafted scopes, as if kept
            se.set_meta(vault, [note_id], must_applies_when=scope["applies_when"],
                        must_not_when=scope.get("not_when") or None)
        brain = Brain(vault, embeddings=False)
        brain.write_kernel()
        folder = brain.repo_root
        brain.close()
        config = _config(vault, scratch)
        sessions = []
        for case in cases:
            if budget.over():
                break
            lines, error = oe.run_lines(case["request"], cwd=folder, mcp_config=config,
                                        model=model, env=env)
            try:
                s = ar.parse(lines or [])
            except (ValueError, TypeError, AttributeError, KeyError) as failed:
                # One unreadable transcript is one failed request, not a lost run.
                s = ar.Session(error=f"could not read the transcript: {failed}")
            s.error = s.error or (error if not s.answer else "")
            budget.add(s.cost)
            sessions.append((case, s))
        brain = se.open_brain(vault)
        try:
            st = brain.state()
            # Only a Brain whose requests are labeled with their must-holds counts wrong ones.
            must_holds = ({n.id for n in st.index.notes.values() if n.must_hold}
                          if entry.get("must_hold_labels") else set())
            rows = []
            for case, s in sessions:
                packet: set[str] = set()
                for request in s.requests:
                    packet |= ar.packet(brain, request)
                row = ar.score(case, packet=packet, fetched=s.fetched, must_holds=must_holds,
                               fetches=s.fetches, tokens=s.tokens, cost=s.cost, error=s.error)
                row["context_calls"] = len(s.requests)
                rows.append(row)
        finally:
            brain.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return {"name": entry["name"], "split": entry["split"], "private": entry["private"],
            "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split", default="tuning", choices=("tuning", "validation"))
    parser.add_argument("--private", help="a vault with its own eval.json: numbers only")
    parser.add_argument("--limit", type=int, help="at most this many requests a Brain")
    parser.add_argument("--max-usd", type=float, default=1.0)
    parser.add_argument("--scopes", help="drafted must-hold scopes (scope_drafts.py), as if kept")
    args = parser.parse_args()
    out = os.path.abspath(args.out)
    if args.private:
        if out.startswith(os.path.abspath(ROOT)):
            print("Keep a private Brain's results outside the repository: choose another --out.")
            return 2
        entries = [evalkit.private_brain(args.private)]
    else:
        entries = evalkit.generated_brains(GENERAL, [args.split])
    plan = []
    for entry in entries:
        cases = [c for c in entry["cases"] if c.get("labeled", True)]
        plan.append((entry, cases[:args.limit] if args.limit else cases))
    count = sum(len(c) for _, c in plan)
    estimate = count * ar.PER_CASE_USD
    print(f"{len(plan)} Brains, {count} requests, about ${estimate:.2f} on {args.model}.")
    if estimate > args.max_usd:
        print(f"That is past ${args.max_usd:.2f}: lower --limit or raise --max-usd.")
        return 2
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP)}
    budget = Budget(args.max_usd)
    scopes = {}
    if args.scopes:
        with open(args.scopes, encoding="utf-8") as handle:
            scopes = json.load(handle)
    with ThreadPoolExecutor(max_workers=len(plan) or 1) as pool:
        brains = list(pool.map(lambda p: run_brain(p[0], p[1], model=args.model, env=env,
                                                   budget=budget,
                                                   scopes=scopes.get(p[0]["name"])), plan))
    found = ar.summary(brains)
    found |= {"model": args.model, "split": "private" if args.private else args.split,
              "stopped_at_budget": budget.over(), "estimate_usd": round(estimate, 4)}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"summary-{args.model}.json"), "w", encoding="utf-8") as handle:
        json.dump(found, handle, indent=2)
    if not args.private:
        with open(os.path.join(out, f"rows-{args.model}.json"), "w", encoding="utf-8") as handle:
            json.dump(brains, handle, indent=2)
    print(json.dumps({k: found[k] for k in ("all", "worst", "stopped_at_budget")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
