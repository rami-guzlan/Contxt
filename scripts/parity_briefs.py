"""Briefs on the eval sets, byte for byte: the parity check for retrieval in fallback.

    uv run python scripts/parity_briefs.py            # compare with the kept briefs
    uv run python scripts/parity_briefs.py --write    # keep the briefs as they are now

Every request in the eval sets (packages/brain/tests/evals: retrieval, must-holds with their
decoys, dated values) is briefed on a scratch copy of its demo Brain, matching by words, with
no model service: retrieval exactly as it runs without the local engine. The brief (the task
context, without the session's continuity lines) is compared with the copy kept in
tests/evals/parity_briefs.json, which was written before the local engine (brain-logic plan
5.11) was built. A change that means to change briefs rewrites the kept copy with --write, in
the same commit, and says so.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import safeguards_eval  # noqa: E402

EVALS = os.path.join(ROOT, "packages", "brain", "tests", "evals")
BRAINS = os.path.join(ROOT, "brains")
KEPT = os.path.join(EVALS, "parity_briefs.json")
CONTINUITY = "\n\n## Continuity"


def requests() -> list[tuple[str, str, str | None]]:
    """(brain, request, partition) for every request in the eval sets, in a fixed order."""
    out: list[tuple[str, str, str | None]] = []

    def load(name):
        with open(os.path.join(EVALS, name), encoding="utf-8") as handle:
            return json.load(handle).get("cases") or []

    for case in load("retrieval.json"):
        out.append((case["brain"], case["request"], case.get("partition") or None))
    for case in load("must_holds.json"):
        for text in list(case.get("requests") or []) + list(case.get("decoys") or []):
            out.append((case["brain"], text, None))
    for case in load("time_cases.json"):
        out.append((case["brain"], case["request"], None))
    return list(dict.fromkeys(out))


def key(brain: str, request: str, partition: str | None) -> str:
    return f"{brain} | {partition or '-'} | {request}"


def briefs() -> dict[str, str]:
    """{key: the brief's task context} for every eval request, engine off, by words."""
    wanted = requests()
    out: dict[str, str] = {}
    for name in sorted({brain for brain, _r, _p in wanted}):
        vault = safeguards_eval.copy_vault(os.path.join(BRAINS, name, "vault"))
        try:
            brain = safeguards_eval.open_brain(vault, semantic=False)
            try:
                for brain_name, request, partition in wanted:
                    if brain_name != name:
                        continue
                    found = brain.context(request, partition=partition, record=False,
                                          include_kernel=False)
                    out[key(name, request, partition)] = found.text.split(CONTINUITY, 1)[0]
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return dict(sorted(out.items()))


def compare(now: dict[str, str], kept: dict[str, str]) -> list[str]:
    """One line per difference, with a short diff for a brief that changed. A request added to
    the eval sets after the briefs were kept has nothing to compare with: it is not a
    difference (`main` names it)."""
    problems = []
    for name in sorted(set(kept) - set(now)):
        problems.append(f"missing now: {name}")
    for name in sorted(set(now) & set(kept)):
        if now[name] != kept[name]:
            diff = "\n".join(list(difflib.unified_diff(
                kept[name].splitlines(), now[name].splitlines(), "kept", "now", lineterm=""))[:40])
            problems.append(f"changed: {name}\n{diff}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="keep the briefs as they are now")
    args = parser.parse_args(argv)
    now = briefs()
    if args.write:
        with open(KEPT, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"about": "Briefs on the eval sets before the local engine (BL 5.11), "
                                "engine off, by words: scripts/parity_briefs.py.",
                       "briefs": now}, handle, indent=1, ensure_ascii=False)
            handle.write("\n")
        print(f"Kept {len(now)} briefs in {os.path.relpath(KEPT, ROOT)}")
        return 0
    with open(KEPT, encoding="utf-8") as handle:
        kept = json.load(handle)["briefs"]
    problems = compare(now, kept)
    for line in problems:
        print(line)
    for name in sorted(set(now) - set(kept)):
        print(f"added since the briefs were kept: {name}")
    print(f"{len(now)} briefs: " + ("the same, byte for byte" if not problems
                                     else f"{len(problems)} differ"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
