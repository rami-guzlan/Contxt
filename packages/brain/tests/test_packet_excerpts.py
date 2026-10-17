"""Only evidence actually delivered is held by a conversation."""
import dataclasses
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import packets
from brainkit.api import Brain
from brainkit.model import Note
from brainkit.router import Policy, Route, Scored, analyze
from brainkit.sections import Section
from tests import fixture


class PacketExcerptTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.addCleanup(fixture.remove, self.vault)
        self.addCleanup(self.brain.close)
        self.state = self.brain.state()
        self.session = "sess-excerpts"
        self.brain.ledger.touch(self.session, "person:alex")
        self.note = Note("maintenance", "facts", "operations", "company", "approved",
                         "on-demand", "The airlock filter interval is 17 days. "
                         "Store coolant in bay seven during shutdown. "
                         + "Routine inspections are entered in the maintenance log. " * 70,
                         "maintenance.md", {"title": "Maintenance", "summary": "Site procedures"})
        self.section = Section("references/procedure.md#1", "references/procedure.md", 1,
                               "Maintenance", self.note.body + "The final release code is orange.")

    def packet(self, query="airlock filter interval", *, note=True, budget=150,
               section_room=160, engine=False, fresh=False):
        chain, partitions = self.brain.caller("person:alex", st=self.state)
        route = Route(query, chain, partitions, analyze(query, self.state.config.routing),
                      policy=dataclasses.replace(Policy(), section_tokens=section_room))
        if note:
            route.notes = [Scored(self.note, .9)]
            if engine:
                route.engine_fit = {self.note.id: "pointer"}
        else:
            route.sections = [Scored(self.section, .9)]
        with mock.patch("brainkit.packets.note_budget", return_value=budget):
            result = packets.build(route, config=self.state.config, index=self.state.index,
                                   delivered=self.brain.ledger.delivered(self.session),
                                   fresh=fresh, session_id=self.session)
        self.brain.ledger.record(self.session, result.id, query, route.mode, result.text,
                                 result.data, result.items)
        return result

    def test_a_different_sentence_of_the_same_note_is_delivered(self):
        first = self.packet()
        self.assertIn("17 days", first.text)
        self.assertNotIn("bay seven", first.text)
        second = self.packet("coolant storage during shutdown")
        self.assertIn("bay seven", second.text)
        self.assertEqual(second.data["held_ids"], [])
        self.assertEqual(second.data["note_ids"], [self.note.id])

    def test_an_identical_excerpt_is_held(self):
        self.packet()
        again = self.packet()
        self.assertEqual(again.data["held_ids"], [self.note.id])
        self.assertEqual(again.data["note_ids"], [])
        self.assertIn("(excerpt only)", again.text)

    def test_an_earlier_excerpt_stays_held_after_another_excerpt(self):
        self.packet()
        self.assertIn("bay seven", self.packet("coolant storage during shutdown").text)
        again = self.packet()
        self.assertEqual(again.data["held_ids"], [self.note.id])
        self.assertNotIn("17 days", again.text)

    def test_an_excerpt_can_upgrade_to_a_full_note_then_stays_held(self):
        self.packet()
        whole = self.packet(budget=5000)
        self.assertIn("bay seven", whole.text)
        self.assertEqual(whole.data["note_ids"], [self.note.id])
        self.assertEqual(self.packet().data["held_ids"], [self.note.id])

    def test_legacy_pointer_history_refreshes_once(self):
        self.brain.ledger.record_items(self.session, "legacy", [
            ("note", self.note.id, "pointer:" + self.note.body_hash, 40)])
        self.assertIn("17 days", self.packet().text)
        self.assertEqual(self.packet().data["held_ids"], [self.note.id])

    def test_engine_pointer_metadata_changes_are_delivered(self):
        self.packet(engine=True)
        self.assertEqual(self.packet(engine=True).data["held_ids"], [self.note.id])
        self.note.meta["summary"] = "Updated maintenance overview"
        self.assertIn("Updated maintenance overview", self.packet(engine=True).text)

    def test_a_clipped_section_can_upgrade_to_the_full_section(self):
        first = self.packet(note=False)
        self.assertIn("Cut short here", first.text)
        self.assertNotIn("release code is orange", first.text)
        whole = self.packet(note=False, section_room=5000)
        self.assertIn("release code is orange", whole.text)
        self.assertNotIn("Cut short here", whole.text)
        self.assertEqual(whole.data["held_section_ids"], [])
        self.assertEqual(self.packet(note=False).data["held_section_ids"], [self.section.id])

    def test_the_same_clipped_section_is_held(self):
        self.packet(note=False)
        again = self.packet(note=False)
        self.assertEqual(again.data["section_ids"], [])
        self.assertEqual(again.data["held_section_ids"], [self.section.id])
        self.assertIn("(excerpt only)", again.text)

    def test_a_larger_clipped_view_is_delivered_and_earlier_view_stays_held(self):
        first = self.packet(note=False)
        larger = self.packet(note=False, section_room=350)
        self.assertIn("Cut short here", larger.text)
        self.assertGreater(len(larger.text), len(first.text))
        self.assertEqual(self.packet(note=False).data["held_section_ids"], [self.section.id])

    def test_legacy_section_history_does_not_claim_unseen_text(self):
        self.brain.ledger.record_items(self.session, "legacy", [
            ("section", self.section.id, self.section.body_hash, 100)])
        self.assertIn("release code is orange", self.packet(note=False, section_room=5000).text)
        self.assertEqual(self.packet(note=False).data["held_section_ids"], [self.section.id])

    def test_fresh_and_refreshed_sessions_resend_excerpts(self):
        self.packet()
        self.assertIn("17 days", self.packet(fresh=True).text)
        self.brain.ledger.refresh(self.session)
        self.assertIn("17 days", self.packet().text)

    def test_a_changed_source_and_a_reversion_are_delivered(self):
        original = self.note.body
        self.packet()
        self.note.body = original.replace("17 days", "21 days")
        self.assertIn("21 days", self.packet().text)
        self.note.body = original
        self.assertIn("17 days", self.packet().text)

    def test_sections_refresh_after_source_changes_and_session_reset(self):
        original = self.section
        self.packet(note=False, section_room=5000)
        self.section = dataclasses.replace(original, text=original.text.replace("orange", "blue"))
        self.assertIn("release code is blue", self.packet(note=False, section_room=5000).text)
        self.section = original
        self.assertIn("release code is orange", self.packet(note=False, section_room=5000).text)
        self.brain.ledger.refresh(self.session)
        self.assertIn("release code is orange", self.packet(note=False, section_room=5000).text)

    def test_another_conversation_does_not_inherit_excerpts(self):
        self.packet()
        self.session = "sess-other-excerpts"
        self.brain.ledger.touch(self.session, "person:alex")
        self.assertIn("17 days", self.packet().text)

    def test_equal_timestamps_preserve_delivery_order(self):
        from brainkit import util
        with mock.patch.object(util, "now_iso", return_value="2026-10-17T12:00:00Z"):
            self.packet()
            self.assertIn("bay seven", self.packet("coolant storage during shutdown").text)
            self.assertEqual(self.packet().data["held_ids"], [self.note.id])
