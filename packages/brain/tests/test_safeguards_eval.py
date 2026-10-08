"""The safeguard evaluations: the harness itself, and the bars each built phase must hold.

The cases are in tests/evals/. They run on scratch copies of the packaged demo Brains with
matching by words only, as CI does; scripts/safeguards_eval.py reports the same numbers with
meaning-matching too.
"""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import review
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
EVALS = os.path.join(HERE, "evals")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")


def _spec(name):
    return se.load_spec(os.path.join(EVALS, name))


class EvalDataTest(unittest.TestCase):
    def test_every_must_hold_case_names_a_real_note_with_eight_requests_and_four_decoys(self):
        for case in _spec("must_holds.json")["cases"]:
            vault = os.path.join(BRAINS, case["brain"], "vault")
            self.assertIn(case["note"], se._note_files(vault), case["note"])
            self.assertEqual(len(case["requests"]), 8, case["note"])
            self.assertEqual(len(case["decoys"]), 4, case["note"])

    def test_tension_pairs_are_labeled_with_known_relations(self):
        pairs = _spec("tension_pairs.json")["pairs"]
        self.assertEqual(len(pairs), 60)
        relations = {p["relation"] for p in pairs}
        self.assertLessEqual(relations, {"contradicts", "narrows", "extends", "agrees",
                                         "unrelated"})
        self.assertEqual(sum(p["relation"] == "contradicts" for p in pairs), 24)


class HarnessTest(unittest.TestCase):
    def test_scratch_copies_take_meta_changes_and_new_notes_without_touching_the_source(self):
        source = os.path.join(BRAINS, "personal", "vault")
        vault = se.copy_vault(source)
        try:
            self.assertEqual(se.set_meta(vault, ["family-ollie"], load="on-demand"),
                             ["family-ollie"])
            se.add_notes(vault, [{"id": "scratch-note", "area": "money", "topic": "budget",
                                  "body": "A scratch figure: 12.", "as_of": "2026-01-01"}])
            brain = se.open_brain(vault)
            try:
                st = brain.state()
                self.assertEqual(st.index.notes["family-ollie"].load, "on-demand")
                self.assertIn("scratch-note", st.index.notes)
            finally:
                brain.close()
            original = brain_meta(source, "family-ollie")
            self.assertNotEqual(original.get("load"), "on-demand")
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)

    def test_tension_scores_count_contradictions_only(self):
        pairs = [{"a": "x", "b": "y", "relation": "contradicts"},
                 {"a": "x", "b": "z", "relation": "agrees"}]
        result = se.tension_eval(pairs, lambda a, b: b == "y")
        self.assertEqual((result["recall"], result["precision"]), (1.0, 1.0))
        result = se.tension_eval(pairs, lambda a, b: True)
        self.assertEqual((result["recall"], result["precision"]), (1.0, 0.5))

    def test_the_sentence_heuristic_keeps_its_measured_floor(self):
        # Phase 0 measured 38% recall at 82% precision; it must not get worse, because the
        # baseline check keeps it as its first, free check.
        result = se.tension_eval(_spec("tension_pairs.json")["pairs"],
                                 lambda a, b: review.contradiction(b, a))
        self.assertGreaterEqual(result["recall"], 0.375)
        self.assertGreaterEqual(result["precision"], 0.8)


class MustHoldBarsTest(unittest.TestCase):
    """Phase A's bars, words only (with meaning-matching the held-out recall is higher)."""

    def test_must_holds_reach_every_in_domain_request_and_few_decoys(self):
        result = se.run_must_holds(BRAINS, _spec("must_holds.json"))
        self.assertEqual(result["recall"], 1.0, result["misses"])
        self.assertLessEqual(result["decoy_rate"], 0.15, result["decoy_hits"])
        # Measured 79% (19 of 24) on October 8, 2026; must not fall.
        self.assertGreaterEqual(result["held_out_recall"], 0.79, result["misses"])


class BaselineCheckBarsTest(unittest.TestCase):
    """Phase B's bars. Checks 1 and 2 stay precise and hold few ordinary notes; with your own
    AI's saved verdicts on the same pairs (check 3, docs/evals/tension-verdicts.json),
    contradictions are found at the spec's bar on the tuning and the held-out pairs."""

    def test_checks_one_and_two_are_precise_and_hold_few_ordinary_notes(self):
        from brainkit import tension
        result = se.tension_eval(_spec("tension_pairs.json")["pairs"],
                                 lambda a, b: tension.tension(b, a))
        # Measured 58% recall at 100% precision on October 8, 2026.
        self.assertGreaterEqual(result["recall"], 0.58, result["missed"])
        self.assertEqual(result["precision"], 1.0, result["false_alarms"])
        ordinary = se.held_ordinary(BRAINS)
        # Measured 4 of 81 (5%); before the overlap bar it was 32 of 81.
        self.assertLessEqual(ordinary["rate"], 0.1, ordinary["held"])

    def test_with_your_own_ais_verdicts_contradictions_are_found(self):
        import json

        from brainkit import tension
        with open(os.path.join(ROOT, "docs", "evals", "tension-verdicts.json"),
                  encoding="utf-8") as handle:
            saved = {(row["a"], row["b"]): row["model"] for row in json.load(handle)}
        for name in ("tension_pairs.json", "tension_holdout.json"):
            found = se.verdicts_eval(_spec(name)["pairs"], saved,
                                     lambda a, b: tension.tension(b, a))
            self.assertEqual(found["read"], len(_spec(name)["pairs"]), name)
            self.assertGreaterEqual(found["combined"]["recall"], 0.9, name)
            self.assertGreaterEqual(found["combined"]["precision"], 0.8, name)


def brain_meta(vault, note_id):
    from brainkit import frontmatter as fm
    from brainkit import util
    meta, _body, _errors = fm.parse(util.read_text(se._note_files(vault)[note_id]))
    return meta


if __name__ == "__main__":
    unittest.main()
