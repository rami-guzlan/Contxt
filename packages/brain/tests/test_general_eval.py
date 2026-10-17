"""The quick set of the multi-Brain retrieval measure, by meaning, held at its last measured
values (general-retrieval plan 4.5): two generated Brains and the demos, zero-config, asked
their own requests, the off-topic scoring set and the calibration bank.

Needs BRAIN_TEST_MODELS (a folder holding bge-small-en-v1.5), as CI's Model tests job sets.
The values are in tests/evals/general/minimums.json; a stage that raises them writes them
again with `scripts/general_eval.py --quick --models <dir> --minimums <file>`.
"""
from __future__ import annotations

import json
import os
import unittest

from brainkit import evalkit
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
GENERAL = os.path.join(HERE, "evals", "general")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")
MODELS = os.environ.get("BRAIN_TEST_MODELS", "")
# One request's worth of give, so a borderline case that flips on another machine's
# arithmetic does not fail the build; a real drop is bigger than this.
SLACK = 0.03


def _have_model() -> bool:
    return bool(MODELS) and os.path.isdir(MODELS)


@unittest.skipUnless(_have_model(), "needs BRAIN_TEST_MODELS with bge-small-en-v1.5")
class QuickSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(GENERAL, "minimums.json"), encoding="utf-8") as handle:
            cls.minimums = json.load(handle)
        entries = [e for e in evalkit.generated_brains(GENERAL)
                   if e["name"] in cls.minimums["brains"]]
        entries += [e for e in evalkit.demo_brains(
            BRAINS, se.load_spec(os.path.join(HERE, "evals", "retrieval.json")))
            if e["name"] in cls.minimums["brains"]]
        cls.results = evalkit.run_suite(
            entries, models_dir=MODELS,
            off_topic=evalkit.off_topic_cases(os.path.join(GENERAL, "off_topic.json")),
            null_bank=True)

    def test_every_brain_in_the_quick_set_holds_its_last_measured_values(self):
        problems = []
        for result in self.results:
            floor = self.minimums["brains"][result["name"]]
            for measure, value in floor.items():
                found = evalkit.rate(result["counts"][measure])
                if found is None:
                    continue
                if measure in evalkit.LOWER_IS_BETTER:
                    if found > value + SLACK:
                        problems.append(f"{result['name']} {measure} {found:.3f} > {value}")
                elif found < value - SLACK:
                    problems.append(f"{result['name']} {measure} {found:.3f} < {value}")
        self.assertEqual(problems, [])

    def test_the_quick_set_ran_every_brain_it_names(self):
        self.assertEqual(sorted(r["name"] for r in self.results),
                         sorted(self.minimums["brains"]))


if __name__ == "__main__":
    unittest.main()
