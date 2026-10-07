"""Moving in: memories and instruction files read into ideas, checked against the brain,
without writing anything."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import movein
from brainkit.api import Brain
from tests import fixture

CHATGPT = """Sure! Here is everything I remember about you:

## About me
- Is a designer at Northwind, a small studio.
- The user's dog is named Pixel.

## How I like work done
- Prefers short answers with the conclusion first.
- Write in plain language with short sentences. No jargon, no hype words.

## Facts
- Web design projects take twelve weeks from kickoff to launch.
- Can be reached at alex@example.com for client questions.

Let me know if you'd like me to forget anything!
"""

CLAUDE_MD = """# Project notes

## Commands

```bash
npm test
```

- Use pnpm, never npm, in this repository.
- The API lives in the server folder and talks to PostgreSQL.

| Key | Value |
| --- | --- |
| a | b |
"""


class SplitTests(unittest.TestCase):
    def test_lines_headings_and_sentences(self):
        ideas = movein.split(CHATGPT)
        texts = [i["text"] for i in ideas]
        self.assertNotIn("Sure! Here is everything I remember about you", " ".join(texts))
        self.assertIn("Prefers short answers with the conclusion first.", texts)
        groups = {i["text"]: i["group"] for i in ideas}
        self.assertEqual(groups["Prefers short answers with the conclusion first."],
                         "How I like work done")
        self.assertFalse(any(t.startswith("Let me know") for t in texts))
        paragraph = movein.split("Alex runs the studio. She hires two freelancers each summer.")
        self.assertEqual(len(paragraph), 2)

    def test_code_and_tables_stay_out(self):
        texts = [i["text"] for i in movein.split(CLAUDE_MD)]
        self.assertEqual(texts, ["Use pnpm, never npm, in this repository.",
                                 "The API lives in the server folder and talks to PostgreSQL."])

    def test_a_note_names_the_person(self):
        self.assertEqual(movein.with_subject("Prefers short answers.", "Alex"),
                         "Alex prefers short answers.")
        self.assertEqual(movein.with_subject("The user's dog is named Pixel.", "Alex"),
                         "Alex's dog is named Pixel.")
        self.assertEqual(movein.with_subject("User is a designer.", "Alex"), "Alex is a designer.")
        self.assertEqual(movein.with_subject("Prefers short answers.", "Me"),
                         "Prefers short answers.")
        self.assertEqual(movein.with_subject("Our studio is in Leeds.", "Alex"),
                         "Our studio is in Leeds.")

    def test_kinds(self):
        self.assertEqual(movein.kind_of("Is a designer.", "About me", "chatgpt"), "identity")
        self.assertEqual(movein.kind_of("Prefers short answers.", "", "chatgpt"), "rule")
        self.assertEqual(movein.kind_of("Use pnpm.", "", "instructions"), "rule")
        self.assertEqual(movein.kind_of("Launch the site in May.", "Projects", "paste"), "state")
        self.assertEqual(movein.kind_of("The API talks to PostgreSQL.", "", "instructions"),
                         "fact")

    def test_private_detail(self):
        self.assertEqual(movein.private_detail("Write to alex@example.com"), "an email address")
        self.assertEqual(movein.private_detail("Call 555-123-4567 after six"), "a phone number")
        self.assertEqual(movein.private_detail("The wifi password is hunter2"),
                         "a password or key")
        self.assertIsNone(movein.private_detail("Prefers short answers."))


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_ideas_are_checked_against_the_brain_and_nothing_is_written(self):
        before = self.brain.state().fingerprint
        result = self.brain.move_in([{"kind": "chatgpt", "text": CHATGPT},
                                     {"kind": "instructions", "text": CLAUDE_MD}], name="Alex")
        self.assertFalse(result.is_error, result.text)
        data = result.data
        by_text = {i["text"]: i for i in data["ideas"]}
        known = by_text["Write in plain language with short sentences. No jargon, no hype words."]
        self.assertEqual((known["status"], known["match"]["id"]), ("known", "rules-style-001"))
        clash = by_text["Web design projects take twelve weeks from kickoff to launch."]
        self.assertEqual((clash["status"], clash["match"]["id"]),
                         ("disagree", "facts-services-002"))
        private = by_text["Can be reached at alex@example.com for client questions."]
        self.assertEqual((private["status"], private["private"]),
                         ("private", "an email address"))
        named = by_text["Alex prefers short answers with the conclusion first."]
        self.assertEqual((named["status"], named["kind"], named["personal"]),
                         ("new", "rule", True))
        self.assertEqual(named["original"], "Prefers short answers with the conclusion first.")
        tool = by_text["Use pnpm, never npm, in this repository."]
        self.assertEqual((tool["kind"], tool["personal"]), ("rule", False))
        stages = data["stages"]
        self.assertEqual(stages["sources"], 2)
        self.assertEqual(stages["ideas"], len(data["ideas"]))
        self.assertEqual(stages["known"], 1)
        self.assertEqual(stages["to_keep"], stages["new"] + stages["disagree"] + stages["private"])
        self.assertEqual(set(data["examples"]), {"split", "known", "disagree", "private", "new"})
        self.assertEqual([s["ideas"] for s in data["sources"]], [6, 2])
        self.assertEqual(self.brain.state().fingerprint, before)
        self.assertFalse(self.brain.state().snapshot.proposals)

    def test_an_idea_already_waiting_is_not_new(self):
        self.brain.propose(layer="facts", topic="services", scope="company",
                           text="Motion retainers renew every quarter.")
        result = self.brain.move_in([{"kind": "paste",
                                      "text": "- Motion retainers renew every quarter."}])
        (idea,) = result.data["ideas"]
        self.assertEqual(idea["status"], "waiting")

    def test_refusals(self):
        self.assertTrue(self.brain.move_in([]).is_error)
        self.assertTrue(self.brain.move_in([{"kind": "paste", "text": "x"}] * 9).is_error)
        too_long = self.brain.move_in([{"kind": "paste", "text": "a " * 100_001}])
        self.assertTrue(too_long.is_error)
        self.assertIn("Capture", too_long.text)


if __name__ == "__main__":
    unittest.main()
