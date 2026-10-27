"""The packet is filled with the request's next best notes (v4 backend plan, 17.1): the model
seldom opens a pointer, so they go whole, after routing, in a standard or project packet only;
never a must-hold, a note loaded manual or a lesson, and they bring no must-hold of their own.
Run on scratch copies of a generated Brain, zero-config and words only."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import evalkit
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
DENTAL = os.path.join(HERE, "evals", "general", "dental", "vault")
REQUEST = "Draft the reminder text for patients overdue for their cleaning"


class FillTest(unittest.TestCase):
    def brain(self, fill):
        vault = se.copy_vault(DENTAL)
        self.addCleanup(shutil.rmtree, os.path.dirname(vault), True)
        evalkit.zero_config(vault)
        with open(os.path.join(vault, "routing.json"), "w", encoding="utf-8") as handle:
            json.dump({"policy": {"fill": fill}}, handle)
        brain = se.open_brain(vault)
        self.addCleanup(brain.close)
        return brain

    def test_the_next_best_notes_go_in_whole(self):
        off = self.brain(0).context(REQUEST, record=False).data
        on = self.brain(4).context(REQUEST, record=False).data
        added = set(on["note_ids"]) - set(off["note_ids"])
        self.assertTrue(added)
        self.assertFalse(added & set(on.get("pointer_ids") or []))  # whole, not in short
        self.assertEqual(off["must_hold_ids"], on["must_hold_ids"])  # no must-hold of its own

    def test_never_a_must_hold_a_manual_note_or_a_lesson(self):
        brain = self.brain(8)
        st = brain.state()
        kept_out = {n.id for n in st.index.notes.values()
                    if n.must_hold or n.load == "manual" or n.kind == "lesson"}
        for request in (REQUEST, "What does a filling cost?", "Plan next week's schedule"):
            route = st.router.route(request, *brain.caller(None, None, None, st=st))
            filled = {s.item.id for s in route.notes if any("filling the packet" in r
                                                          for r in s.reasons)}
            self.assertFalse(filled & kept_out)

    def test_a_lean_packet_is_not_filled(self):
        data = self.brain(8).context("What's the capital of Mongolia?", record=False).data
        self.assertEqual(data["mode"], "lean")
        self.assertEqual(data["note_ids"], [])


if __name__ == "__main__":
    unittest.main()
