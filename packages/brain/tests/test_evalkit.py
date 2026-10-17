"""The multi-Brain retrieval harness (general-retrieval plan, stage 0): its arithmetic, the
zero-config copy every headline number is measured on, and the generated test Brains' data.

The scoring runs themselves are in test_general_eval.py; these checks need no model.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from brainkit import evalkit
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
GENERAL = os.path.join(HERE, "evals", "general")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")


class WilsonTest(unittest.TestCase):
    def test_an_interval_brackets_the_rate_and_narrows_with_more_cases(self):
        low, high = evalkit.wilson(8, 10)
        self.assertLess(low, 0.8)
        self.assertGreater(high, 0.8)
        wide = high - low
        low, high = evalkit.wilson(80, 100)
        self.assertLess(high - low, wide)

    def test_known_values(self):
        low, high = evalkit.wilson(8, 10)
        self.assertAlmostEqual(low, 0.490, places=3)
        self.assertAlmostEqual(high, 0.943, places=3)

    def test_all_or_none_stays_inside_zero_and_one(self):
        low, high = evalkit.wilson(10, 10)
        self.assertEqual(high, 1.0)
        self.assertGreater(low, 0.6)
        low, high = evalkit.wilson(0, 10)
        self.assertEqual(low, 0.0)

    def test_no_cases_has_no_interval(self):
        self.assertIsNone(evalkit.wilson(0, 0))


class AcrossBrainsTest(unittest.TestCase):
    def test_the_mean_weighs_each_brain_alike_and_the_worst_brain_is_named(self):
        results = [
            {"name": "big", "split": "tuning", "counts": {"recall": [90, 100]}},
            {"name": "small", "split": "tuning", "counts": {"recall": [5, 10]}},
        ]
        summary = evalkit.across(results)["recall"]
        self.assertAlmostEqual(summary["mean"], 0.7)
        self.assertEqual(summary["worst"], {"brain": "small", "rate": 0.5})
        self.assertAlmostEqual(summary["pooled"], 95 / 110, places=3)

    def test_for_a_bad_measure_the_worst_brain_is_the_highest(self):
        results = [
            {"name": "a", "split": "tuning", "counts": {"false_nothing": [1, 20]}},
            {"name": "b", "split": "tuning", "counts": {"false_nothing": [6, 20]}},
        ]
        self.assertEqual(evalkit.across(results)["false_nothing"]["worst"]["brain"], "b")

    def test_a_brain_without_cases_for_a_measure_is_left_out_of_it(self):
        results = [
            {"name": "a", "split": "tuning", "counts": {"recall": [3, 4]}},
            {"name": "b", "split": "tuning", "counts": {"recall": [0, 0]}},
        ]
        self.assertEqual(evalkit.across(results)["recall"]["brains"], 1)

    def test_leave_one_out_never_fits_on_the_brain_it_scores(self):
        brains = [{"name": n} for n in ("a", "b", "c")]
        seen = []

        def fit(train):
            return sorted(b["name"] for b in train)

        def score(brain, fitted):
            seen.append((brain["name"], fitted))
            return {"name": brain["name"]}

        evalkit.leave_one_out(brains, fit, score)
        for name, fitted in seen:
            self.assertNotIn(name, fitted)
            self.assertEqual(len(fitted), 2)


class ZeroConfigTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "personal", "vault"))

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_a_zero_config_copy_has_no_routing_no_topic_lines_and_no_trigger_words(self):
        evalkit.zero_config(self.vault)
        with open(os.path.join(self.vault, "routing.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {})
        with open(os.path.join(self.vault, "topics.md"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), "# Topics")
        for path in se._note_files(self.vault).values():
            with open(path, encoding="utf-8") as handle:
                self.assertNotIn("\ntriggers:", handle.read(), path)

    def test_zero_config_keeps_every_note(self):
        before = set(se._note_files(self.vault))
        evalkit.zero_config(self.vault)
        self.assertEqual(set(se._note_files(self.vault)), before)


class GeneratedBrainsTest(unittest.TestCase):
    """The generated test Brains: a persona, its notes, requests written without seeing the
    notes, and labels written by reading them."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(GENERAL, "splits.json"), encoding="utf-8") as handle:
            cls.splits = json.load(handle)

    def test_every_split_is_known_and_each_kind_has_brains(self):
        self.assertLessEqual(set(self.splits.values()), {"tuning", "validation", "sealed"})
        for split in ("tuning", "validation", "sealed"):
            self.assertIn(split, self.splits.values())

    def test_every_labeled_brain_names_real_notes_for_every_request(self):
        entries = evalkit.generated_brains(GENERAL)
        self.assertTrue(entries)
        for entry in entries:
            known = set(se._note_files(entry["vault"]))
            with open(os.path.join(GENERAL, entry["name"], "requests.json"),
                      encoding="utf-8") as handle:
                requests = json.load(handle)
            self.assertEqual([c["id"] for c in entry["cases"]], [r["id"] for r in requests],
                             entry["name"])
            for case in entry["cases"]:
                named = {i for group in case["must"] for i in group}
                named |= set(case["useful"]) | set(case["noise"]) | set(case["must_holds"])
                self.assertLessEqual(named, known, case["id"])
                if case["nothing"]:
                    self.assertFalse(case["must"] or case["useful"], case["id"])

    def test_every_generated_brain_starts_as_nobody_tuned_it(self):
        for entry in evalkit.generated_brains(GENERAL):
            with open(os.path.join(entry["vault"], "routing.json"), encoding="utf-8") as h:
                self.assertEqual(json.load(h), {}, entry["name"])
            with open(os.path.join(entry["vault"], "topics.md"), encoding="utf-8") as h:
                self.assertEqual(h.read().strip(), "# Topics", entry["name"])

    def test_every_generated_brain_passes_its_health_check(self):
        from brainkit.api import Brain
        for entry in evalkit.generated_brains(GENERAL):
            vault = se.copy_vault(entry["vault"])
            try:
                brain = Brain(vault, embeddings=False)
                try:
                    health = brain.health()
                finally:
                    brain.close()
                self.assertTrue(health.data.get("ok"), entry["name"] + "\n" + health.text)
            finally:
                shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


