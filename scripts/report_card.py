"""The final report card (brain-logic plan phase 6): every bar the plans set, run again on the
packaged demo Brains, in one Markdown page.

    uv run python scripts/report_card.py --out <file.md>

It runs the retrieval eval, each plan section's gate tests, the drift eval, the four-week soak,
the alignment tax and the knowledge agent's labeled set, and lists what waits for real models
or for a person. Everything runs on scratch copies; nothing touches a real Brain.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import agent_eval, proof  # noqa: E402

BRAINS = os.path.join(ROOT, "brains")
B, S, C = "packages/brain/tests/", "apps/server/tests/", "packages/core/tests/"

# Each plan section's gates, and the tests that hold them.
GATES = [
    ("BL 5.9 to 5.11: retrieval, briefs, the kernel, the local engine",
     [B + "test_routing.py", B + "test_kernel.py", B + "test_parity.py",
      B + "test_local_models.py", B + "test_must_holds.py"]),
    ("BL 6: one statement model", [B + "test_statements.py", S + "test_statements.py"]),
    ("BL 7.4: ingestion and distillation", [B + "test_ingestion.py", C + "test_prepass.py",
                                            C + "test_distill.py", S + "test_triage.py"]),
    ("BL 8.9: State and working contexts", [B + "test_state.py"]),
    ("BL 9: the updating loop", [B + "test_updating_loop.py", B + "test_blind_judging.py",
                                 C + "test_agent.py", S + "test_loop.py",
                                 S + "test_runners.py"]),
    ("BL 10.6: proof", [B + "test_proof.py"]),
    ("BL 17.9: the knowledge agent run locally", [B + "test_agent_tools.py",
                                                  B + "test_agent_eval.py",
                                                  C + "test_agent_loop.py"]),
    ("Goals G1 to G4", [B + "test_ladder.py", B + "test_handoff.py", S + "test_goals.py",
                        S + "test_live_and_tasks.py", B + "test_g4.py"]),
    ("UX F and G3: workflows", [S + "test_workflows.py", C + "test_workflows.py"]),
]

WAITS = {
    "the owner": [
        "Labels for the private eval set, including about 20 requests that should get nothing.",
        "Confirming Claude Code for the knowledge agent as an opt-in once a local agent model "
        "is here.",
        "Confirming a preference as a subtype of rule.",
        "Labeled transcripts and the interview sorting exercise (ingestion precision, recall "
        "and tier routing).",
        "Content proposals for the owner's own Brain (core facts to must-holds by domain, "
        "identity bullets), made in the app and never committed here.",
        "The walkthrough on the demo Brain and a real day on the owner's own Brain, then "
        "sign-off.",
        "G4: a goal of the owner's through the coach, the T-41 story and the two "
        "interviewees; board restraint counted from those; objectives judged blind.",
        "The private agent set from the owner's own Catch up decisions.",
    ],
    "The PC and real runs": [
        "Model downloads, pins and verification; the setup comparison B to E; defaults; cut "
        "fitting; speed; Kev-0.8B's qualification.",
        "The knowledge agent per machine setup: agreement with Claude Code, hand-up rates, "
        "speed; 4B against 9B against Claude Code.",
        "Triage measured; cost per hour of meeting; the coach timed on a real model.",
        "Drift on real Work runs (the stand-in here has bounded attention, not a model's); "
        "output quality with and without alignment, judged blind.",
        "Whether formulas help (kept only if proven helpful); the agent set grown to about 15 "
        "cases per action.",
    ],
}


def _pytest(paths: list[str]) -> tuple[int, int, int]:
    present = [p for p in paths if os.path.exists(os.path.join(ROOT, p))]
    if not present:
        return 0, 0, 0
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           *present], cwd=ROOT, capture_output=True, text=True, check=False)
    tail = (done.stdout or "").strip().splitlines()[-1:] or [""]
    count = lambda word: int((re.search(rf"(\d+) {word}", tail[0]) or [0, 0])[1])  # noqa: E731
    return count("passed"), count("failed"), count("skipped")


def _retrieval() -> list[str]:
    done = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "retrieval_eval.py")],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    lines: list[str] = []
    for ln in (done.stdout or "").splitlines():
        if ln.startswith("Should get nothing"):
            lines += ["", ln, ""]  # a line between the two tables
        elif ln.startswith("|"):
            lines.append(ln)
    return lines


def build() -> str:
    today = dt.date.today().isoformat()
    out = [f"# Report card, {today}", "",
           "Every bar the brain-logic, UX and goals plans set, run again on the packaged demo "
           "Brains. Stand-ins are named where they stand in; what needs real models or a "
           "person is listed at the end.", "", "## Retrieval", ""]
    out += _retrieval() + [""]
    out += ["## Gates, by plan section", "", "| Section | Passed | Failed | Skipped |",
            "| --- | --- | --- | --- |"]
    for name, paths in GATES:
        passed, failed, skipped = _pytest(paths)
        out.append(f"| {name} | {passed} | {failed} | {skipped} |")
    found = proof.drift()
    w, wo = found["with"], found["without"]
    out += ["", "## Drift on long runs (stand-in with bounded attention)", "",
            "| | Objective kept | Must-holds in view | Finished |", "| --- | --- | --- | --- |",
            f"| With re-anchoring | {w['objective_kept']:.0%} | {w['must_holds_in_view']:.0%} "
            f"| {w['finished']:.0%} |",
            f"| Without | {wo['objective_kept']:.0%} | {wo['must_holds_in_view']:.0%} "
            f"| {wo['finished']:.0%} |", ""]
    lost = [r["id"] for r in found["rows"] if r["anchoring"] and not r["objective_kept"]]
    if lost:
        out.append(f"Lost with re-anchoring: {', '.join(lost)}, a distractor closer to the end "
                   f"than the cadence ({proof.EVERY} calls).")
        out.append("")
    soak = proof.soak(os.path.join(BRAINS, "knowledge-company", "vault"), weeks=4)
    out += ["## Four simulated weeks (knowledge-company)", "",
            "| Week | Kernel stable | Briefs moved | Unexplained | Stale caught | Bent rules "
            "flagged | Goal cards |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in soak["weeks"]:
        out.append(f"| {r['week']} | {'yes' if r['kernel_stable'] else 'no'} | "
                   f"{r['briefs_moved']} | {r['moved_unexplained']} | {r['stale_caught']} | "
                   f"{r['bent_rules']} | {r['goal_cards']} |")
    tax = proof.alignment_tax(os.path.join(BRAINS, "knowledge-company", "vault"))
    out += ["", "## The alignment tax", "",
            f"- First brief of a chat (with the startup context): {tax['first_share']:.0%} of "
            f"{tax['first_avg_tokens']} tokens on alignment ({tax['first_alignment_tokens']}).",
            f"- Later briefs: {tax['later_share']:.0%} of {tax['later_avg_tokens']} tokens "
            f"({tax['later_alignment_tokens']}).",
            f"- The deterministic output check: {tax['check_ms']} ms at most per draft.",
            "- Quality with and without alignment waits for real runs and a blind judge.", ""]
    rows = [agent_eval.run_case(BRAINS, case) for case in agent_eval.load(BRAINS)]
    bars = agent_eval.score(rows)
    out += ["## The knowledge agent's labeled set (oracle stand-in)", "",
            f"{bars['cases']} cases: valid answers {bars['valid']:.0%}, no direct writes "
            f"{'100%' if bars['no_writes'] else 'NO'}, impact lines matching "
            f"{'100%' if bars['impacts_match'] else 'NO'}, hand-ups {bars['hand_ups']}. "
            "The oracle checks the harness; agreement with Claude Code waits for the PC.", ""]
    for who, items in WAITS.items():
        out += [f"## Waiting for {who}", ""] + [f"- {item}" for item in items] + [""]
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="write the report here (Markdown); else print it")
    args = parser.parse_args(argv)
    text = build()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"Wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
