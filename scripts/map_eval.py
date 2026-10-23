"""Does the Brain map help an AI answer, without over-pulling? (Release 1 plan, section 10.5)

    uv run python scripts/map_eval.py --models <dir> --longmemeval <longmemeval_s_cleaned.json>
        --cohorts <dir with development.json> [--only scope,gaps,lme] [--limit N]
        [--markdown out.md] [--json out.json]

About 60 questions, each asked three ways by Claude Haiku 5.5 (`claude -p`, the prompt on
stdin, only the Brain's MCP tools, connectors off, at most 4 turns; the journey_check
pattern):

    packet      the packet only: no map, no pulls
    map         the packet with the Brain map, no pulls
    map_pulls   the packet with the map, and the read tools to pull what it lists

Questions (scripts/map_eval_questions.json, labelled before any run): the 28 project
requests of scope.json, 12 gap questions whose answer is in the Brain but not in today's
packet, and the first 20 short-answer questions of the frozen LongMemEval development
cohort. The release cohort and the sealed Brains are never read.

Scored with no model judge: an answer is correct when it holds an expected term and cites
the needed note; gaps closed (a gap answered correctly through a pull); unused pulls (opened,
never cited); tokens per answer (the receipts' packet, map and pulls). About 180 short calls
a run: at gate points only, never in CI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import conversation_eval, evalkit, receipts, scope_eval  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402
from brainkit.api import Brain  # noqa: E402

MODEL = "claude-haiku-5-5"
QUESTIONS = os.path.join(ROOT, "scripts", "map_eval_questions.json")
SCOPE = os.path.join(ROOT, "packages", "brain", "tests", "evals", "scope.json")
SERVER = os.path.join(ROOT, "scripts", "map_eval_server.py")
EMPTY = os.path.join(ROOT, "brains", "empty", "vault")
CONTEXT = ("get_task_context", "gnomon_get_context")
PULLS = ("get_note", "notes_get", "search_notes", "notes_search", "gnomon_map",
         "get_reference", "files_open", "get_state", "sheets_get", "receipts_get")
CONDITIONS = {"packet": (True, CONTEXT), "map": (False, CONTEXT),
              "map_pulls": (False, CONTEXT + PULLS)}
TURNS = 4
ASK = """Answer this request for the person whose Brain is connected, using only the Brain's \
tools. Start with get_task_context (or gnomon_get_context) for the request. Use only what the \
tools return. If the Brain does not hold the answer, say so.

Reply with one JSON object and nothing else:
{{"answer": "<your answer, in a few sentences>", "cited": ["<the id of every note you used>"]}}

Request: {question}"""


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w%$.,:]+", " ", str(text or "").lower()).split())


def ask(vault: str, question: str, condition: str) -> dict:
    no_map, tools = CONDITIONS[condition]
    args = [SERVER, "--vault", vault] + (["--no-map"] if no_map else [])
    config = {"mcpServers": {"contxt": {"command": sys.executable, "args": args}}}
    folder = tempfile.mkdtemp(prefix="map-eval-")
    path = os.path.join(folder, "mcp.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDECODE", "CLAUDE_CODE_", "MCP_", "CONTXT_", "BRAIN_"))}
    env.update({"MCP_TIMEOUT": "60000", "ENABLE_CLAUDEAI_MCP_SERVERS": "false"})
    allowed = ",".join(f"mcp__contxt__{t}" for t in tools)
    try:
        done = subprocess.run(
            [shutil.which("claude") or "claude", "-p", "--model", MODEL, "--mcp-config", path,
             "--strict-mcp-config", "--allowedTools", allowed, "--max-turns", str(TURNS),
             "--output-format", "json"],
            input=ASK.format(question=question), capture_output=True, text=True,
            encoding="utf-8", timeout=600, env=env, cwd=folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    try:
        out = json.loads(done.stdout.strip())
    except ValueError:
        out = {"result": done.stdout.strip()}
    result = str(out.get("result") or "")
    start, end = result.find("{"), result.rfind("}")
    try:
        answer = json.loads(result[start:end + 1]) if start >= 0 else {}
    except ValueError:
        answer = {}
    usage = out.get("usage") or {}
    return {"answer": str(answer.get("answer") or result)[:2000],
            "cited": [str(c) for c in answer.get("cited") or []],
            "model_tokens": int(usage.get("input_tokens") or 0)
            + int(usage.get("output_tokens") or 0),
            "error": done.stderr[-400:] if done.returncode else ""}


def _receipts(vault: str, seen: set) -> list[dict]:
    """The receipts of the packets this question's run asked for."""
    brain = Brain(vault, embeddings=False)
    try:
        rows = brain.ledger.requests(limit=50)
        found = [receipts.build(brain, r["id"]) for r in rows if r["id"] not in seen]
    finally:
        brain.close()
    seen.update(r["id"] for r in rows)
    return [f for f in found if f]


def grade(reply: dict, expect: list[str], needs: set, got: list[dict]) -> dict:
    text = _norm(reply["answer"])
    worded = any(_norm(term) in text for term in expect)
    cited = set(reply["cited"])
    sent = {s["id"] for r in got for s in r["sent"]}
    listed = {s["id"] for r in got for s in r["did_not_fit"]}
    opened = [o["id"] for r in got for o in r["opened"]]
    return {"correct": worded and (not needs or bool(needs & cited)), "worded": worded,
            "cited_need": bool(needs & cited), "in_packet": bool(needs & sent),
            "listed_only": bool(needs & listed) and not needs & sent,
            "pulled_need": bool(needs & set(opened)), "pulls": len(opened),
            "unused_pulls": sum(1 for o in opened if o not in cited),
            "tokens": sum(int(r["tokens"]["total"]) for r in got),
            "model_tokens": reply["model_tokens"], "error": reply["error"]}


