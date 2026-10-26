"""Run the operating eval (brainkit/operating_eval.py) on real CLI models.

    uv run python scripts/operating_eval.py --model claude-haiku-5-5 --out F:/tmp/opeval

Each case gets a fresh copy of the test fixture Brain, with its startup files written and
one note seeded with an instruction aimed at the model. Claude Code runs headless in the
Brain's folder with only the Brain's MCP server; code scores what it did. It runs a real model
on this computer's Claude Code sign-in: about 2,000 to 8,000 tokens a case.

The Brain's server runs without the meaning model (words only), so the eval measures the
startup context and the tools, not retrieval by meaning.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain"))

from tests import fixture  # noqa: E402

from brainkit import operating_eval as oe  # noqa: E402
from brainkit import util  # noqa: E402
from brainkit.api import Brain  # noqa: E402

STRIP = ("CLAUDE", "ANTHROPIC", "MCP_", "CONTXT_", "WORKSPACE_", "BRAIN_")


def _brain(base: str) -> tuple[str, str, int]:
    """A fresh fixture Brain under `base`: (its folder, its MCP config, startup tokens)."""
    if os.path.isdir(base):
        shutil.rmtree(base)
    vault = fixture.build(base)
    oe.prepare(vault)
    brain = Brain(vault, embeddings=False)
    brain.write_kernel()
    folder = brain.repo_root
    brain.close()
    startup = 0
    for name in ("AGENTS.md",):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            startup += util.tokens(util.read_text(path))
    config = os.path.join(base, "mcp.json")
    with open(config, "w", encoding="utf-8") as handle:
        json.dump({"mcpServers": {oe.SERVER: {
            "command": sys.executable, "args": ["-m", "brainkit", "--vault", vault, "mcp"],
            "env": {"BRAIN_EMBEDDINGS": "0", "BRAIN_MODEL_SERVICE": "off",
                    "PYTHONPATH": os.path.join(ROOT, "packages", "brain", "src")}}}}, handle)
    return folder, config, startup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--case", action="append", help="run only these cases")
    args = parser.parse_args()
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP)}
    results = []
    for case in oe.CASES:
        if args.case and case.id not in args.case:
            continue
        folder, config, startup = _brain(os.path.join(args.out, args.model, case.id))
        found = oe.run_claude(case, cwd=folder, mcp_config=config, model=args.model, env=env)
        row = oe.score(case, found) | {"startup_file_tokens": startup}
        results.append(row)
        print(json.dumps({k: row[k] for k in ("case", "passed", "why", "calls", "tokens_in",
                                              "tokens_out", "first_packet_tokens")}),
              flush=True)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, f"results-{args.model}.json"), "w",
              encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    passed = sum(r["passed"] for r in results)
    print(f"{args.model}: {passed}/{len(results)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
