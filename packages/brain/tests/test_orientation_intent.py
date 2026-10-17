"""A task about onboarding is not necessarily a request for a Brain overview."""
import unittest

from brainkit.config import RoutingConfig
from brainkit.router import analyze


class OrientationIntentTest(unittest.TestCase):
    def test_concrete_tasks_do_not_become_a_general_orientation(self):
        requests = (
            "Draft a welcome email explaining the first week to a new client.",
            "A teammate starts tomorrow. What should her first week look like?",
            "Compare the first day of sales with the first week of sales.",
            "I'm new here. Create a proposal for our design service.",
            "What should I know before replacing a laptop battery?",
        )
        for request in requests:
            with self.subTest(request=request):
                self.assertFalse(analyze(request, RoutingConfig()).orientation)

    def test_explicit_general_orientation_is_preserved(self):
        requests = (
            "I'm new here. What do I need to know before I write anything?",
            "It's my first day. What should I know here?",
            "Give me a tour of what you know.",
            "What should I know about the team?",
            "Onboard me.",
        )
        for request in requests:
            with self.subTest(request=request):
                self.assertTrue(analyze(request, RoutingConfig()).orientation)
