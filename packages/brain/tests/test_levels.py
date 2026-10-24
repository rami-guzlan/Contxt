"""Levels on every entry: each packet item carries its level in braces, and the inventory
gives it to the app (v4 spec, section 6)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import inventory, levels
from brainkit import safeguards_eval as se
from brainkit.model import Note

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def note(load="on-demand", **meta):
    return Note(id="n", area="work", topic="general", scope="company", status="approved",
                load=load, body="Text.", path="knowledge/work/general/n.md", meta=meta)


class LevelsTest(unittest.TestCase):
    def test_a_note_is_canon_confirmed_kept_or_tentative_from_what_it_records(self):
        self.assertEqual(levels.of(note(load="domain")), "canon")
        self.assertEqual(levels.of(note(baseline=True)), "canon")
        self.assertEqual(levels.of(note(verified="2026-10-01")), "confirmed")
        self.assertEqual(levels.of(note(statement_status="tentative")), "tentative")
        self.assertEqual(levels.of(note()), "kept")
        self.assertEqual(levels.tag(note()), "{kept, not verified}")

    def test_every_packet_item_carries_its_level_in_braces(self):
        vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        try:
            se.add_notes(vault, [
                {"id": "invoice-days", "area": "work", "topic": "money", "kind": "fact",
                 "title": "Invoice days", "verified": "2026-10-01",
                 "body": "Invoices go out on the 1st and the 15th."},
                {"id": "sign-off", "area": "work", "topic": "money", "kind": "rule",
                 "load": "domain", "applies_to": ["work"], "triggers": ["invoices"],
                 "must_text": "The owner signs off every invoice",
                 "title": "Sign-off", "body": "The owner signs off every invoice."}])
            brain = se.open_brain(vault)
            try:
                found = brain.context("When do invoices go out?")
                self.assertIn("### Invoice days (new)   {confirmed}", found.text)
                self.assertIn("The owner signs off every invoice (`sign-off`) {canon}.",
                              found.text)
                rows = {r["id"]: r for r in inventory.rows(brain)}
                self.assertEqual(rows["invoice-days"]["level"], "confirmed")
                self.assertEqual(rows["sign-off"]["level_label"], "canon")
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
