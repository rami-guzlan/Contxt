"""Time as knowledge in motion (v4 backend plan, 13.3): `activity(action: "timeline")` lists
what was kept, changed, superseded or disputed in a window, each with when it was true and when
it was recorded, scope-filtered; a new conversation's startup carries one line of what changed
since this app's last one."""
from __future__ import annotations

import unittest

from brainkit import mcp_server, timeline
from brainkit.api import Brain
from tests import fixture


def record(brain, at, action, note, **extra):
    brain.vault.append_decision({"at": at, "action": action, "note": note, "by": "person:alex",
                                 **extra})


class TimelineTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        record(self.brain, "2026-10-01T10:00:00Z", "approved", "facts-services-002")
        record(self.brain, "2026-10-05T10:00:00Z", "edited", "rules-style-001")
        record(self.brain, "2026-10-08T10:00:00Z", "approved", "rules-style-002",
               superseded=["rules-style-003"])
        record(self.brain, "2026-10-09T10:00:00Z", "marked", "facts-services-001",
               state="disputed")
        record(self.brain, "2026-10-10T10:00:00Z", "approved", "facts-clients-acme-001")

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def rows(self, **kw):
        found = self.brain.timeline(**kw)
        self.assertFalse(found.is_error, found.text)
        return [(r["what"], r["id"]) for r in found.data["entries"]]

    def test_what_moved_in_a_window_newest_first(self):
        self.assertEqual(self.rows(since="2026-10-02", until="2026-10-09T23:59:59Z"), [
            ("disputed", "facts-services-001"), ("kept", "rules-style-002"),
            ("superseded", "rules-style-003"), ("changed", "rules-style-001")])

    def test_each_entry_carries_when_it_was_true_and_when_it_was_recorded(self):
        found = self.brain.timeline(since="2026-10-01").data["entries"]
        kept = next(r for r in found if r["id"] == "facts-services-002")
        self.assertEqual(kept["recorded"], "2026-10-01T10:00:00Z")
        self.assertIn("true_from", kept)

    def test_a_sealed_entry_is_left_out(self):
        self.assertNotIn("facts-clients-acme-001", {i for _, i in self.rows()})

    def test_by_area_and_paged(self):
        self.assertEqual({i for _, i in self.rows(area="rules")},
                         {"rules-style-001", "rules-style-002", "rules-style-003"})
        first = self.brain.timeline(limit=2).data
        self.assertEqual(len(first["entries"]), 2)
        self.assertTrue(first["more"])

    def test_agents_read_it_as_activity_timeline(self):
        server = mcp_server.Server(self.brain)
        found = server.call("activity", {"action": "timeline", "since": "2026-10-02"})
        self.assertFalse(found.is_error, found.text)
        self.assertIn("superseded", found.text)

    def test_the_since_line_counts_what_moved(self):
        line = timeline.since_line(self.brain, self.brain.state(), ["company", "person:alex"],
                                   (), "2026-10-02T00:00:00Z")
        self.assertTrue(line.startswith("Since Oct 2:"), line)
        self.assertIn("1 kept", line)
        self.assertIn("1 superseded", line)
        self.assertIn("1 disputed", line)

    def test_a_new_conversation_of_the_same_app_gets_the_since_line(self):
        self.brain.client = "Claude Code 2.0"
        first = self.brain.context("How long do web projects take?")
        self.assertNotIn("changed since your last conversation", first.text.lower())
        record(self.brain, "2099-01-01T00:00:00Z", "edited", "rules-style-001")
        later = self.brain.context("Headline rules?")
        self.assertIn("changed since your last conversation", later.text.lower())


if __name__ == "__main__":
    unittest.main()
