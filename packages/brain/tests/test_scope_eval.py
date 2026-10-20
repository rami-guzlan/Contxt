"""The project-scope measure (Release 1 plan, M00) reads its spec and scores every request."""
from __future__ import annotations

import os
import unittest

from brainkit import scope_eval

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SPEC = os.path.join(HERE, "evals", "scope.json")


class SpecTest(unittest.TestCase):
    def test_every_needed_note_and_pin_belongs_to_its_project(self):
        spec = scope_eval.load(SPEC)
        ids = [n["id"] for n in spec["brain_wide"]]
        for project in spec["projects"]:
            own = {n["id"] for n in project["notes"]}
            ids += list(own)
            self.assertTrue(set(project["pins"]) <= own, project["key"])
            for case in project["requests"]:
                self.assertTrue(case.get("status") or case["need"] in own, case["q"])
        self.assertEqual(len(ids), len(set(ids)))


class RunTest(unittest.TestCase):
    def test_words_only_run_scores_every_request_and_dated_case(self):
        spec = scope_eval.load(SPEC)
        result = scope_eval.run(ROOT, spec)
        asked = sum(len(p["requests"]) for p in spec["projects"])
        self.assertEqual(len(result["requests"]), asked)
        self.assertEqual(len(result["updates"]), len(spec["updates"]))
        self.assertEqual(len(result["conflicts"]), len(spec["conflicts"]))
        summary = scope_eval.summary(result)
        self.assertEqual(summary["leak_free"][1], asked)
        self.assertIn("Status request delivers every pin",
                      scope_eval.markdown(result, "words only"))


if __name__ == "__main__":
    unittest.main()
