"""Score retrieval on a public long-term memory benchmark: data nobody here wrote
(general-retrieval plan, stage 0).

    uv run python scripts/third_party_eval.py longmemeval --data <longmemeval_s_cleaned.json>
        [--models <dir>] [--per-type 10] [--markdown <file>]

LongMemEval (MIT license; https://github.com/xiaowu0162/LongMemEval): each question comes with
its own chat history of about 50 sessions, a few of which hold the answer, and the turns that
hold it are marked. For each question this builds a Brain from that history, one note per
turn the person wrote (with the reply it got, cut short), every session its own topic, and
asks the question as a request. A question is answered when the brief carries a marked turn
from every session that holds the answer (or lists one, for reachable recall). Questions the
history cannot answer (ids ending in _abs) are left out. Zero-config, as every headline is.

The data stays outside this repository (download it yourself; the file is about 280 MB):
the notes are built in scratch folders and removed after each question.

LoCoMo is not used: its license (CC BY-NC 4.0) allows non-commercial use only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import evalkit  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402

EMPTY = os.path.join(ROOT, "brains", "empty", "vault")
REPLY_CHARS = 400


def _slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "x"


def _date(raw: str) -> str:
    match = re.match(r"(\d{4})/(\d{2})/(\d{2})", raw or "")
    return "-".join(match.groups()) if match else "2023-01-01"


def _title(text: str) -> str:
    words = " ".join(text.split()).split(" ")
    return " ".join(words[:8]) + ("..." if len(words) > 8 else "")


def question_brain(item: dict) -> tuple[str, dict]:
    """A scratch vault from one question's history, and its case for evaluate.py."""
    root = tempfile.mkdtemp(prefix="lme-")
    vault = os.path.join(root, "vault")
    shutil.copytree(EMPTY, vault, ignore=shutil.ignore_patterns(".brain", ".git"))
    notes, evidence = [], {}
    for sid, date, session in zip(item["haystack_session_ids"], item["haystack_dates"],
                                  item["haystack_sessions"], strict=False):
        topic = "s-" + _slug(sid, 30)
        for turn_no, turn in enumerate(session):
            if turn.get("role") != "user":
                continue
            reply = session[turn_no + 1] if turn_no + 1 < len(session) else {}
            said = " ".join(str(turn.get("content") or "").split())
            if not said:
                continue
            answer = " ".join(str(reply.get("content") or "").split())[:REPLY_CHARS]
            note_id = f"{topic}-t{turn_no:02d}"
            notes.append({"id": note_id, "title": _title(said), "summary": said[:150],
                          "area": "me", "topic": topic, "kind": "fact",
                          "added": _date(date), "source": "the person, in conversation",
                          "body": said + (f"\n\nReply: {answer}" if answer else "") + "\n"})
            if turn.get("has_answer") or reply.get("has_answer"):
                evidence.setdefault(sid, []).append(note_id)
    se.add_notes(vault, notes)
    groups = [evidence[sid] for sid in item.get("answer_session_ids") or [] if sid in evidence]
    case = {"id": item["question_id"], "request": item["question"], "must": groups,
            "useful": [i for g in groups for i in g], "noise": [], "must_holds": [],
            "nothing": False, "set": "own", "type": item["question_type"]}
    return vault, case


def sample(items: list[dict], per_type: int) -> list[dict]:
    by_type: dict[str, list] = {}
    for item in items:
        if str(item["question_id"]).endswith("_abs"):
            continue
        by_type.setdefault(item["question_type"], []).append(item)
    out = []
    for kind in sorted(by_type):
        pool = sorted(by_type[kind], key=lambda i: str(i["question_id"]))
        step = max(1, len(pool) // per_type)
        out += pool[::step][:per_type]
    return out


def longmemeval(args) -> str:
    with open(args.data, encoding="utf-8") as handle:
        items = json.load(handle)
    chosen = sample(items, args.per_type)
    rows, notes, started = [], [], time.perf_counter()
    for number, item in enumerate(chosen, 1):
        vault, case = question_brain(item)
        try:
            if not case["must"]:
                continue
            entry = {"name": case["id"], "split": "third-party", "vault": vault,
                     "cases": [case], "private": False}
            result = evalkit.run_brain(entry, models_dir=args.models)
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
        row = result["rows"][0]
        row["type"] = item["question_type"]
        rows.append(row)
        notes.append(result["notes"])
        print(f"  {number}/{len(chosen)} {item['question_type']}: "
              f"{row['hits']}/{row['must']} ({result['notes']} notes)", file=sys.stderr,
              flush=True)
    took = time.perf_counter() - started
    lines = ["## LongMemEval (small), zero-config", "",
             f"Matching: {'words and meaning' if args.models else 'words only'}. "
             f"{len(rows)} questions ({args.per_type} per type, abstention questions left "
             f"out), each its own Brain of {min(notes)} to {max(notes)} notes (median "
             f"{round(statistics.median(notes))}). {took:.0f} s.", "",
             "| Question type | Questions | Recall | Reachable | Avg tokens |",
             "| --- | --- | --- | --- | --- |"]

    def line(label, subset):
        must = sum(r["must"] for r in subset)
        hits = sum(r["hits"] for r in subset)
        reach = sum(r["reach"] for r in subset)
        low, high = evalkit.wilson(hits, must) or (0, 0)
        tokens = round(statistics.fmean(r["tokens"] or 0 for r in subset))
        return (f"| {label} | {len(subset)} | {hits / must:.0%} ({low:.0%} to {high:.0%}) | "
                f"{reach / must:.0%} | {tokens} |")

    for kind in sorted({r["type"] for r in rows}):
        lines.append(line(kind, [r for r in rows if r["type"] == kind]))
    lines.append(line("**all**", rows))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("benchmark", choices=["longmemeval"])
    parser.add_argument("--data", required=True, help="the benchmark's data file")
    parser.add_argument("--models", help="a folder holding the embedding model (by meaning)")
    parser.add_argument("--per-type", type=int, default=10)
    parser.add_argument("--markdown", help="write the report to this file too")
    args = parser.parse_args(argv)
    text = longmemeval(args)
    print(text)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
