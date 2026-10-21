"""A distilled piece goes to its own home: a sheet cell, a project's progress, a task, a
project's kept item or a long-term note. Every one waits in the one inbox, with its source,
and the owner can move it before keeping it (Release 1 plan, M03)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import destinations, focus, governance, handoff, state
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SOURCE = {"source_id": "context_item:ci_7", "source_locator": "02:10",
          "source_speaker": "Morgan Lee", "source_excerpt": "Dana said yes for the twelfth."}


class DestinationTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        self.brain = se.open_brain(self.vault)
        made = focus.create_focus(self.brain, "Q4 webinars", "Run four webinars this quarter.",
                                  objective="Run four webinars this quarter.")
        self.project = made.data["id"]
        state.create_sheet(self.brain, title="Guests", columns=[
            {"name": "Guest", "type": "text"}, {"name": "Status", "type": "text"}],
            key="Guest")
        state.add_row(self.brain, "guests", "Dana Ruiz", {"Status": "Invited"}, who="person:me")

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def keep(self, made, **kw):
        self.assertFalse(made.is_error, made.text)
        kept = governance.approve(self.brain, made.data["proposal_id"], actor="person:me", **kw)
        self.assertFalse(kept.is_error, kept.text)
        return kept

    def test_a_sheet_value_waits_in_the_inbox_then_updates_the_cell(self):
        made = destinations.propose(self.brain, "sheet", "Dana Ruiz is confirmed.",
                                    sheet="guests", row="Dana Ruiz", column="Status",
                                    value="Confirmed for Nov 12", **SOURCE)
        row = next(r for r in governance.inbox(self.brain).data["proposals"]
                   if r["id"] == made.data["proposal_id"])
        self.assertEqual(row["operation"], "update a sheet value")
        self.assertEqual(row["destination"], "Guests › Dana Ruiz › Status")
        self.assertEqual(row["source"]["speaker"], "Morgan Lee")
        self.assertEqual(state.find_row(self.brain, "guests", "Dana Ruiz").value("Status"),
                         "Invited")
        self.keep(made)
        cell = state.find_row(self.brain, "guests", "Dana Ruiz")
        self.assertEqual(cell.value("Status"), "Confirmed for Nov 12")
        last = state.history(self.brain, "guests", cell.id, "Status")[0]
        self.assertIn("context_item:ci_7", last.get("source", ""))

    def test_progress_goes_to_the_projects_journal(self):
        made = destinations.propose(self.brain, "progress", "Session 2 guest confirmed.",
                                    project="Q4 webinars", next_up="Promote session 2")
        self.keep(made)
        found = self.brain.state().index.focuses[self.project]
        self.assertEqual(found.updates[-1].summary, "Session 2 guest confirmed.")

    def test_a_task_opens_in_the_tasks_sheet(self):
        made = destinations.propose(self.brain, "task", "Priya builds the replay page.",
                                    project="Q4 webinars", due="2026-10-29", **SOURCE)
        self.keep(made)
        titles = [t["task"] for t in handoff.tasks(self.brain)]
        self.assertIn("Priya builds the replay page.", titles)

    def test_a_kept_item_is_a_note_filed_with_the_project(self):
        made = destinations.propose(self.brain, "kept", "Reminders go out 48 hours ahead.",
                                    project="Q4 webinars", group="rules", **SOURCE)
        self.keep(made)
        note = self.brain.state().index.note(made.data["id"])
        self.assertEqual(note.meta.get("project_id"), self.project)
        self.assertEqual(note.kind, "rule")

    def test_the_owner_can_move_a_piece_before_keeping_it(self):
        made = destinations.propose(self.brain, "sheet", "Dana prefers a fireside chat.",
                                    sheet="guests", row="Dana Ruiz", column="Status",
                                    value="Fireside chat", **SOURCE)
        kept = self.keep(made, edits={"destination": "note", "area": "people",
                                      "topic": "guests", "title": "Dana's format"})
        self.assertEqual(state.find_row(self.brain, "guests", "Dana Ruiz").value("Status"),
                         "Invited")
        note = self.brain.state().index.note(kept.data["id"])
        self.assertEqual(note.body.strip(), "Dana prefers a fireside chat.")
        self.assertEqual(note.meta["source_speaker"], "Morgan Lee")

    def test_skipping_a_piece_changes_nothing(self):
        made = destinations.propose(self.brain, "sheet", "Dana is confirmed.", sheet="guests",
                                    row="Dana Ruiz", column="Status", value="Confirmed")
        governance.reject(self.brain, made.data["proposal_id"], "not yet",
                          actor="person:me")
        self.assertEqual(state.find_row(self.brain, "guests", "Dana Ruiz").value("Status"),
                         "Invited")


if __name__ == "__main__":
    unittest.main()
