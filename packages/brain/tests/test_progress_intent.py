"""Questions about project facts must not be mistaken for reports of new progress."""

import unittest
from brainkit.config import RoutingConfig
from brainkit.router import analyze


class ProgressIntentTests(unittest.TestCase):
    def test_reading_or_drafting_about_progress_is_not_reporting_progress(self):
        for request in (
            "What budget is approved for the workshop?",
            "Which proposal has been approved?",
            "When was the invoice sent?",
            "Remind me what we sent to the client.",
            "Please explain what has been approved.",
            "Could you tell me what was sent?",
            "Show me the brief that is approved.",
            "Give me a copy of the proposal that was sent.",
            "Draft an email about the proposal that is approved.",
            "Has the client signed off?",
            "Plan an email about the proposal that is approved.",
            "Could you draft an email about the proposal that is approved",
        ):
            with self.subTest(request=request):
                self.assertFalse(analyze(request, RoutingConfig()).focus_update)

    def test_reports_and_explicit_requests_to_record_progress_still_work(self):
        for request in (
            "The client approved the proposal.",
            "The proposal is approved.",
            "The email was sent.",
            "The report is complete.",
            "We just finished the draft proposal.",
            "The prototype is approved; record that.",
            "We just finished the workshop.",
            "Can we record that the prototype is approved?",
            "Could you record an update: the prototype is approved?",
        ):
            with self.subTest(request=request):
                self.assertTrue(analyze(request, RoutingConfig()).focus_update)
