"""Meaning, not words: file sections reach questions asked in a person's own words.

These tests use the real local embedding model, so they run only where one is on disk: set
BRAIN_TEST_MODELS to a brain's model folder (vault/.brain/models) holding bge-small-en-v1.5.
Without it they are skipped (CI has no model), and the word-based fallback is covered by
test_files.py.
"""
import os
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit.api import Brain  # noqa: E402
from tests import test_layout  # noqa: E402
from tests.test_files import PROPOSAL_V2  # noqa: E402

MODELS = os.environ.get("BRAIN_TEST_MODELS", "")
SMALL = "models--qdrant--bge-small-en-v1.5-onnx-q"


def _have_model() -> bool:
    if not MODELS or not os.path.isdir(os.path.join(MODELS, SMALL)):
        return False
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(_have_model(), "needs BRAIN_TEST_MODELS with bge-small-en-v1.5")
class MeaningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = test_layout.build()
        target = os.path.join(cls.vault, ".brain", "models", SMALL)
        shutil.copytree(os.path.join(MODELS, SMALL), target)
        cls.brain = Brain(cls.vault, embeddings=True, local_models=True)
        made = cls.brain.focus_create("Spring launch proposals",
                                      "Proposals for the spring launch campaign.",
                                      principal="person:ana")
        cls.path = cls.brain.add_file(content=PROPOSAL_V2, filename="Spring proposal.md",
                                      project=made.data["id"], principal="person:ana",
                                      origin="app").data["path"]

    @classmethod
    def tearDownClass(cls):
        cls.brain.close()
        shutil.rmtree(os.path.dirname(cls.vault), ignore_errors=True)

    def sections(self, request):
        res = self.brain.context(request, principal="person:ana", record=False)
        return [i.rsplit("#", 1)[1] for i in res.data["section_ids"]]

    def test_the_model_is_used(self):
        self.assertTrue(self.brain.state().index.semantic_ready())

    def test_questions_in_other_words_reach_the_part_that_answers_them(self):
        # The proposal says "Podcast sponsorship ... Budget: 900 dollars" and "March: film".
        self.assertIn("3", self.sections("How much money is going to the podcast?"))
        self.assertIn("4", self.sections("When are we shooting the videos?"))

    def test_an_unrelated_question_gets_nothing_from_the_file(self):
        self.assertEqual(self.sections("What's the capital of Portugal?"), [])


# A planning call as transcripts arrive: small talk, timestamps, no headings. Invented.
CALL = (
    "Machine-generated transcript of a planning call, pasted as provided.\n\n"
    "[00:00] Hi, can you hear me? Yes. How was your weekend? Oh it was lovely, we finally had "
    "some sun, we took the kids to the coast on Sunday. [00:09] Nice, it rained the whole "
    "weekend here, typical. Anyway, I have a hard stop at eleven so let's get going. [00:15] "
    "Okay so the main thing on my list is the polls, I wanted to be a bit more intentional this "
    "season and run a poll every other Tuesday on Instagram, what bread people want to see "
    "next, and then at the end of the season we write it up as a little report for the cafes. "
    "[00:34] Yeah I like that, do we have enough Tuesdays though? [00:38] I think six or seven, "
    "that's enough to say something. [00:42] Okay. And the tasting day, are we still doing the "
    "Saturday one? If it rains we move it inside. [00:47] Yes, the Saturday tasting stays, Ana "
    "wants it before the end of April, so I'll book the back room. [00:55] Great. I'll come up "
    "with the angle for the polls, maybe tomorrow or the day after, probably Thursday actually, "
    "and then you tell me how it fits with your schedule and we can alternate weeks if that's "
    "easier. [01:09] Sure, either we run parallel polls or we repost the same ones, whatever "
    "works. [01:15] Fine. Last thing, the wholesale list, I've got two cafes interested, the one "
    "by the station and the bookshop cafe, I'll send them the price sheet on Monday. [01:26] "
    "Perfect, thanks, enjoy the sunshine while it lasts, talk soon.\n")


@unittest.skipUnless(_have_model(), "needs BRAIN_TEST_MODELS with bge-small-en-v1.5")
class GateTests(unittest.TestCase):
    """A part that merely sounds like the request stays out: an everyday request nothing else
    in the brain is about, and a writing task the file is not the material for."""

    @classmethod
    def setUpClass(cls):
        cls.vault = test_layout.build()
        target = os.path.join(cls.vault, ".brain", "models", SMALL)
        shutil.copytree(os.path.join(MODELS, SMALL), target)
        cls.brain = Brain(cls.vault, embeddings=True, local_models=True)
        made = cls.brain.focus_create("Spring launch proposals",
                                      "Proposals for the spring launch campaign.",
                                      principal="person:ana")
        cls.proposal = cls.brain.add_file(content=PROPOSAL_V2, filename="Spring proposal.md",
                                          project=made.data["id"], principal="person:ana",
                                          origin="app").data["path"]
        cls.call = cls.brain.add_file(content=CALL, filename="Planning call 2026-03-02.md",
                                      project=made.data["id"], principal="person:ana",
                                      origin="app").data["path"]

    @classmethod
    def tearDownClass(cls):
        cls.brain.close()
        shutil.rmtree(os.path.dirname(cls.vault), ignore_errors=True)

    def ctx(self, request):
        return self.brain.context(request, principal="person:ana", record=False)

    def card(self, path):
        return self.brain.state().index.cards[path].id

    def test_an_everyday_request_does_not_quote_a_meeting_that_sounds_like_it(self):
        # "Maybe tomorrow or the day after", the rain and the sun sound like tomorrow's
        # forecast (meaning 0.62); nothing else in the brain is about the weather.
        res = self.ctx("Tell me the weather forecast for tomorrow.")
        self.assertEqual(res.data["mode"], "lean")
        self.assertEqual(res.data["section_ids"], [])
        self.assertEqual(res.data["note_ids"], [])

    def test_a_question_about_the_meeting_quotes_it_when_it_names_it(self):
        named = self.ctx("What did we decide about the polls in the planning call?")
        self.assertEqual(named.data["section_ids"], [f"{self.call}#1"])
        # Unnamed, with no note about polls, the call matches no better than the forecast
        # did: it is listed for the AI to open, not quoted.
        unnamed = self.ctx("What did we decide about the polls?")
        self.assertEqual(unnamed.data["section_ids"], [])
        self.assertIn(self.card(self.call), unnamed.data["related_ids"])

    def test_a_writing_task_quotes_only_the_files_it_names(self):
        loose = self.ctx("Write a LinkedIn post about our bakers at work")
        self.assertEqual(loose.data["section_ids"], [])
        self.assertIn(self.card(self.proposal),
                      loose.data["note_ids"] + loose.data["related_ids"])
        named = self.ctx("Write a LinkedIn post for the spring launch about our bakers at work")
        self.assertEqual(named.data["section_ids"], [f"{self.proposal}#2"])


if __name__ == "__main__":
    unittest.main()
