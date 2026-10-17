"""Real-model quality gates with the inputs that produced each baseline.

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
from brainkit import safeguards_eval as se

HERE = Path(__file__).resolve().parent
GENERAL = HERE / "evals" / "general"
ROOT = HERE.parents[2]
BRAINS = ROOT / "brains"
MODELS = os.environ.get("BRAIN_TEST_MODELS", "")
# Existing cross-platform arithmetic allowance, unchanged for BOTH gates.
SLACK = 0.03


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _entries(names):
    entries = evalkit.generated_brains(str(GENERAL))
    entries += evalkit.demo_brains(str(BRAINS), se.load_spec(str(HERE / "evals/retrieval.json")))
    return [e for e in entries if e["name"] in names]


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
        row["minimums"] = _json(GENERAL / row["minimums_file"])["brains"]
        row["entries"] = _entries(row["minimums"])
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
        if sorted(e["name"] for e in row["entries"]) != sorted(row["minimums"]):
            raise ValueError(f"{row['id']}: a required Brain is missing")
    return manifest, rows


def _problems(results, minimums):
    problems = []
    for result in results:
        floor = minimums[result["name"]]
        for measure, value in floor.items():
            found = evalkit.rate(result["counts"].get(measure, [0, 0]))
            if found is None:
                problems.append(f"{result['name']} {measure} was not measured")
            elif measure in evalkit.LOWER_IS_BETTER:
                if found > value + SLACK:
                    problems.append(f"{result['name']} {measure} {found:.3f} > {value}")
            elif found < value - SLACK:
                problems.append(f"{result['name']} {measure} {found:.3f} < {value}")
    return problems


class BaselineInputsTest(unittest.TestCase):
    def test_both_baselines_keep_their_recorded_inputs_and_cover_every_brain(self):
        _manifest, rows = _baselines()
        self.assertEqual(set(rows[0]["minimums"]), set(rows[1]["minimums"]))

    def test_a_required_measurement_cannot_pass_by_disappearing(self):
        results = [{"name": "sample", "counts": {"reachable": [0, 0]}}]
        self.assertEqual(_problems(results, {"sample": {"reachable": 0.9}}),
                         ["sample reachable was not measured"])


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

    def test_every_brain_in_the_quick_set_holds_its_last_measured_values(self):
        for baseline in self.baselines:
            with self.subTest(calibration=baseline["id"]):
                self.assertEqual(_problems(baseline["results"], baseline["minimums"]), [])

    def test_the_quick_set_ran_every_brain_it_names(self):
        for baseline in self.baselines:
            with self.subTest(calibration=baseline["id"]):
                self.assertEqual(sorted(r["name"] for r in baseline["results"]),
                                 sorted(baseline["minimums"]))


if __name__ == "__main__":
    unittest.main()
