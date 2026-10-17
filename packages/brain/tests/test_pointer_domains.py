"""Search suggestions in a nothing brief do not establish a task domain."""
import unittest
from types import SimpleNamespace
from unittest import mock

from brainkit.model import Note
from brainkit.router import Policy, Route, Router, Scored


class PointerDomainTest(unittest.TestCase):
    def setUp(self):
        self.rule = Note("food-rule", "food", "diet", "company", "approved", "domain",
                         "Use safe ingredients.", "rule.md", {"applies_to": ["food"]})
        self.recipe = Note("recipe", "food", "dinner", "company", "approved", "on-demand",
                           "A supper recipe.", "recipe.md", {})
        self.router = object.__new__(Router)
        self.router.policy = Policy()
        self.router.config = SimpleNamespace(review_days_for=lambda n: 30)
        self.router.admitted_notes = lambda *args: [self.rule, self.recipe]
        self.router.similarity = lambda request: {}
        self.router._close_topics = lambda request: {}

    def route(self, mode, pointer):
        request = "Explain lunar phases"
        route = Route(request=request, chain=["company"], partitions=[],
                      signals=SimpleNamespace(words=["lunar", "phases"], norm="explain lunar phases",
                                              request=request, continuation=False), mode=mode)
        route.related = [Scored(pointer, 0.3)]
        self.router._attach_must_holds(route)
        return route

    def test_a_tentative_pointer_in_a_nothing_brief_does_not_put_its_domain_in_play(self):
        self.assertEqual(self.route("lean", self.recipe).must_holds, [])

    def test_a_qualified_rule_pointer_still_carries_the_rule(self):
        self.assertEqual([m.note.id for m in self.route("standard", self.rule).must_holds],
                         [self.rule.id])

    def test_a_relevant_content_pointer_still_brings_its_domain_constraint(self):
        self.assertEqual([m.note.id for m in self.route("standard", self.recipe).must_holds],
                         [self.rule.id])

    def test_an_independent_domain_match_still_applies_in_a_lean_brief(self):
        with mock.patch.object(self.router, "_close_topics", return_value={"food/diet": 0.8}):
            self.assertEqual([m.note.id for m in self.route("lean", self.recipe).must_holds],
                             [self.rule.id])

