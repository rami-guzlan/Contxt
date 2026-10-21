"""A request about one project gets that project's packet and never another project's notes
(Release 1 plan: project scope, M01 and M11)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import focus
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def _project(brain, name, objective, pins=()):
    made = focus.create_focus(brain, name, objective, objective=objective,
                              pinned_notes=list(pins))
    assert not made.is_error, made.text
    return made.data["id"]


class ProjectScopeTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        brain = se.open_brain(self.vault)
        try:
            bakery = _project(brain, "Bakery site", "Launch the bakery ordering site.",
                              pins=["bakery-tax"])
            podcast = _project(brain, "Podcast season", "Release ten podcast episodes.")
            st = brain.state()
            where = {f.id: (f.note.area, f.note.topic) for f in st.index.focuses.values()}
        finally:
            brain.close()
        note = lambda i, fid, body: {"id": i, "area": where[fid][0],  # noqa: E731
                                     "topic": where[fid][1], "kind": "fact", "title": i,
                                     "summary": body, "project_id": fid, "body": body}
        se.add_notes(self.vault, [
            note("bakery-budget", bakery, "The bakery site budget is $6,500."),
            note("bakery-tax", bakery, "Every bakery page shows prices including tax."),
            note("podcast-photo-budget", podcast,
                 "The photography budget for studio photos is $1,800 of the $9,000 budget."),
        ])
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def sent(self, request):
        data = self.brain.context(request, record=False, include_kernel=False).data
        return (set(data.get("note_ids") or []) | set(data.get("pointer_ids") or [])
                | set(data.get("related_ids") or []) | set(data.get("unfit_ids") or []))

    def test_a_named_project_never_brings_another_projects_notes(self):
        sent = self.sent("Write the photography budget line for the Bakery site launch plan.")
        self.assertNotIn("podcast-photo-budget", sent)

    def test_another_projects_note_is_still_found_when_no_project_is_named(self):
        self.assertIn("podcast-photo-budget",
                      self.sent("What is the photography budget for studio photos?"))

    def test_a_status_question_brings_the_projects_pins(self):
        self.assertIn("bakery-tax", self.sent("Where does the Bakery site stand?"))


if __name__ == "__main__":
    unittest.main()
