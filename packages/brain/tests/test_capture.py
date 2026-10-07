"""Capture detection: noticing durable context in what a person says, without guessing.

Detection only ever produces a NUDGE (a line in the packet, or hook context for the agent).
The agent decides whether to propose, and governance decides what becomes live, so the
detector favours precision: a missed cue costs one reminder, a false one costs noise.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import capture

DURABLE = [
    ("From now on, always put the event date in the first line of event posts.", "rule"),
    ("Going forward, Dana Lee is the proposal contact for enterprise accounts.", "rule"),
    ("Never use the word synergy in our copy.", "rule"),
    ("We should always add alt text to carousel images.", "rule"),
    ("Actually, we don't call them webinars, we call them sessions.", "correction"),
    ("That's outdated: the assessment is no longer our paid CTA.", "correction"),
    ("Please don't add hashtags to newsletter posts anymore.", "correction"),
    ("I prefer bullet summaries over long paragraphs.", "preference"),
    ("I'd rather you draft in plain text first.", "preference"),
    ("FYI Lena decided that every client proposal needs a one-page executive summary.",
     "decision"),
    ("The client approved the new module outline.", "decision"),
    ("Remember that Jordan is on leave until October 20.", "memory"),
    ("For future reference, the webinar platform is Zoom Events.", "memory"),
    ("Our new price for the half-day workshop is $4,500.", "fact"),
    ("We're no longer using Supabase for anything.", "fact"),
    ("Here's how we onboard a new freelance partner: intro call, bio, headshot, podcast.",
     "procedure"),
    ("Our process for a new webinar is: book the speaker, build the page, promote for three "
     "weeks.", "procedure"),
    ("Here's our updated brand guide, keep it for future reference.", "reference"),
    ("I've attached our new style guide.", "reference"),
    # Phrasings from a real chat (2026-09-28) that the first version missed.
    ("Attached is the pdf explaining the vision.", "reference"),
    ("This ai-brain is going to be the basis to a full ai workspace app.", "decision"),
    ("It's important this all works at a production level.", "rule"),
    ("Our plan is to launch the community in November.", "decision"),
]

ONE_OFF = [
    "Write a LinkedIn post about AI leadership.",
    "What is the capital of France?",
    "Make the second sentence more direct.",
    "Can I publish this now?",
    "Draft the next Acme proposal section.",
    "Summarize the attached article.",
    "Never mind, let's move on.",
    "Tighten it and cut the hashtags.",
    "Don't use bullet points in this post.",
    "Which UTM values do I use for a LinkedIn ad link?",
    "Did Lena approve the outline?",
    "Should we always use UTMs?",
    "How do I keep my LinkedIn post from sounding robotic?",
    "Tell me about Taylor Brooks.",
    "It's important to mention the date in this post.",
    "What is the plan for next week?",
    "Please find the attached draft and tighten it.",
    "",
]


class DetectionTests(unittest.TestCase):
    def test_durable_statements_are_noticed_with_their_kind(self):
        for text, kind in DURABLE:
            with self.subTest(text=text):
                found = capture.detect(text)
                self.assertTrue(found, f"missed: {text}")
                self.assertEqual(found[0].kind, kind, f"{text} -> {found[0]}")
                self.assertTrue(found[0].sentence)
                self.assertTrue(found[0].cue)

    def test_one_off_requests_are_left_alone(self):
        for text in ONE_OFF:
            with self.subTest(text=text):
                self.assertEqual(capture.detect(text), [], f"false alarm: {text!r}")

    def test_only_the_durable_sentence_is_quoted(self):
        text = ("Write a short post announcing the October 14 webinar. From now on, always "
                "put the event date in the first line of event posts.")
        found = capture.detect(text)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].sentence.startswith("From now on"))
        self.assertNotIn("October 14", found[0].sentence)

    def test_limit_and_one_candidate_per_sentence(self):
        text = " ".join(t for t, _kind in DURABLE)
        self.assertEqual(len(capture.detect(text, limit=3)), 3)
        self.assertEqual(len(capture.detect("I prefer X. I prefer X.")), 1)

    def test_long_sentences_are_clipped(self):
        text = "From now on, " + "always check the numbers twice " * 40 + "."
        self.assertLessEqual(len(capture.detect(text)[0].sentence), 301)


class NudgeTests(unittest.TestCase):
    def test_nudge_quotes_candidates_and_names_the_tools(self):
        text = capture.nudge(capture.detect("I prefer bullet summaries over long paragraphs."))
        self.assertIn("I prefer bullet summaries", text)
        self.assertIn("propose_note", text)
        self.assertIn("do not ask first", text.lower())

    def test_no_candidates_no_nudge(self):
        self.assertEqual(capture.nudge([]), "")

    def test_nudge_routes_each_kind_to_the_right_tool(self):
        procedure = capture.nudge(capture.detect(DURABLE[15][0]))
        self.assertIn("propose_skill", procedure)
        reference = capture.nudge(capture.detect(DURABLE[17][0]))
        self.assertIn("add_file", reference)



class PromptHookTests(unittest.TestCase):
    def test_the_hook_asks_for_context_on_requests_but_not_small_talk(self):
        from brainkit.hooks import capture_prompt
        self.assertTrue(capture_prompt._asks_for_something("Also add a call to action"))
        self.assertFalse(capture_prompt._asks_for_something("thanks!"))
        self.assertFalse(capture_prompt._asks_for_something("ok"))

if __name__ == "__main__":
    unittest.main()
