"""Enrichment at the door (general-retrieval plan, stage 3): one model answer per note
writes how a person would ask for it, and the note is found by those words."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import enrich
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
LAWFIRM = os.path.join(HERE, "evals", "general", "lawfirm", "vault")
MODELS = os.environ.get("BRAIN_TEST_MODELS", "")

ANSWER = json.dumps({
    "asked_as": ["what do we charge to file for citizenship",
                 "price for a naturalization case",
                 "how much is the N-400 package — our fee",
                 "price for a naturalization case"],
    "applies_when": "quoting or explaining fees for a citizenship case",
    "not_when": "government filing fees the client pays the agency",
    "role": "Knowledge", "triggers": ["ignored"]})


class ParseTest(unittest.TestCase):
    def test_an_answer_becomes_clean_fields(self):
        found = enrich.parse("Sure, here it is:\n" + ANSWER)
        self.assertEqual(found["asked_as"][1], "price for a naturalization case")
        self.assertEqual(len(found["asked_as"]), 3)  # the repeated line once
        self.assertNotIn("—", found["asked_as"][2])
        self.assertEqual(found["role"], "knowledge")
        self.assertNotIn("triggers", found)

    def test_a_must_hold_answer_keeps_its_trigger_words(self):
        found = enrich.parse(ANSWER, must_hold=True)
        self.assertEqual(found["triggers"], ["ignored"])

    def test_an_answer_with_too_few_ways_to_ask_is_refused_in_plain_words(self):
        with self.assertRaisesRegex(ValueError, "at least 3"):
            enrich.parse('{"asked_as": ["one"], "role": "rule"}')
        with self.assertRaisesRegex(ValueError, "no JSON"):
            enrich.parse("I cannot help with that.")

    def test_an_unknown_role_reads_as_knowledge(self):
        found = enrich.parse(ANSWER.replace("Knowledge", "trivia"))
        self.assertEqual(found["role"], "knowledge")


class ApplyTest(unittest.TestCase):
    def setUp(self):
        from brainkit import evalkit
        self.vault = se.copy_vault(LAWFIRM)
        evalkit.strip_enrichment(self.vault)  # the test Brain ships enriched
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def _note(self, note_id):
        return self.brain.state().index.note(note_id)

    def test_the_prompt_reads_the_note_and_asks_a_must_hold_for_trigger_words(self):
        plain = enrich.prompt_for(self._note("consultation-fee"))
        self.assertIn(self._note("consultation-fee").title, plain)
        self.assertNotIn('"triggers"', plain)
        must = enrich.prompt_for(self._note("asylum-one-year-deadline"))
        self.assertIn('"triggers"', must)
        self.assertIn("must always hold", must)

    def test_an_applied_answer_is_written_into_the_note_and_it_is_no_longer_pending(self):
        self.assertTrue(enrich.needs(self._note("consultation-fee")))
        result = enrich.apply(self.brain, "consultation-fee", ANSWER, by="model:test")
        self.assertFalse(result.is_error, result.text)
        note = self._note("consultation-fee")
        self.assertIn("price for a naturalization case", note.asked_as)
        self.assertEqual(note.applies_when, "quoting or explaining fees for a citizenship case")
        self.assertEqual(note.meta["enriched_by"], "model:test")
        self.assertFalse(enrich.needs(note))
        self.assertNotIn("consultation-fee", [n.id for n in enrich.pending(
            self.brain.state().index)])

    def test_a_note_whose_text_changed_is_enriched_again(self):
        enrich.apply(self.brain, "consultation-fee", ANSWER, by="model:test")
        note = self._note("consultation-fee")
        se.set_meta(self.vault, ["consultation-fee"], summary="A different summary now.")
        self.brain.close()
        self.brain = se.open_brain(self.vault)
        self.assertNotEqual(note.summary, self._note("consultation-fee").summary)
        self.assertTrue(enrich.needs(self._note("consultation-fee")))

    def test_suggested_trigger_words_wait_for_the_owner(self):
        answer = ANSWER.replace('["ignored"]', '["asylum", "persecution", "filing late"]')
        enrich.apply(self.brain, "asylum-one-year-deadline", answer, by="model:test")
        note = self._note("asylum-one-year-deadline")
        self.assertEqual(note.triggers, [])
        self.assertEqual(note.meta["suggested_triggers"],
                         ["asylum", "persecution", "filing late"])
        owner = self.brain.state().config.owner
        result = enrich.accept_triggers(self.brain, "asylum-one-year-deadline", actor=owner)
        self.assertFalse(result.is_error, result.text)
        note = self._note("asylum-one-year-deadline")
        self.assertEqual(note.triggers, ["asylum", "persecution", "filing late"])
        self.assertNotIn("suggested_triggers", note.meta)

    def test_a_note_is_found_by_the_words_it_is_asked_by(self):
        request = "what is our price to file for citizenship"
        before = self.brain.context(request, record=False, include_kernel=False).data
        enrich.apply(self.brain, "consultation-fee", ANSWER, by="model:test")
        after = self.brain.context(request, record=False, include_kernel=False,
                                   explain=True).data
        scores = {s["id"]: s for s in after["trace"]["note_scores"]}
        old = {s["id"]: s for s in self.brain.context(
            request, record=False, explain=True, include_kernel=False).data[
                "trace"]["note_scores"]}
        self.assertIn("consultation-fee", scores)
        self.assertGreaterEqual(scores["consultation-fee"]["rel"],
                                old["consultation-fee"]["rel"])
        self.assertIsNotNone(before)


@unittest.skipUnless(os.path.isdir(MODELS or "-"), "needs BRAIN_TEST_MODELS with bge-small")
class MeaningTest(unittest.TestCase):
    def test_a_note_scores_by_the_closest_of_its_text_and_its_ask_lines(self):
        from brainkit import evalkit
        vault = se.copy_vault(LAWFIRM, MODELS)
        evalkit.strip_enrichment(vault)
        try:
            brain = se.open_brain(vault, semantic=True)
            try:
                request = "what is our price to file for citizenship"
                before = brain.state().index.similarity(request)["note:consultation-fee"]
                enrich.apply(brain, "consultation-fee", ANSWER, by="model:test")
                index = brain.state().index
                after = index.similarity(request)["note:consultation-fee"]
                self.assertGreater(after, before)
                self.assertNotIn("ask:consultation-fee:0", index.similarity(request))
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class TopicTextTest(unittest.TestCase):
    def test_a_topic_without_a_line_is_described_by_the_work_its_notes_are_for(self):
        vault = se.copy_vault(LAWFIRM)
        try:
            brain = se.open_brain(vault)
            try:
                index = brain.state().index
                note = index.note("consultation-fee")
                self.assertTrue(note.applies_when)  # the test Brain ships enriched
                self.assertIn(note.applies_when, index.topic_texts[note.route_key])
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
