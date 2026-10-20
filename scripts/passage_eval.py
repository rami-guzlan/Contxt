"""Does the brief reach the evidence, and is the evidence visible in what it sends? Measured on
a development cohort of public LongMemEval questions nobody here has scored before.

    uv run python scripts/passage_eval.py --data <longmemeval_s_cleaned.json>
        --exclude <protocol.json> --cohorts <dir> --models <dir> [--markdown <file>]

The first run freezes two cohorts in --cohorts: `development.json` (60 questions, measured
here, safe to look at) and `release.json` (60 more, written once and never scored by this
script: it is the untouched cohort a release is judged on). Questions in --exclude (an
earlier protocol's question_ids and excluded_ids) and abstention questions are left out.

For each development question the history becomes a Brain (conversation_eval.convert: one
note per user turn with the replies it got) on a zero-config scratch copy, and the question
is asked once. Measures, over the annotated evidence groups:
    reach    a note of the group is sent or listed
    whole    a note of the group is sent whole
    visible  ten words in a row of an evidence turn appear in the text the brief sends
    answer   the question's expected answer appears in that text, word for word (a short
             answer such as a name or a figure; computed answers rarely can)
Labels never enter the Brain or the request. No model is asked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import conversation_eval, evalkit  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402

EMPTY = os.path.join(ROOT, "brains", "empty", "vault")
SALT = "passage-cohorts-2026-10-19"
SIZE = 60


def _order(qid: str) -> str:
    return hashlib.sha256(f"{SALT}:{qid}".encode()).hexdigest()


def cohorts(items: list[dict], exclude: set[str], folder: str) -> list[dict]:
    """The development cohort, freezing both cohorts the first time."""
    dev_path = os.path.join(folder, "development.json")
    if not os.path.exists(dev_path):
        pool = sorted((i for i in items if not str(i["question_id"]).endswith("_abs")
                       and i["question_id"] not in exclude), key=lambda i: _order(
                           i["question_id"]))
        os.makedirs(folder, exist_ok=True)
        for name, chosen in (("development", pool[:SIZE]), ("release", pool[SIZE:2 * SIZE])):
            with open(os.path.join(folder, f"{name}.json"), "x", encoding="utf-8") as handle:
                json.dump({"salt": SALT, "question_ids": [i["question_id"] for i in chosen]},
                          handle, indent=1)
    with open(dev_path, encoding="utf-8") as handle:
        wanted = json.load(handle)["question_ids"]
    by_id = {i["question_id"]: i for i in items}
    return [by_id[q] for q in wanted]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


WINDOW = 10


def evidence_snippets(item: dict) -> dict[str, list[str]]:
    """{session id: every run of WINDOW words of its marked turns}."""
    out: dict[str, list[str]] = {}
    for sid, turns in zip(item["haystack_session_ids"], item["haystack_sessions"],
                          strict=True):
        for turn in turns:
            if turn.get("has_answer"):
                words = _norm(turn["content"]).split()
                out.setdefault(sid, []).extend(
                    " ".join(words[i:i + WINDOW])
                    for i in range(0, max(1, len(words) - WINDOW + 1), 3))
    return out


def run_question(item: dict, models: str | None, prepare=None) -> dict:
    notes, case = conversation_eval.convert(item)
    root = se.copy_vault(EMPTY, models)
    try:
        se.add_notes(root, notes)
        evalkit.zero_config(root)
        if prepare is not None:
            prepare(root)
        brain = se.open_brain(root, semantic=bool(models))
        try:
            started = time.perf_counter()
            res = brain.context(item["question"], record=False, include_kernel=False)
            ms = (time.perf_counter() - started) * 1000
        finally:
            brain.close()
    finally:
        shutil.rmtree(os.path.dirname(root), ignore_errors=True)
    data = res.data
    sent = set(data.get("note_ids") or [])
    listed = sent | set(data.get("related_ids") or [])
    text = _norm(res.text)
    snippets = evidence_snippets(item)
    targets = list(dict.fromkeys(item.get("answer_session_ids") or []))
    rows = []
    for sid, group in zip(targets, case["annotated_turn_groups"], strict=True):
        if not group:
            continue
        rows.append({"reach": bool(listed & set(group)), "whole": bool(sent & set(group)),
                     "visible": any(s and s in text for s in snippets.get(sid, []))})
    answer = _norm(str(item.get("answer") or ""))
    return {"id": item["question_id"], "type": item["question_type"], "groups": rows,
            "answer_seen": bool(answer) and len(answer.split()) <= 6 and answer in text,
            "short_answer": bool(answer) and len(answer.split()) <= 6,
            "tokens": data.get("token_count"), "ms": round(ms)}


def summarize(results: list[dict]) -> dict:
    groups = [g for r in results for g in r["groups"]]
    out = {"questions": len(results), "groups": len(groups)}
    for key in ("reach", "whole", "visible"):
        k = sum(g[key] for g in groups)
        low, high = evalkit.wilson(k, len(groups)) or (0, 0)
        out[key] = {"k": k, "n": len(groups), "rate": k / len(groups) if groups else None,
                    "low": low, "high": high}
    out["all_visible"] = sum(all(g["visible"] for g in r["groups"]) for r in results
                             if r["groups"])
    short = [r for r in results if r.get("short_answer")]
    out["answer_seen"] = {"k": sum(r["answer_seen"] for r in short), "n": len(short)}
    out["tokens"] = round(sum(r["tokens"] or 0 for r in results) / max(1, len(results)))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--data", required=True)
    parser.add_argument("--exclude", required=True, help="an earlier protocol.json")
    parser.add_argument("--cohorts", required=True, help="where the frozen cohorts live")
    parser.add_argument("--models", help="a folder holding the meaning model")
    parser.add_argument("--json", help="write every question's result here")
    args = parser.parse_args(argv)
    with open(args.data, encoding="utf-8") as handle:
        items = json.load(handle)
    with open(args.exclude, encoding="utf-8") as handle:
        protocol = json.load(handle)
    exclude = set(protocol.get("question_ids") or []) | set(protocol.get("excluded_ids") or [])
    chosen = cohorts(items, exclude, args.cohorts)
    results = []
    for number, item in enumerate(chosen, 1):
        results.append(run_question(item, args.models))
        print(f"  {number}/{len(chosen)}", file=sys.stderr, flush=True)
    summary = summarize(results)
    print(json.dumps(summary, indent=1))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"summary": summary, "results": results}, handle, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
