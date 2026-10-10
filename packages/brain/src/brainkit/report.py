"""The report card (brain-logic plan 10.4): what context cost by day and line, how big briefs
are by request type, and how well they carry what a task needs.

Quality comes from the brain's own eval cases (`eval.json` in the vault, when it has one) and
the owner's labeled real requests (evalset.py). Both route on a throwaway ledger.
"""
from __future__ import annotations

import os
import statistics

from . import costs, evalset, util


def card(brain, *, days: int = 7, transcripts: str | None = None, model: str | None = None,
         quality: bool = True) -> dict:
    spend = costs.daily(brain, days, transcripts=transcripts, model=model)
    sizes: dict[str, list[int]] = {}
    for day in spend["days"]:
        for kind, value in day["median_brief_by_type"].items():
            sizes.setdefault(kind, []).append(value)
    out = {
        "at": util.now_iso(), "days": days, "spend": spend,
        "per_day_usd": round(statistics.mean([d["total_usd"] for d in spend["days"]]), 4)
        if spend["days"] else 0.0,
        "brief_tokens_by_type": {k: int(statistics.median(v)) for k, v in sorted(sizes.items())},
        "tokenizer": util.tokenizer_status(),
        "eval_set": evalset.status(brain),
    }
    if quality:
        public = os.path.join(brain.vault.root, "eval.json")
        if os.path.isfile(public):
            from . import evaluate
            result = evaluate.run(brain, public)
            out["eval"] = {k: result[k] for k in ("tuning", "holdout", "all")}
        private = evalset.run(brain)
        if "all" in private:
            out["private_eval"] = {k: private[k] for k in ("tuning", "holdout", "all")}
    return out


def _usd(value: float) -> str:
    return f"${value:,.2f}" if value >= 0.1 else f"${value:,.4f}"


def render(found: dict) -> str:
    spend = found["spend"]
    factor = spend["factor"]
    lines = [f"Report card, last {found['days']} day(s)", ""]
    lines.append("Tokens: " + (
        f"calibrated against Claude (x{factor['factor']}, {factor.get('samples')} samples, "
        f"{factor.get('method')})" if factor.get("measured") else
        "estimates, not calibrated against Claude yet (run the calibration)"))
    lines.append(f"Prices: {spend['model']} where a figure is estimated; re-reads per brief: "
                 f"{spend['later_calls']} ({spend['later_calls_source']})")
    over = spend["overhead"]
    lines.append(f"Fixed overhead per call: Claude Code {over['per_call_claude_code']} tokens, "
                 f"other clients {over['per_call_other']} ({over['tools']} tools); kernel "
                 f"{over['kernel']} tokens where it loads")
    lines += ["", "Day         fixed     briefs    rereads   rewrites  jobs      total"]
    for day in spend["days"]:
        cells = [_usd(day["lines"][n]["usd"]).rjust(9) for n in costs.LINES]
        lines.append(f"{day['day']}  " + " ".join(cells) + f" {_usd(day['total_usd']).rjust(9)}")
    if spend["days"]:
        lines.append(f"Average per day: {_usd(found['per_day_usd'])}")
    else:
        lines.append("No brain use logged in this period.")
    if found["brief_tokens_by_type"]:
        lines += ["", "Median brief, tokens by request type: " + ", ".join(
            f"{k} {v}" for k, v in found["brief_tokens_by_type"].items())]
    for key, label in (("eval", "Eval cases"), ("private_eval", "Your labeled requests")):
        if key in found:
            lines += ["", label + ":"]
            for name in ("tuning", "holdout"):
                m = found[key][name]
                if m["cases"]:
                    lines.append(f"  {name:8s} {m['cases']:3d} cases, needed-note recall "
                                 f"{m['must_recall']:.0%}, precision {m['precision']:.0%}, "
                                 f"noise {m['noise_share']:.0%} of tokens, "
                                 f"{m['avg_tokens']} tokens on average")
    status = found["eval_set"]
    lines += ["", f"Private eval set: {status['labeled']} of {status['cases']} request(s) "
                  f"labeled, {status['held_out']} held out."]
    return "\n".join(lines) + "\n"
