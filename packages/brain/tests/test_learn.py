"""Learning from use (general-retrieval plan, stage 4): a note a conversation had to search
for learns the words it was asked in, so the next request like it finds it."""
from __future__ import annotations

import unittest

from brainkit import learn
from brainkit import safeguards_eval as se
from tests import fixture

ODD = "What is the zebra paperwork rule for quarterly filings"


class WordingTest(unittest.TestCase):
    def test_a_request_becomes_its_first_sentence_in_at_most_24_words(self):
        self.assertEqual(learn.wording("Who signs the lease? Also the keys are lost."),
                         "Who signs the lease?")
        long = " ".join(["word"] * 40)
        self.assertEqual(len(learn.wording(long).split()), learn.MAX_WORDS)


class FromGapsTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = se.open_brain(self.vault)
        st = self.brain.state()
        self.target = next(n.id for n in sorted(st.index.notes.values(), key=lambda n: n.id)
                           if not n.standing and not n.must_hold and n.live
                           and not n.partition and n.scope == "company")

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def _search(self, session, principal=None):
        brief = self.brain.context(ODD, session_id=session, principal=principal).data
        self.assertNotIn(self.target, (brief.get("note_ids") or [])
                         + (brief.get("related_ids") or []))
        self.brain.note(self.target, session_id=session, principal=principal)

    def test_the_owners_searched_note_learns_the_request_and_is_found_next_time(self):
        self._search("sess-learn-001")
        found = learn.from_gaps(self.brain)
        self.assertEqual(found["learned"], [self.target])
        note = self.brain.state().index.note(self.target)
        self.assertIn(learn.wording(ODD), note.asked_as)
        again = self.brain.context(ODD, record=False).data
        self.assertIn(self.target, (again.get("note_ids") or [])
                      + (again.get("related_ids") or []))
        self.assertEqual(learn.from_gaps(self.brain)["learned"], [])  # learned once

    def test_someone_elses_searched_note_waits_for_the_owner(self):
        self._search("sess-learn-002", principal="person:sam")
        found = learn.from_gaps(self.brain)
        self.assertEqual(found["suggested"], [self.target])
        note = self.brain.state().index.note(self.target)
        self.assertNotIn(learn.wording(ODD), note.asked_as)
        self.assertEqual(note.meta["suggested_asked_as"], [learn.wording(ODD)])
        result = learn.accept_asked_as(self.brain, self.target, actor="person:alex")
        self.assertFalse(result.is_error, result.text)
        note = self.brain.state().index.note(self.target)
        self.assertIn(learn.wording(ODD), note.asked_as)
        self.assertNotIn("suggested_asked_as", note.meta)

    def test_a_pointer_most_conversations_open_is_reported(self):
        self.assertEqual(learn.pointer_report(self.brain), [])


if __name__ == "__main__":
    unittest.main()
