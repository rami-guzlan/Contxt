"""Draft must-hold scopes with a model (brainkit/rule_scope.py, v4 backend plan 16.3).

    uv run python scripts/scope_drafts.py --model claude-haiku-5-5 --out F:/tmp/scopes.json
    uv run python scripts/scope_drafts.py --split validation --model ... --out ...
    uv run python scripts/scope_drafts.py --vault <a Brain's vault> --propose --model ...

For the generated Brains it writes the drafts to a file, for the answer-recall eval to apply as
if the owner had kept them (`answer_recall_eval.py --scopes`). With --vault and --propose it
proposes each draft to that Brain, where it waits in Catch up. Each draft is one Claude Code
call with no tools, on this computer's sign-in.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import evalkit, rule_scope  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402

GENERAL = os.path.join(ROOT, "packages", "brain", "tests", "evals", "general")
STRIP = ("CLAUDE", "ANTHROPIC", "MCP_", "CONTXT_", "WORKSPACE_", "BRAIN_")


def draft(note, *, model: str, env: dict) -> tuple[dict | None, float]:
    # No tools and none of the person's own MCP servers: one plain answer.
    # The prompt goes on stdin: on Windows the shell would cut an argument at its first newline.
    command = ["claude", "-p", "--model", model, "--output-format",
               "json", "--mcp-config", '{"mcpServers": {}}', "--strict-mcp-config",
               "--disallowedTools", "Bash,Edit,Write,MultiEdit,Read,Glob,Grep,WebFetch,"
               "WebSearch,Task,NotebookEdit,TodoWrite", "--no-session-persistence"]
    try:
        proc = subprocess.run(command, input=rule_scope.prompt(note), env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", timeout=180, shell=os.name == "nt")
        found = json.loads(proc.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError):
        return None, 0.0
    return rule_scope.parse(str(found.get("result") or "")), float(
        found.get("total_cost_usd") or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", help="where the drafts go (generated Brains)")
    parser.add_argument("--split", default="tuning", choices=("tuning", "validation"))
    parser.add_argument("--vault", help="one Brain's vault instead of the generated Brains")
    parser.add_argument("--propose", action="store_true", help="propose to --vault's Brain")
    args = parser.parse_args()
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP)}
    if args.vault:
        entries = [{"name": "brain", "vault": args.vault}]
    else:
        entries = evalkit.generated_brains(GENERAL, [args.split])
    drafts: dict = {}
    spent = 0.0
    for entry in entries:
        vault = entry["vault"] if args.propose else se.copy_vault(entry["vault"])
        brain = se.open_brain(vault)
        try:
            for note in rule_scope.due(brain.state()):
                found, cost = draft(note, model=args.model, env=env)
                spent += cost
                if found is None:
                    print(f"{entry['name']} {note.id}: no usable draft")
                    continue
                drafts.setdefault(entry["name"], {})[note.id] = found
                if args.propose:
                    made = brain.propose_must_hold_scope(note.id, found["applies_when"],
                                                         found["not_when"])
                    print(f"{note.id}: {'proposed' if not made.is_error else made.text}")
        finally:
            brain.close()
            if vault != entry["vault"]:
                shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(drafts, handle, indent=2)
    print(f"{sum(len(v) for v in drafts.values())} drafts, ${spent:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
