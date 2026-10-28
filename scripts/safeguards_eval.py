"""Run the safeguard evaluations on the packaged demo Brains and print (or save) a report.

    uv run python scripts/safeguards_eval.py                    # as the engine is now
    uv run python scripts/safeguards_eval.py --relevance-only   # constraints compete on relevance
    uv run python scripts/safeguards_eval.py --models <dir>     # match by meaning too
    uv run python scripts/safeguards_eval.py --markdown docs/evals/report.md
    uv run python scripts/safeguards_eval.py --ask-model        # check 3 through Claude Code
    uv run python scripts/safeguards_eval.py --ask-model --model haiku --verdicts <file>

`--models` is a folder holding a downloaded embedding model, as it sits in a vault's
`.brain/models` (for example a demo home's `brain/vault/.brain/models`). Every run works on
scratch copies and a throwaway session ledger.

CHECK 3. `--ask-model` asks Claude Code on this computer about every labeled pair, one call
each, with the app's own prompt (services/adjudicate.py) and the same settings as the app (no
tools, no MCP server), and saves the verdicts (`--verdicts`, by default
docs/evals/tension-verdicts.json). Without it, the saved verdicts are scored again.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS = os.path.join(ROOT, "packages", "brain", "tests", "evals")
BRAINS = os.path.join(ROOT, "brains")
VERDICTS = os.path.join(ROOT, "docs", "evals", "tension-verdicts.json")
NO_TOOLS = "You have no tools in this conversation. Reply once, with the finished answer only."


def detectors():
    """The disagreement detectors to grade: the sentence heuristic the review started from,
    and checks 1 and 2 of the baseline check."""
    from brainkit import review, tension
    return {"sentence heuristic (review.contradiction)":
            lambda a, b: review.contradiction(b, a),
            "checks 1 and 2 (tension.tension)": lambda a, b: tension.tension(b, a)}


MODEL: list[str] = []  # `--model`: the model check 3 asks (Claude Code's default without it)


def ask(prompt: str, timeout: float = 240.0) -> str:
    """One answer from Claude Code, as Runners.ask gets it."""
    folder = tempfile.mkdtemp(prefix="safeguards-ask-")
    config = os.path.join(folder, "mcp.json")
    with open(config, "w", encoding="utf-8") as handle:
        json.dump({"mcpServers": {}}, handle)
    argv = [shutil.which("claude") or "claude", "-p", "--output-format", "json",
            "--restricted", "--tools", "", "--mcp-config", config, "--strict-mcp-config",
            "--permission-mode", "dontAsk", "--no-session-persistence",
            "--append-system-prompt", NO_TOOLS, *MODEL]
    # A Claude Code session's own variables would make this a child of that session.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CLAUDE_CODE_") and k not in ("CLAUDECODE", "CLAUDE_PID")}
    try:
        done = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=folder, env=env,
                              timeout=timeout, check=False)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    try:
        found = json.loads(done.stdout or "{}")
    except ValueError:
        return ""
    return "" if found.get("is_error") else str(found.get("result") or "")


def ask_model(pairs, workers: int = 4) -> list[dict]:
    from workspace_core.services import adjudicate

    def one(pair):
        batch = {"subject": "pair", "title": "", "text": pair["b"],
                 "pairs": [{"key": "k", "id": "note-1", "title": "Existing note",
                            "text": pair["a"]}]}
        found = adjudicate.parse(ask(adjudicate.prompt(batch)), batch)
        return {"set": pair["set"], "a": pair["a"], "b": pair["b"],
                "relation": pair["relation"],
                "model": found[0]["relation"] if found else None,
                "detail": found[0]["detail"] if found else None}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, pairs))


def main(argv=None) -> int:
    from brainkit import safeguards_eval as se
    from brainkit import tension as tension_module

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--relevance-only", action="store_true",
                        help="set every target constraint to load: on-demand first")
    parser.add_argument("--models", help="a folder holding a downloaded embedding model")
    parser.add_argument("--ask-model", action="store_true",
                        help="ask Claude Code about every labeled pair (check 3)")
    parser.add_argument("--verdicts", default=VERDICTS, help="where check 3's verdicts are")
    parser.add_argument("--model", help="the model check 3 asks, for example haiku")
    parser.add_argument("--json", help="write the full results here")
    parser.add_argument("--markdown", help="write a short report here")
    args = parser.parse_args(argv)
    if args.model:
        MODEL[:] = ["--model", args.model]

    must = se.run_must_holds(BRAINS, se.load_spec(os.path.join(EVALS, "must_holds.json")),
                             relevance_only=args.relevance_only, models_dir=args.models)
    sets = {"tuning": se.load_spec(os.path.join(EVALS, "tension_pairs.json"))["pairs"],
            "held out": se.load_spec(os.path.join(EVALS, "tension_holdout.json"))["pairs"]}
    tension = {label: {name: se.tension_eval(pairs, detect)
                       for name, detect in detectors().items()}
               for label, pairs in sets.items()}
    if args.ask_model:
        every = [dict(p, set=label) for label, pairs in sets.items() for p in pairs]
        os.makedirs(os.path.dirname(os.path.abspath(args.verdicts)), exist_ok=True)
        with open(args.verdicts, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(ask_model(every), handle, indent=1, ensure_ascii=False)
    saved = {}
    if os.path.exists(args.verdicts):
        with open(args.verdicts, encoding="utf-8") as handle:
            saved = {(row["a"], row["b"]): row.get("model") for row in json.load(handle)}
    model = {label: se.verdicts_eval(pairs, saved,
                                     lambda a, b: tension_module.tension(b, a))
             for label, pairs in sets.items()} if saved else {}
    ordinary = se.held_ordinary(BRAINS)
    seeded = se.run_seeded_beliefs(
        BRAINS, se.load_spec(os.path.join(EVALS, "seeded_beliefs.json"))["cases"]
    )
    noise = se.cross_check_noise(BRAINS)
    time = se.run_time_cases(BRAINS, se.load_spec(os.path.join(EVALS, "time_cases.json"))["cases"],
                             models_dir=args.models)
    results = {"settings": {"relevance_only": args.relevance_only,
                            "semantic": bool(args.models)},
               "must_holds": must, "tension": tension, "model": model,
               "ordinary": ordinary, "seeded": seeded, "noise": noise, "time": time}

    matching = "words and meaning" if args.models else "words only"
    filed = "relevance only (set to on-demand)" if args.relevance_only else "as filed"
    lines = ["# Safeguard evaluations", "",
             f"Matching: {matching}. Constraints: {filed}.",
             "", "## Must-hold recall", "",
             f"- In-domain requests: {must['requests']}, recall {must['recall']:.0%}",
             f"- Decoys: {must['decoys']}, constraint included {must['decoy_rate']:.0%}"]
    if must.get("held_out"):
        lines.append(f"- Held-out requests (never used to tune triggers): {must['held_out']}, "
                     f"recall {must['held_out_recall']:.0%}")
    lines += ["",
              "| Brain | Note | Recall | Decoys including it |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['brain']} | `{r['note']}` | {r['recall']:.0%} | {r['decoy_rate']:.0%} |"
              for r in must["by_note"]]
    if must["misses"]:
        lines += ["", "Missed requests:", ""]
        lines += [f"- `{m['note']}`: \"{m['request']}\"" + (" (listed under Also relevant)"
                                                            if m["listed"] else "")
                  for m in must["misses"]]
    lines += ["", "## Disagreement detection", ""]
    for label, rows in tension.items():
        first = next(iter(rows.values()))
        lines += [f"{label.capitalize()}: {first['pairs']} labeled pairs, "
                  f"{first['contradictions']} of them contradictions.", "",
                  "| Detector | Recall | Precision |", "| --- | --- | --- |"]
        lines += [f"| {name} | {r['recall']:.0%} | {r['precision']:.0%} |"
                  for name, r in rows.items()]
        if model.get(label):
            found = model[label]
            lines += [f"| check 3, your own AI (saved verdicts, {found['read']} read) | "
                      f"{found['model']['recall']:.0%} | {found['model']['precision']:.0%} |",
                      f"| checks 1 to 3, as the app decides | {found['combined']['recall']:.0%} | "
                      f"{found['combined']['precision']:.0%} |"]
        lines.append("")
    lines += [f"Ordinary notes held by checks 1 and 2: {len(ordinary['held'])} of "
              f"{ordinary['notes']} ({ordinary['rate']:.0%}), each demo note proposed against "
              "the rest of its Brain.", ""]
    lines += ["## The weekly cross-check", "",
              f"Seeded wrong beliefs shown with their evidence within two weekly cycles, by "
              f"words and figures alone: {seeded['score']:.0%} of {len(seeded['cases'])}.", ""]
    lines += [f"- {c['id']} ({c['what']}, evidence in a {c['evidence']}): "
              + ("ok" if c["ok"] else "missed") for c in seeded["cases"]]
    lines += ["", "Shown on the demo Brains as they are, with nothing seeded: "
              + ", ".join(f"{name} {len(found)}" for name, found in noise.items()) + ".", ""]
    lines += ["## Dated values", "",
              f"Newest value delivered without an unmarked older one: {time['score']:.0%} "
              f"of {len(time['cases'])} cases.", ""]
    lines += [f"- {c['id']}: " + ("ok" if c["ok"] else
                                  ("newest missing" if not c["newest_delivered"] else
                                   "older value delivered unmarked: "
                                   + ", ".join(c["older_unmarked"])))
              for c in time["cases"]]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(results, handle, indent=1)
    if args.markdown:
        os.makedirs(os.path.dirname(os.path.abspath(args.markdown)), exist_ok=True)
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
