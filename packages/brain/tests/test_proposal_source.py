"""Every proposal carries where it came from (source, version, location, speaker, excerpt),
how it was said (stated, tentative or conditional), and an operation id that makes a retry
harmless; an owner who rewords a proposal keeps their version and the original stays on
record (Release 1 plan, M02 and M03)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import governance, statements
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SOURCE = {"source_id": "context_item:ci_042", "source_version": "rev 2 · 3f9a1c",
          "source_locator": "02:10", "source_speaker": "Morgan Lee",
          "source_excerpt": "Morgan: Dana said yes for the twelfth, so session two is set."}


class StatementStatusTest(unittest.TestCase):
    def test_hedged_words_stay_tentative_and_conditions_stay_conditional(self):
        self.assertEqual(statements.statement_status("We might move the launch to May."),
                         "tentative")
        self.assertEqual(statements.statement_status("If the grant comes through, we hire."),
                         "conditional")
        self.assertEqual(statements.statement_status("Dana is confirmed for November 12."),
                         "stated")


class ProposalSourceTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def propose(self, text, **extra):
        return governance.propose_note(
            self.brain, area="work", topic="events", text=text, title="Session 2 guest",
            force_pending=True, **{**SOURCE, **extra})

    def test_the_source_reference_is_on_the_proposal_and_on_the_kept_note(self):
        made = self.propose("Dana Ruiz is confirmed for November 12.", op_id="op-1")
        self.assertFalse(made.is_error, made.text)
        row = governance.inbox(self.brain).data["proposals"][0]
        self.assertEqual(row["source"], {"id": "context_item:ci_042",
                                         "version": "rev 2 · 3f9a1c", "locator": "02:10",
                                         "speaker": "Morgan Lee",
                                         "excerpt": SOURCE["source_excerpt"]})
        self.assertEqual(row["operation"], "new note")
        self.assertEqual(row["statement_status"], "stated")
        kept = governance.approve(self.brain, made.data["proposal_id"], actor="person:me")
        self.assertFalse(kept.is_error, kept.text)
        note = self.brain.state().index.note(made.data["id"])
        self.assertEqual(note.meta["source_locator"], "02:10")
        self.assertEqual(note.meta["source_speaker"], "Morgan Lee")

    def test_the_same_operation_id_never_makes_a_second_proposal(self):
        first = self.propose("Dana Ruiz is confirmed for November 12.", op_id="op-7")
        again = self.propose("Dana Ruiz is confirmed for Nov 12, session two.", op_id="op-7")
        self.assertEqual(again.data["status"], "duplicate")
        self.assertEqual(again.data["proposal_id"], first.data["proposal_id"])
        self.assertEqual(len(governance.inbox(self.brain).data["proposals"]), 1)

    def test_a_source_without_a_speaker_says_unknown(self):
        made = self.propose("Dana Ruiz is confirmed for November 12.", source_speaker="")
        row = governance.inbox(self.brain).data["proposals"][0]
        self.assertEqual(row["source"]["speaker"], "unknown")
        self.assertFalse(made.is_error)

    def test_an_owner_who_rewords_keeps_their_version_and_the_original_stays(self):
        made = self.propose("Dana Ruiz is confirmed for November 12.")
        kept = governance.approve(self.brain, made.data["proposal_id"], actor="person:me",
                                  body="Dana Ruiz headlines session 2 on November 12.")
        self.assertFalse(kept.is_error, kept.text)
        note = self.brain.state().index.note(made.data["id"])
        self.assertEqual(note.body.strip(), "Dana Ruiz headlines session 2 on November 12.")
        self.assertEqual(note.meta["said_by"], "owner")
        self.assertEqual(note.meta["original_text"], "Dana Ruiz is confirmed for November 12.")
        self.assertEqual(note.meta["source_speaker"], "Morgan Lee")


if __name__ == "__main__":
    unittest.main()
