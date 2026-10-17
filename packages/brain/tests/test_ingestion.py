"""Ingestion (brain-logic plan 7.1): who said it, recorded at the door; an instruction found
inside content kept as what it is, never as a rule; and evidence that is real: a quote an AI
attributes to the person is checked against what they said in that conversation."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import safeguards_eval as se
from brainkit import statements
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
BRAINS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "brains")
SESSION = "5f0e7c1a-4444-4c2e-9a37-2f1d1c0e9b10"


class DoorTest(unittest.TestCase):
    def test_who_said_it_comes_from_how_and_where_it_came(self):
        door = statements.said_at_door
        self.assertEqual(door("file:brief.pdf"), "document")
        self.assertEqual(door("meeting:kickoff"), "person")
        self.assertEqual(door("run:task_1"), "agent")
        self.assertEqual(door("import:instructions"), "owner")  # Moving in: the owner's file
        # An AI app's exported history gives the person's own messages, read by code.
        self.assertEqual(door("import:chatgpt"), "owner")
        self.assertEqual(door("import:claude"), "owner")
        self.assertEqual(door(None, "app"), "owner")
        self.assertEqual(door(None, "chat"), "owner-ai")
        self.assertEqual(door(None, "folder"), "document")
        self.assertEqual(door(None, None, SESSION), "owner-ai")
        self.assertEqual(door("file:x", own="person"), "person")  # the proposer's word wins
        self.assertEqual(door(), "")

    def test_quotes_are_found_and_checked_against_what_was_said(self):
        evidence = 'They said “always send the deck a day early” in the call.'
        self.assertEqual(statements.quotes(evidence), ["always send the deck a day early"])
        self.assertEqual(statements.unheard(evidence, ["Please always send the deck, a day "
                                                       "early, to the client."]), [])
        self.assertEqual(statements.unheard(evidence, ["Send it whenever."]),
                         ["always send the deck a day early"])
        self.assertEqual(statements.quotes('A short "quote" only.'), [])


class ProposalsTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)
        self.owner = self.brain.state().config.owner

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def target(self, made):
        self.assertFalse(made.is_error, made.text)
        inbox = self.brain.inbox().data.get("proposals") or []
        found = next((p["target"] for p in inbox if p["id"] == made.data["proposal_id"]), None)
        if found is None:  # applied at once
            found = dict(self.brain.state().index.note(made.data["id"]).meta)
            found["body"] = self.brain.state().index.note(made.data["id"]).body
        return found

    def test_an_instruction_inside_a_document_is_reported_never_a_rule(self):
        made = self.brain.propose(
            area="marketing", topic="channels", text="Always post to LinkedIn before 9am.",
            note_kind="rule", principal=self.owner, origin="file:agency-brief.pdf",
            force_pending=True)
        target = self.target(made)
        self.assertEqual((target["kind"], target["said_by"]), ("fact", "document"))
        self.assertEqual(target["instruction_from"], "file:agency-brief.pdf")
        self.assertIn("The document says: Always post to LinkedIn before 9am.",
                      self.brain.inbox().text + str(target))
        card = next(p for p in self.brain.review().data["proposals"]
                    if p["id"] == made.data["proposal_id"])
        self.assertIn("An instruction found in file:agency-brief.pdf", " ".join(card["problems"]))

    def test_the_owners_own_rule_and_their_instruction_files_stay_rules(self):
        mine = self.target(self.brain.propose(
            area="marketing", topic="channels", text="Always post to LinkedIn before 9am.",
            note_kind="rule", principal=self.owner, capture_origin="app", force_pending=True))
        self.assertEqual((mine["kind"], mine["said_by"]), ("rule", "owner"))
        moved = self.target(self.brain.propose(
            area="marketing", topic="voice", text="Never use exclamation marks in headlines.",
            note_kind="rule", principal=self.owner, origin="import:instructions",
            force_pending=True))
        self.assertEqual((moved["kind"], moved["said_by"]), ("rule", "owner"))
        self.assertNotIn("instruction_from", moved)

    def test_a_quote_the_person_never_said_makes_the_statement_inferred_and_it_waits(self):
        self.brain.context("Remember that I always send the deck a day early.",
                           session_id=SESSION)
        heard = self.target(self.brain.propose(
            area="marketing", topic="channels", text="Send client decks a day early.",
            principal=self.owner, session_id=SESSION, capture_origin="chat",
            evidence="The person said “I always send the deck a day early”."))
        self.assertNotIn("unheard_quote", heard)
        invented = self.brain.propose(
            area="marketing", topic="channels", text="Send client decks two days early.",
            principal=self.owner, session_id=SESSION, capture_origin="chat",
            evidence="The person said “send every deck two days before the meeting”.")
        target = self.target(invented)
        self.assertEqual(invented.data["status"], "pending")
        self.assertEqual(target["confidence"], "inferred")
        self.assertEqual(target["unheard_quote"], "send every deck two days before the meeting")
        card = next(p for p in self.brain.review().data["proposals"]
                    if p["id"] == invented.data["proposal_id"])
        self.assertIn("is not in what you said in that conversation", " ".join(card["problems"]))


    def test_an_output_cannot_be_evidence_for_the_notes_in_its_own_brief(self):
        """The circular-evidence rule (decision 11): a seeded promotion of what an output only
        repeats from its brief is refused; something new from the same output is not."""
        session = "5f0e7c1a-5555-4c2e-9a37-2f1d1c0e9b10"
        self.brain.context("How should LinkedIn posts be written?", session_id=session)
        given = [item for kind, item, *_ in self.brain.ledger.session_items(session)
                 if kind == "note"]
        self.assertTrue(given)
        echoed = self.brain.state().index.note(given[0])
        deck = os.path.join(os.path.dirname(self.vault), "deck.md")
        with open(deck, "w", encoding="utf-8") as handle:
            handle.write(echoed.body)
        self.brain.record_output(deck, title="A deck", session_id=session)
        refused = self.brain.propose(
            area=echoed.area, topic=echoed.topic, text=echoed.body, principal=self.owner,
            origin=f"output:{deck}", force_pending=True)
        self.assertTrue(refused.is_error)
        self.assertIn("circular-evidence rule", refused.text)
        self.assertIn(echoed.id, refused.text)
        fresh = self.brain.propose(
            area=echoed.area, topic=echoed.topic, principal=self.owner,
            text="The spring webinar drew 212 attendees, the most so far.",
            origin=f"output:{deck}", force_pending=True)
        self.assertFalse(fresh.is_error, fresh.text)

    def test_every_seeded_fabricated_quote_is_caught(self):
        """The gate (7.4): fabricated evidence quotes on a seeded test, all caught."""
        said = ["Remember that our webinars run on Tuesdays at noon Eastern.",
                "I never want prices in a first email, ever.",
                "Keep the newsletter under four hundred words please."]
        invented = ["our webinars run on Thursdays at noon Eastern",
                    "always put the price in the first email",
                    "keep the newsletter over a thousand words",
                    "I prefer long subject lines with emoji",
                    "the budget for October is twelve thousand dollars"]
        for quote in invented:
            self.assertEqual(statements.unheard(f"They said “{quote}”.", said), [quote], quote)
        for message in said:
            quote = " ".join(message.rstrip(".").split()[1:9])
            self.assertEqual(statements.unheard(f"They said “{quote}”.", said), [], quote)


if __name__ == "__main__":
    unittest.main()
