"""Real-model quality gates with the inputs that produced each baseline.

The gate is general (owner, October 25, 2026): it runs every Brain of the tuning split and
holds two sets of floors that name no Brain, the aggregate over all of them and the worst
Brain, the same for each.

The original stage-5 floors are retained against their 277-request calibration bank.
The shipped 292-request bank is ALSO gated, against a replay of the original reference
code with that bank. Never compare
measurements with different calibration inputs, or regenerate floors to hide a failure.
See docs/evals/stage-5-baseline-reconciliation.md for reproduction and provenance.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from brainkit import calibration, evalkit, util

HERE = Path(__file__).resolve().parent
GENERAL = HERE / "evals" / "general"
ROOT = HERE.parents[2]
MODELS = os.environ.get("BRAIN_TEST_MODELS", "")
# Existing cross-platform arithmetic allowance, unchanged for BOTH gates.
SLACK = 0.03


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _entries():
    """Every Brain of the tuning split: the quick set is general, not a chosen few."""
    return evalkit.generated_brains(str(GENERAL), ["tuning"])


def _fixture_fingerprint(entries):
    files = {}
    for entry in entries:
        vault = Path(entry["vault"])
        for path in sorted(vault.rglob("*")):
            relative = path.relative_to(vault)
            if path.is_file() and not any(p.startswith(".") for p in relative.parts):
                key = f"{entry['name']}/{relative.as_posix()}"
                files[key] = path.read_text(encoding="utf-8-sig")
    payload = {"files": files, "cases": {e["name"]: e["cases"] for e in entries},
               "off_topic": _json(GENERAL / "off_topic.json")}
    return util.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _baselines():
    manifest = _json(GENERAL / "baseline-inputs.json")
    rows = manifest["baselines"]
    if len(rows) != 2 or sum(r["bank_file"] is None for r in rows) != 1:
        raise ValueError("Both the historical bank and the shipped bank must be gated")
    for row in rows:
        row["minimums"] = _json(GENERAL / row["minimums_file"])
        row["entries"] = _entries()
        if row["bank_file"] is None:
            bank = calibration.null_bank()
        else:
            text = (GENERAL / row["bank_file"]).read_text(encoding="utf-8")
            bank = [line.strip() for line in text.splitlines()
                    if line.strip() and not line.startswith("#")]
        row["bank"] = bank
        if calibration.bank_fingerprint(bank) != row["bank_sha256"]:
            raise ValueError(f"{row['id']}: calibration inputs changed; replay the baseline")
        if _fixture_fingerprint(row["entries"]) != row["fixtures_sha256"]:
            raise ValueError(f"{row['id']}: benchmark fixtures changed; replay the baseline")
        if not row["entries"] or set(row["minimums"]) < {"aggregate", "worst"}:
            raise ValueError(f"{row['id']}: the floors need the aggregate and the worst Brain")
    return manifest, rows


def measured(results) -> dict:
    """The aggregate over every Brain, and the worst Brain, of each measure."""
    total: dict = {}
    rates: dict = {}
    for result in results:
        for measure, (k, n) in result["counts"].items():
            pair = total.setdefault(measure, [0, 0])
            pair[0] += k
            pair[1] += n
            found = evalkit.rate([k, n])
            if found is not None:
                rates.setdefault(measure, []).append(found)
    aggregate = {m: evalkit.rate(pair) for m, pair in total.items()
                 if evalkit.rate(pair) is not None}
    worst = {m: (max if m in evalkit.LOWER_IS_BETTER else min)(values)
             for m, values in rates.items()}
    return {"aggregate": aggregate, "worst": worst}


def _problems(results, minimums):
    found = measured(results)
    problems = []
    for level in ("aggregate", "worst"):
        for measure, value in (minimums.get(level) or {}).items():
            got = found[level].get(measure)
            if got is None:
                problems.append(f"{level} {measure} was not measured")
            elif measure in evalkit.LOWER_IS_BETTER:
                if got > value + SLACK:
                    problems.append(f"{level} {measure} {got:.3f} > {value}")
            elif got < value - SLACK:
                problems.append(f"{level} {measure} {got:.3f} < {value}")
    return problems


class BaselineInputsTest(unittest.TestCase):
    def test_both_baselines_keep_their_recorded_inputs_and_cover_every_brain(self):
        _manifest, rows = _baselines()
        self.assertEqual(set(rows[0]["minimums"]["aggregate"]),
                         set(rows[1]["minimums"]["aggregate"]))

    def test_a_required_measurement_cannot_pass_by_disappearing(self):
        results = [{"name": "sample", "counts": {"reachable": [0, 0]}}]
        self.assertEqual(_problems(results, {"aggregate": {"reachable": 0.9}, "worst": {}}),
                         ["aggregate reachable was not measured"])

    def test_the_floors_name_no_brain(self):
        _manifest, rows = _baselines()
        names = {e["name"] for e in evalkit.generated_brains(str(GENERAL))}
        for row in rows:
            text = json.dumps({k: v for k, v in row["minimums"].items() if k != "about"})
            self.assertFalse([n for n in names if f'"{n}"' in text], row["id"])


@unittest.skipUnless(MODELS and os.path.isdir(MODELS), "needs BRAIN_TEST_MODELS with bge-small")
class QuickSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest, cls.baselines = _baselines()
        model = manifest["model"]
        cache = Path(MODELS) / model["cache_folder"]
        revision = (cache / "refs/main").read_text(encoding="utf-8").strip()
        if revision != model["revision"]:
            raise ValueError("Embedding model revision changed; replay the baselines")
        for name, digest in model["files"].items():
            artifact = cache / "snapshots" / revision / name
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if actual != digest:
                raise ValueError(f"Embedding artifact {name} changed; replay the baselines")
        at = dt.datetime.fromisoformat(manifest["as_of"])
        for baseline in cls.baselines:
            bank_override = (mock.patch.object(calibration, "null_bank",
                                               return_value=baseline["bank"])
                             if baseline["bank_file"] else contextlib.nullcontext())
            with bank_override, mock.patch.object(util, "now", return_value=at), util.zone(dt.UTC):
                baseline["results"] = evalkit.run_suite(
                    baseline["entries"], models_dir=MODELS,
                    off_topic=evalkit.off_topic_cases(str(GENERAL / "off_topic.json")),
                    null_bank=True)

    def test_the_tuning_brains_hold_the_aggregate_and_worst_brain_floors(self):
        for baseline in self.baselines:
            with self.subTest(calibration=baseline["id"]):
                self.assertEqual(_problems(baseline["results"], baseline["minimums"]), [])

    def test_the_quick_set_ran_every_brain_it_names(self):
        for baseline in self.baselines:
            with self.subTest(calibration=baseline["id"]):
                self.assertEqual(sorted(r["name"] for r in baseline["results"]),
                                 sorted(e["name"] for e in _entries()))


if __name__ == "__main__":
    unittest.main()
