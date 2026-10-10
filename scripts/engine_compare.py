"""Pick the retrieval setup (brain-logic plan 5.11.11): setups A to E on the labeled requests.

    uv run python scripts/engine_compare.py [--models <embedding models folder>] [--markdown <file>]

    A  today: keywords and bge-small, no model service
    B  A plus Qwen3-Reranker with the relevance cut
    C  B plus the decision model's gate (Kev)
    D  C plus Kev's second pass and the link loop
    E  Kev as the main relevance scorer instead of the reranker

Each runs on the demo Brains' labeled requests (tests/evals/retrieval.json, with requests that
should get nothing) and their must-hold cases with decoys (tests/evals/must_holds.json), scored
on needed-note recall at the budget, noise, decoys, correct nothing and false nothing, brief
tokens and each layer's time at p50 and p95. Each runs with bge-small and with
Qwen3-Embedding-0.6B in the find step.

B to E need a verified local model service (`python -m brainkit.modelservice`, on a machine
that runs the pinned models: a PC with an NVIDIA GPU or an Apple Silicon Mac). Where there is
none, they are skipped and the report says why. Qwen3-Embedding needs a meaning-index backend
the engine does not have yet; it is skipped the same way. The winner is the fastest setup that
clears every gate in 5.11.13; a tie goes to the setup with fewer models. Nothing here downloads
a model.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import models_client, safeguards_eval  # noqa: E402

EVALS = os.path.join(ROOT, "packages", "brain", "tests", "evals")
BRAINS = os.path.join(ROOT, "brains")
ALL_ON = {"gate": True, "second_pass": True, "loop": True}
SETUPS = {
    "A": {"about": "today: keywords and bge-small", "engine": {"enabled": False},
          "models": 1, "service": False},
    "B": {"about": "A plus Qwen3-Reranker with the relevance cut",
          "engine": {"layers": {"gate": False, "second_pass": False, "loop": False}},
          "models": 2, "service": True},
    "C": {"about": "B plus the Kev gate",
          "engine": {"layers": {"gate": True, "second_pass": False, "loop": False}},
          "models": 3, "service": True},
    "D": {"about": "C plus Kev's second pass and the link loop",
          "engine": {"layers": dict(ALL_ON)}, "models": 3, "service": True},
    "E": {"about": "Kev as the main relevance scorer instead of the reranker",
          "engine": {"layers": dict(ALL_ON), "scorer": "decide"}, "models": 2,
          "service": True},
}
EMBEDDINGS = ("bge-small-en-v1.5", "qwen3-embedding-0.6b")
# The gates in 5.11.13 a winner must clear (speed is checked against 5.11.7 on the reference
# machines; tokens against setup A's).
GATES = {"held_out_recall": 0.90, "noise": 0.15, "decoys": 0.02, "correct_nothing": 0.95,
         "false_nothing": 0.02}
BUDGET_P95_MS = {"pc": 1000, "mac": 2000}  # the whole brief, 5.11.7


def load(name: str) -> dict:
    with open(os.path.join(EVALS, name), encoding="utf-8") as handle:
        return json.load(handle)


def percentiles(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return round(statistics.median(ordered), 1), round(p95, 1)


def run_setup(key: str, embedding: str, models_dir: str | None) -> dict:
    setup = SETUPS[key]
    if embedding != "bge-small-en-v1.5":
        return {"setup": key, "embedding": embedding, "skipped":
                "Qwen3-Embedding-0.6B needs a meaning-index backend the engine does not run yet"}
    if setup["service"]:
        found = models_client.status(refresh=True)
        if not found.ready:
            return {"setup": key, "embedding": embedding,
                    "skipped": f"needs a verified local model service: {found.reason}"}
    retrieval = safeguards_eval.run_retrieval(BRAINS, load("retrieval.json"),
                                              models_dir=models_dir, engine=setup["engine"])
    must = safeguards_eval.run_must_holds(BRAINS, load("must_holds.json"),
                                          models_dir=models_dir, engine=setup["engine"])
    rows = retrieval["rows"]
    layers: dict[str, list[float]] = {}
    totals = []
    warm = set()
    for row in rows:
        if row.get("brain") not in warm:
            warm.add(row.get("brain"))  # its first request builds the meaning cache: left out
            continue
        totals.append(float(row.get("ms") or 0.0))
        for layer, ms in ((row.get("engine") or {}).get("timings") or {}).items():
            layers.setdefault(layer, []).append(float(ms))
    every = retrieval["all"]
    return {
        "setup": key, "embedding": embedding, "about": setup["about"],
        "models": setup["models"] + (0 if models_dir else -1),
        "held_out_recall": retrieval["holdout"]["must_recall"],
        "recall": every["must_recall"], "precision": every["precision"],
        "noise": every["noise_share"], "decoys": must["decoy_rate"],
        "must_hold_recall": must["recall"],
        "correct_nothing": every.get("correct_nothing"),
        "false_nothing": every.get("false_nothing"),
        "tokens": every["avg_tokens"],
        "brief_ms": percentiles(totals),
        "layers": {layer: percentiles(values) for layer, values in sorted(layers.items())},
        "ceiling_hits": sum(1 for r in rows if (r.get("engine") or {}).get("ceiling_hit")),
    }


def passes(result: dict, baseline_tokens: int | None) -> list[str]:
    """The gates a setup misses (an empty list clears them all)."""
    missed = []
    if (result.get("held_out_recall") or 0) < GATES["held_out_recall"]:
        missed.append("held-out recall")
    if (result.get("noise") or 0) > GATES["noise"]:
        missed.append("noise")
    if (result.get("decoys") or 0) > GATES["decoys"]:
        missed.append("decoys")
    if result.get("correct_nothing") is None or result["correct_nothing"] < GATES[
            "correct_nothing"]:
        missed.append("correct nothing")
    if (result.get("false_nothing") or 0) > GATES["false_nothing"]:
        missed.append("false nothing")
    if baseline_tokens is not None and (result.get("tokens") or 0) > baseline_tokens:
        missed.append("tokens above setup A")
    return missed


def qualification(results: list[dict]) -> dict:
    """Which Kev steps the decision model passed here (5.11.15): the gate when setup C clears
    held-out recall and both nothing gates; the second pass when setup D clears held-out
    recall, noise and decoys. Judged with the default embedding."""
    ran = {r["setup"]: r for r in results
           if "skipped" not in r and r["embedding"] == EMBEDDINGS[0]}
    out = {}
    if "C" in ran:
        missed = set(passes(ran["C"], None))
        out["gate"] = not missed & {"held-out recall", "correct nothing", "false nothing"}
    if "D" in ran:
        missed = set(passes(ran["D"], None))
        out["second_pass"] = not missed & {"held-out recall", "noise", "decoys"}
    return out


def report(results: list[dict]) -> str:
    def pct(value):
        return "-" if value is None else f"{value:.0%}"

    lines = ["# Retrieval setups A to E (brain-logic plan 5.11.11)", "",
             "| Setup | Find | Held-out recall | Recall | Noise | Decoys | Correct nothing "
             "| False nothing | Tokens | Brief ms p50 / p95 (warm) | Gates missed |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    baseline = next((r["tokens"] for r in results if r["setup"] == "A" and "skipped" not in r),
                    None)
    for r in results:
        if "skipped" in r:
            lines.append(f"| {r['setup']} | {r['embedding']} | skipped: {r['skipped']} "
                         "| | | | | | | | |")
            continue
        p50, p95 = r["brief_ms"]
        missed = passes(r, baseline)
        lines.append(f"| {r['setup']} | {r['embedding']} | {pct(r['held_out_recall'])} "
                     f"| {pct(r['recall'])} | {pct(r['noise'])} | {pct(r['decoys'])} "
                     f"| {pct(r['correct_nothing'])} | {pct(r['false_nothing'])} "
                     f"| {r['tokens']} | {p50} / {p95} | {', '.join(missed) or 'none'} |")
    ran = [r for r in results if "skipped" not in r]
    clear = [r for r in ran if not passes(r, baseline)]
    lines.append("")
    if clear:
        best = min(clear, key=lambda r: (r["brief_ms"][1] or 0, r["models"]))
        lines.append(f"Winner: setup {best['setup']} with {best['embedding']} (fastest of those "
                     "that clear every gate; a tie goes to fewer models). Speed against 5.11.7 "
                     "is judged on the reference PC and Mac.")
    else:
        lines.append("No setup that ran clears every gate yet"
                     + ("; the others need the models on a PC or Mac." if len(ran) < len(results)
                        else "."))
    for r in ran:
        if r["layers"]:
            parts = ", ".join(f"{layer} {p50} / {p95} ms" for layer, (p50, p95)
                              in r["layers"].items())
            lines.append(f"- Setup {r['setup']} layers (p50 / p95): {parts}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", help="a folder holding the bge-small embedding model")
    parser.add_argument("--setups", default="ABCDE", help="which setups to run (default all)")
    parser.add_argument("--markdown", help="write the report to this file too")
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    parser.add_argument("--record", action="store_true",
                        help="keep which Kev steps the running decision model qualified for "
                             "on this machine (Settings shows each fallback)")
    args = parser.parse_args(argv)
    results = []
    for key in [k for k in args.setups.upper() if k in SETUPS]:
        for embedding in EMBEDDINGS:
            found = run_setup(key, embedding, args.models)
            results.append(found)
            if "skipped" in found:
                print(f"Setup {key} with {embedding}: skipped ({found['skipped']})", flush=True)
    if args.record:
        record_qualification(results)
    if args.json:
        print(json.dumps(results, indent=1))
        return 0
    text = report(results)
    print(text)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return 0


def record_qualification(results: list[dict]) -> None:
    from brainkit import machine
    steps = qualification(results)
    decider = (models_client.status(refresh=True).roles.get("decide") or {}).get("model")
    if not decider or not steps:
        print("Nothing recorded: no decision model ran, or setups C and D were skipped.")
        return
    machine.record(decider, steps=steps)
    print(f"Recorded for {decider} on this machine: " + ", ".join(
        f"{step.replace('_', ' ')} {'qualified' if ok else 'not qualified'}"
        for step, ok in steps.items()))


if __name__ == "__main__":
    sys.exit(main())
