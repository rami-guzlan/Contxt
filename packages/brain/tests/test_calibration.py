"""Each Brain's own bar for "nothing here" (general-retrieval plan, stage 1): set against
requests unrelated to anyone's notes, not by numbers fitted to one Brain."""
from __future__ import annotations

import json
import os
import shutil
import unittest
from types import SimpleNamespace

from brainkit import calibration, evalkit
from brainkit import safeguards_eval as se
from brainkit.router import Policy, Router, Scored

HERE = os.path.dirname(os.path.abspath(__file__))
GENERAL = os.path.join(HERE, "evals", "general")


class WordsOnlyTest(unittest.TestCase):
    def test_a_brain_without_a_meaning_model_keeps_the_hand_set_floors(self):
        vault = se.copy_vault(os.path.join(GENERAL, "lawfirm", "vault"))
        try:
            brain = se.open_brain(vault)
            try:
                router = brain.state().router
                self.assertFalse(router.calibrated("lean_floor"))
                self.assertIsNone(router._calibration)
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


class EvidenceTest(unittest.TestCase):
    def test_evidence_is_the_share_of_unrelated_requests_a_match_beats(self):
        cal = calibration.Calibration(cos=None, bm=[1.0, 2.0, 3.0, 4.0])
        self.assertEqual(cal.evidence(None, 0.5), 0.0)
        self.assertEqual(cal.evidence(None, 3.5), 0.75)
        self.assertEqual(cal.evidence(None, 9.0), 1.0)

    def test_meaning_decides_when_the_brain_has_it(self):
        cal = calibration.Calibration(cos=[0.1, 0.2, 0.3, 0.4], bm=[1.0, 2.0, 3.0, 4.0])
        self.assertEqual(cal.evidence(0.35, 0.0), 0.75)

    def test_a_calibration_survives_a_round_trip(self):
        cal = calibration.Calibration(cos=[0.3, 0.1], bm=[2.0], domains={"d": [0.2, 0.4]},
                                      notes=7)
        again = calibration.Calibration.from_dict(json.loads(json.dumps(cal.to_dict())))
        self.assertEqual(again.cos, [0.1, 0.3])
        self.assertEqual(again.domain_share("d", 0.3), 0.5)
        self.assertEqual(again.notes, 7)

    def test_the_bank_is_shipped_with_the_engine(self):
        self.assertGreaterEqual(len(calibration.null_bank()), 250)


class SelectionEvidenceTest(unittest.TestCase):
    def test_a_match_that_fails_the_evidence_bar_cannot_hide_a_qualified_match(self):
        router = Router.__new__(Router)
        router.policy = Policy()
        router._hand = set()
        router.index = SimpleNamespace(semantic_ready=lambda: True)
        router._calibration = calibration.Calibration(cos=[0.5] * 19 + [0.9], bm=[])
        route = SimpleNamespace(task_type="combined", scale="standard",
                                signals=SimpleNamespace(include_topics=[]), log=lambda _: None)
        weak = Scored(SimpleNamespace(id="incidental", route_key="a/one"), 0.8,
                      detail={"adj": 0.8, "cos_raw": 0.8})
        strong = Scored(SimpleNamespace(id="answer", route_key="b/two"), 0.6,
                        detail={"adj": 0.6, "cos_raw": 0.96})
        next_match = Scored(SimpleNamespace(id="additional", route_key="c/three"), 0.58,
                            detail={"adj": 0.58, "cos_raw": 0.96})
        selected, related = router._select(route, [weak, strong, next_match], [], set())
        self.assertEqual([s.item.id for s in selected], ["answer"])
        self.assertEqual([s.item.id for s in related], ["incidental", "additional"])
        # Filtering must still return nothing when every candidate fails the same bar.
        selected, related = router._select(route, [weak], [], set())
        self.assertEqual(selected, [])
        self.assertEqual([s.item.id for s in related], ["incidental"])