SILENT = []  # replies that came back empty in a row: the model is not answering


def run_one(vault: str, question: str, expect, needs, conditions, seen) -> dict:
    out = {}
    for condition in conditions:
        reply = ask(vault, question, condition)
        SILENT.append(not reply["model_tokens"])
        if len(SILENT) >= 3 and all(SILENT[-3:]):
            # A usage limit or a dead login: stop rather than score silence as wrong answers.
            raise SystemExit("The model stopped answering (three empty replies in a row); "
                             "nothing after this point was scored. " + reply["error"][-200:])
        out[condition] = grade(reply, expect, needs, _receipts(vault, seen))
        print(f"  {condition}: {'correct' if out[condition]['correct'] else 'wrong'}",
              flush=True)
    return out


def scope_set(spec, labels, models, conditions, limit):
    rows = []
    vault, _owner = scope_eval.build(ROOT, spec, models)
    seen: set = set()
    try:
        cases = [(p, c) for p in spec["projects"] for c in p["requests"]][:limit]
        for project, case in cases:
            needs = set(project["pins"]) if case.get("status") else {case["need"]}
            print(case["q"], flush=True)
            rows.append({"set": "scope", "q": case["q"], **{"by": run_one(
                vault, case["q"], labels["scope"][case["q"]], needs, conditions, seen)}})
    finally:
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return rows


def gap_set(labels, models, conditions, limit):
    rows = []
    for case in labels["gaps"][:limit]:
        source = os.path.join(ROOT, case.get("vault") or os.path.join("brains", case["brain"],
                                                                       "vault"))
        vault = se.copy_vault(source, models)
        try:
            evalkit.zero_config(vault)
            print(case["request"], flush=True)
            rows.append({"set": "gaps", "q": case["request"], "by": run_one(
                vault, case["request"], case["expect"], {case["need"]}, conditions, set())})
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return rows


def lme_set(data_path, cohorts, models, conditions, limit):
    with open(data_path, encoding="utf-8") as handle:
        items = {i["question_id"]: i for i in json.load(handle)}
    with open(os.path.join(cohorts, "development.json"), encoding="utf-8") as handle:
        order = json.load(handle)["question_ids"]
    chosen = [items[q] for q in order if q in items
              and 0 < len(str(items[q].get("answer") or "").split()) <= 6][:min(limit, 20)]
    rows = []
    for item in chosen:
        notes, case = conversation_eval.convert(item)
        vault = se.copy_vault(EMPTY, models)
        try:
            se.add_notes(vault, notes)
            evalkit.zero_config(vault)
            needs = {n for group in case["annotated_turn_groups"] for n in group}
            print(item["question"], flush=True)
            rows.append({"set": "lme", "q": item["question_id"], "by": run_one(
                vault, item["question"], [str(item["answer"])], needs, conditions, set())})
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return rows


def summary(rows, conditions) -> list[str]:
    lines = ["| Set | Condition | Correct | Median Brain tokens | Pulls | Unused pulls | "
             "Gaps closed by a pull |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for name in ("scope", "gaps", "lme"):
        group = [r for r in rows if r["set"] == name]
        if not group:
            continue
        for condition in conditions:
            got = [r["by"][condition] for r in group]
            pulls = sum(g["pulls"] for g in got)
            unused = sum(g["unused_pulls"] for g in got)
            closed = sum(1 for g in got if g["correct"] and g["pulled_need"]
                         and not g["in_packet"])
            lines.append(
                f"| {name} | {condition} | {sum(g['correct'] for g in got)}/{len(got)} | "
                f"{round(statistics.median(g['tokens'] for g in got))} | {pulls} | "
                f"{f'{100 * unused / pulls:.0f}%' if pulls else 'none'} | {closed} |")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--models", required=True, help="the embedding model's folder")
    parser.add_argument("--longmemeval", help="longmemeval_s_cleaned.json")
    parser.add_argument("--cohorts", help="the folder holding development.json")
    parser.add_argument("--only", default="scope,gaps,lme")
    parser.add_argument("--conditions", default=",".join(CONDITIONS))
    parser.add_argument("--limit", type=int, default=1000, help="questions per set")
    parser.add_argument("--markdown")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    sets = set(args.only.split(","))
    conditions = [c for c in args.conditions.split(",") if c in CONDITIONS]
    with open(QUESTIONS, encoding="utf-8") as handle:
        labels = json.load(handle)
    rows = []
    if "scope" in sets:
        rows += scope_set(scope_eval.load(SCOPE), labels, args.models, conditions, args.limit)
    if "gaps" in sets:
        rows += gap_set(labels, args.models, conditions, args.limit)
    if "lme" in sets and args.longmemeval and args.cohorts:
        rows += lme_set(args.longmemeval, args.cohorts, args.models, conditions, args.limit)
    text = "\n".join([f"# Brain map evaluation ({MODEL}, at most {TURNS} turns)", ""]
                     + summary(rows, conditions)) + "\n"
    print(text)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