class ScaleTest(unittest.TestCase):
    def test_a_scale_brain_has_the_size_asked_for_and_every_note_is_distinct(self):
        sources = [os.path.join(BRAINS, n, "vault") for n in ("personal", "programmer")]
        vault = evalkit.scale_vault(sources, 150)
        try:
            files = se._note_files(vault)
            self.assertEqual(len(files), 150)
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)

    def test_latency_is_measured_on_a_brain_of_that_size(self):
        sources = [os.path.join(BRAINS, "personal", "vault")]
        found = evalkit.latency_at(sources, 60, ["plan dinner for Tuesday", "what is due"])
        self.assertGreaterEqual(found["notes"], 60)
        self.assertGreater(found["p95"], 0)


def _script(name):
    import importlib.util
    path = os.path.join(ROOT, "scripts", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LongMemEvalAdapterTest(unittest.TestCase):
    """A question in LongMemEval's shape, invented here: its history becomes a Brain, one
    note per turn the person wrote, and the marked turns are what the request needs."""

    ITEM = {
        "question_id": "q1", "question_type": "single-session-user",
        "question": "What breed is my dog?", "answer": "A whippet",
        "haystack_session_ids": ["s-a", "s-b"],
        "haystack_dates": ["2023/05/20 (Sat) 02:21", "2023/05/22 (Mon) 10:00"],
        "haystack_sessions": [
            [{"role": "user", "content": "Help me plan a birthday party for my niece."},
             {"role": "assistant", "content": "Sure, here are some ideas."}],
            [{"role": "user", "content": "My whippet Juno pulls on the leash, any tips?",
              "has_answer": True},
             {"role": "assistant", "content": "Try a front-clip harness."},
             {"role": "user", "content": "Thanks, what about treats?"},
             {"role": "assistant", "content": "Small soft ones work best."}]],
        "answer_session_ids": ["s-b"],
    }

    def test_a_question_becomes_a_brain_whose_marked_turn_is_the_needed_note(self):
        adapter = _script("third_party_eval")
        vault, case = adapter.question_brain(self.ITEM)
        try:
            files = se._note_files(vault)
            self.assertEqual(len(files), 3)
            self.assertEqual(len(case["must"]), 1)
            (needed,) = case["must"][0]
            with open(files[needed], encoding="utf-8") as handle:
                self.assertIn("whippet", handle.read())
            self.assertEqual(case["request"], "What breed is my dog?")
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)

    def test_abstention_questions_are_left_out_and_each_type_is_sampled(self):
        adapter = _script("third_party_eval")
        items = [dict(self.ITEM, question_id=f"q{i}", question_type=t)
                 for i, t in enumerate(["a", "a", "a", "b", "b"])]
        items.append(dict(self.ITEM, question_id="q9_abs", question_type="b"))
        chosen = adapter.sample(items, 2)
        self.assertEqual(sorted(i["question_type"] for i in chosen), ["a", "a", "b", "b"])
        self.assertNotIn("q9_abs", [i["question_id"] for i in chosen])


class OffTopicSetTest(unittest.TestCase):
    def test_the_scoring_set_never_repeats_a_calibration_request(self):
        null = {r.lower() for r in evalkit.null_requests()}
        self.assertGreaterEqual(len(null), 250)
        scoring = evalkit.off_topic_cases(os.path.join(GENERAL, "off_topic.json"))
        self.assertGreaterEqual(len(scoring), 100)
        for case in scoring:
            self.assertNotIn(case["request"].lower(), null, case["id"])
            self.assertTrue(case["nothing"])


class PrivateBrainTest(unittest.TestCase):
    def test_a_private_brain_reports_numbers_and_never_its_requests_or_notes(self):
        root = tempfile.mkdtemp(prefix="private-")
        try:
            result = {"name": "private", "split": "private", "private": True,
                      "counts": {"recall": [3, 4]},
                      "rows": [{"id": "secret-1", "request": "a secret request",
                                "missed": [["secret-note"]], "noise": []}]}
            text = evalkit.markdown([result], title="t")
            self.assertNotIn("secret", text)
            self.assertIn("75%", text)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