class PointerCoverageTest(unittest.TestCase):
    def test_rules_already_carried_do_not_consume_pointer_slots(self):
        def scored(note_id, topic):
            return Scored(SimpleNamespace(id=note_id, route_key=topic), 0.6)

        rule = scored("existing-rule", "work/rules")
        first = scored("first-reference", "work/facts")
        next_rule = scored("new-area-rule", "new/rules")
        last = scored("next-reference", "new/facts")
        older = scored("old-value", "work/facts")
        current = scored("current-value", "work/facts")
        linked = Scored(first.item, first.score, detail={"linked_from": "current-value"})
        route = SimpleNamespace(
            related=[rule, linked], related_pool=[rule, first, older, next_rule, last],
            notes=[current], style_notes=[], standing_answer=[], sections=[],
            older=[(older.item, current.item)], must_holds=[], must_overflow=[])
        router = Router.__new__(Router)
        router.policy = Policy(related_count=2)
        router.index = SimpleNamespace(cards={})
        router._route = lambda *args, **kwargs: route
        router._prefer_newer = lambda _: None

        def attach(found, reached_extra=()):
            reached = set(reached_extra) | {s.item.route_key for s in found.related}
            found.must_holds = [SimpleNamespace(note=rule.item)]
            if any(topic.startswith("new/") for topic in reached):
                found.must_holds.append(SimpleNamespace(note=next_rule.item))

        router._attach_must_holds = attach
        found = router.route("Prepare the project summary", [])
        self.assertEqual([s.item.id for s in found.related],
                         ["first-reference", "next-reference"])
        self.assertEqual(found.related[0].detail.get("linked_from"), "current-value")
        self.assertEqual({m.note.id for m in found.must_holds},
                         {"existing-rule", "new-area-rule"})
        self.assertNotIn("old-value", [s.item.id for s in found.related])


MODELS = os.environ.get("BRAIN_TEST_MODELS", "")


def _words_calibrated(vault):
    with open(os.path.join(vault, "routing.json"), "w", encoding="utf-8") as handle:
        json.dump({"policy": {"calibrated_words": True}}, handle)


class CalibratedRoutingTest(unittest.TestCase):
    """On a generated Brain nobody tuned: by meaning when the model is here (as CI's model
    job runs it), else by words with the calibration asked for."""

    def setUp(self):
        self.vault = se.copy_vault(os.path.join(GENERAL, "lawfirm", "vault"),
                                   MODELS if os.path.isdir(MODELS or "-") else None)
        evalkit.zero_config(self.vault)
        if not os.path.isdir(MODELS or "-"):
            _words_calibrated(self.vault)
        self.brain = se.open_brain(self.vault, semantic=os.path.isdir(MODELS or "-"))

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def _notes(self, request):
        data = self.brain.context(request, record=False, include_kernel=False).data
        return data.get("note_ids") or []

    def test_a_general_question_that_shares_a_word_with_a_note_gets_nothing(self):
        self.assertEqual(self._notes("What is the capital of Peru?"), [])
        self.assertEqual(self._notes("How many strings does a violin have?"), [])

    def test_a_request_about_the_work_still_gets_its_notes(self):
        self.assertIn("trust-account-money",
                      self._notes("A client wants to pay the full flat fee up front. "
                                  "Where does that money go until the work is done?"))

    def test_a_floor_set_by_hand_in_routing_json_still_decides(self):
        with open(os.path.join(self.vault, "routing.json"), "w", encoding="utf-8") as h:
            json.dump({"policy": {"lean_floor": 0.0, "note_abs_floor": 0.0,
                                  "calibrated_words": True}}, h)
        self.brain.close()
        self.brain = se.open_brain(self.vault)
        self.assertNotEqual(self._notes("What is the capital of Peru?"), [])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.path.isdir(MODELS or "-"), "needs BRAIN_TEST_MODELS with bge-small")
class TiersTest(unittest.TestCase):
    """Whole notes only when the Brain is confident; the rest as pointers (plan 3.4)."""

    def setUp(self):
        self.vault = se.copy_vault(os.path.join(GENERAL, "lawfirm", "vault"), MODELS)
        evalkit.zero_config(self.vault)
        self.brain = se.open_brain(self.vault, semantic=True)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_whole_notes_are_the_confident_top_and_the_next_ones_are_pointers(self):
        request = "Draft a reply to a client asking what we charge for a naturalization case"
        router = self.brain.state().router
        data = self.brain.context(request, record=False, include_kernel=False,
                                  explain=True).data
        scores = {s["id"]: s for s in data["trace"]["note_scores"]}
        whole = data["note_ids"]
        self.assertTrue(whole)
        best = max(scores[i]["adj"] for i in whole)
        for note_id in whole:
            self.assertGreaterEqual(scores[note_id]["adj"],
                                    router.policy.whole_relative * best - 0.051)
        self.assertTrue(data["related_ids"])
        self.assertFalse(set(whole) & set(data["related_ids"]))


class PointerTest(unittest.TestCase):
    def test_a_pointer_says_what_its_note_holds(self):
        vault = se.copy_vault(os.path.join(HERE, "..", "..", "..", "brains",
                                           "knowledge-company", "vault"))
        try:
            brain = se.open_brain(vault)
            try:
                res = brain.context("Draft the newsletter intro for this month", record=False)
            finally:
                brain.close()
            pointers = res.text.split("## Also relevant (not included)", 1)
            self.assertEqual(len(pointers), 2)
            first = pointers[1].strip().splitlines()[0]
            self.assertRegex(first, r"^- .+ \(`[^`]+`, [^)]+\): .{10,}")
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
