"""Does the world view earn its place? (v4 backend plan, 13.7)

    uv run python scripts/world_eval.py --label with --out F:/tmp/world
    uv run python scripts/world_eval.py --label without --code <checkout>/packages/brain/src \
        --out F:/tmp/world

Twenty questions labelled before any run (scripts/world_eval_questions.json): 8 about how
entries relate, 8 about time, 4 for orientation. Each runs on a fresh copy of the test fixture
Brain, seeded here with relationships, a superseded day rate, a dispute and dated decisions,
through Claude Code headless in the Brain's folder with only the Brain's MCP server (the
operating eval's harness, brainkit/operating_eval.py). `--code` points the Brain at another
checkout's brainkit: the code from just before section 13 is the run without the world view.
Scored by code: an answer is correct when it holds an expected term. Stops if the spend passes
`--cap` dollars. Claude Haiku by default.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain"))

from tests import fixture  # noqa: E402

from brainkit import operating_eval as oe  # noqa: E402
from brainkit import util  # noqa: E402

STRIP = ("CLAUDE", "ANTHROPIC", "MCP_", "CONTXT_", "WORKSPACE_", "BRAIN_")
QUESTIONS = os.environ.get("WORLD_EVAL_QUESTIONS") or os.path.join(
    ROOT, "scripts", "world_eval_questions.json")


def _note(note_id, layer, topic, body, **meta) -> str:
    head = {"id": note_id, "layer": layer, "topic": topic, "scope": "company",
            "status": meta.pop("status", "approved"), "load": "on-demand",
            "summary": body.split(".")[0] + ".", **meta}
    lines = ["---"]
    for key, value in head.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines += [f'  - "{item}"' for item in value]
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines + ["---", "", body, ""])


SEED = [
    ("rules/style", _note("rules-headline-why", "rules", "style",
                          "Sentence case headlines read as plain speech to our clients.",
                          relates=["explains: rules-style-002"])),
    ("facts/services", _note("facts-kickoff-deposit", "facts", "services",
                             "The kickoff invoice is a 40% deposit of the project fee.",
                             relates=["depends on: facts-services-002"])),
    ("rules/style", _note("rules-case-studies", "rules", "style",
                          "Case studies open with the client's result in one plain sentence.",
                          relates=["example of: rules-style-001"])),
    ("facts/services", _note("facts-figma-handoff", "facts", "services",
                             "Developers receive the Figma prototype on the second Monday.",
                             project="Website Redesign")),
    ("facts/services", _note("facts-podcast-gear", "facts", "services",
                             "Episodes are recorded on two Shure SM7B microphones.",
                             project="Studio Podcast")),
    ("facts/services", _note("facts-day-rate-2025", "facts", "services",
                             "Our day rate is $950.", status="archived", as_of="2025-01-01")),
    ("facts/services", _note("facts-day-rate-2026", "facts", "services",
                             "Our day rate is $1,200 from October 2026.",
                             supersedes="facts-day-rate-2025", as_of="2026-10-12")),
]
JOURNAL = [
    {"at": "2026-10-05T10:00:00Z", "action": "approved", "note": "rules-headline-why"},
    {"at": "2026-10-08T10:00:00Z", "action": "approved", "note": "facts-kickoff-deposit"},
    {"at": "2026-10-12T10:00:00Z", "action": "approved", "note": "facts-day-rate-2026",
     "superseded": ["facts-day-rate-2025"]},
    {"at": "2026-10-14T10:00:00Z", "action": "edited", "note": "rules-style-002"},
    {"at": "2026-10-16T10:00:00Z", "action": "marked", "note": "facts-podcast-gear",
     "state": "disputed"},
    {"at": "2026-10-18T10:00:00Z", "action": "approved", "note": "facts-figma-handoff"},
]


# The second set's seed (--set 2), on top of the first: questions it has not answered yet.
SEED_2 = [
    ("rules/style", _note("rules-proposal-old", "rules", "style",
                          "Proposals run to five pages.", status="archived")),
    ("rules/style", _note("rules-proposal-length", "rules", "style",
                          "Proposals fit on two pages.", supersedes="rules-proposal-old",
                          relates=["instead of: rules-proposal-old"])),
    ("facts/services", _note("facts-launch-checklist", "facts", "services",
                             "Before launch we run a Lighthouse audit on every page.",
                             project="Website Redesign",
                             relates=["example of: rules-delivery-001"])),
    ("facts/services", _note("facts-guest-booking", "facts", "services",
                             "Podcast guests book their slot through Calendly.",
                             project="Studio Podcast")),
]
JOURNAL_2 = [
    {"at": "2026-10-03T10:00:00Z", "action": "verified", "note": "rules-style-001"},
    {"at": "2026-10-20T10:00:00Z", "action": "approved", "note": "rules-proposal-length",
     "superseded": ["rules-proposal-old"]},
    {"at": "2026-10-21T10:00:00Z", "action": "edited", "note": "facts-services-002"},
    {"at": "2026-10-22T10:00:00Z", "action": "marked", "note": "facts-guest-booking",
     "state": "disputed"},
    {"at": "2026-10-23T10:00:00Z", "action": "approved", "note": "facts-launch-checklist"},
]


def _brain(base: str, code: str, second: bool = False) -> tuple[str, str, int]:
    if os.path.isdir(base):
        shutil.rmtree(base)
    vault = fixture.build(base)
    for folder, text in SEED + (SEED_2 if second else []):
        path = os.path.join(vault, "knowledge", *folder.split("/"))
        os.makedirs(path, exist_ok=True)
        name = text.split("id: ", 1)[1].split("\n", 1)[0]
        with open(os.path.join(path, f"{name}.md"), "w", encoding="utf-8") as handle:
            handle.write(text)
    journal = os.path.join(vault, "journal", "decisions.jsonl")
    os.makedirs(os.path.dirname(journal), exist_ok=True)
    with open(journal, "a", encoding="utf-8") as handle:
        for record in sorted(JOURNAL + (JOURNAL_2 if second else []), key=lambda r: r["at"]):
            handle.write(json.dumps({**record, "by": "person:alex"}) + "\n")
    env = {**os.environ, "PYTHONPATH": code, "BRAIN_EMBEDDINGS": "0",
           "BRAIN_MODEL_SERVICE": "off"}
    subprocess.run([sys.executable, "-m", "brainkit", "--vault", vault, "kernel"], env=env,
                   capture_output=True, check=False)
    folder = os.path.dirname(vault)
    agents = os.path.join(folder, "AGENTS.md")
    startup = util.tokens(util.read_text(agents)) if os.path.isfile(agents) else 0
    config = os.path.join(base, "mcp.json")
    with open(config, "w", encoding="utf-8") as handle:
        json.dump({"mcpServers": {oe.SERVER: {
            "command": sys.executable, "args": ["-m", "brainkit", "--vault", vault, "mcp"],
            "env": {"BRAIN_EMBEDDINGS": "0", "BRAIN_MODEL_SERVICE": "off",
                    "PYTHONPATH": code}}}}, handle)
    return folder, config, startup


def correct(question: dict, answer: str) -> bool:
    text = answer.lower()
    if question.get("expect_all"):
        return all(term.lower() in text for term in question["expect_all"])
    return any(term.lower() in text for term in question.get("expect") or [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--code", default=os.path.join(ROOT, "packages", "brain", "src"))
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--cap", type=float, default=1.0, help="stop past this many dollars")
    parser.add_argument("--spent", type=float, default=0.0, help="already spent elsewhere")
    parser.add_argument("--set", type=int, default=1, help="1 or 2 (questions and seed)")
    args = parser.parse_args()
    questions_path = QUESTIONS if args.set == 1 else QUESTIONS.replace(
        "world_eval_questions.json", "world_eval_questions_2.json")
    with open(questions_path, encoding="utf-8") as handle:
        questions = json.load(handle)["questions"]
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP)}
    spent, rows = args.spent, []
    for q in questions:
        if spent > args.cap:
            print(f"Stopped: ${spent:.3f} spent, past the ${args.cap:.2f} cap.", flush=True)
            break
        folder, config, startup = _brain(os.path.join(args.out, args.label, q["id"]),
                                         args.code, second=args.set == 2)
        case = oe.Case(q["id"], q["q"], q["kind"], lambda t: "")
        found = oe.run_claude(case, cwd=folder, mcp_config=config, model=args.model, env=env)
        spent += float(found.cost or 0)
        pulls = [c.name for c in found.calls if c.name != "gnomon_get_context"]
        row = {"id": q["id"], "kind": q["kind"], "correct": correct(q, found.answer),
               "error": found.error, "calls": [c.name for c in found.calls],
               "pulls": len(pulls), "tokens_in": found.tokens_in, "tokens_out": found.tokens_out,
               "cost": found.cost, "startup_tokens": startup,
               "first_packet_tokens": util.tokens(found.first_packet) if found.first_packet else 0}
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("id", "correct", "calls", "first_packet_tokens")}),
              flush=True)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, f"results-{args.label}.json"), "w", encoding="utf-8") as h:
        json.dump(rows, h, indent=2)
    print(f"{args.label}: {sum(r['correct'] for r in rows)}/{len(rows)} correct, "
          f"${spent - args.spent:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
