"""A task verb in a project description does not name the project."""
import unittest
from unittest import mock

from brainkit.api import Brain
from brainkit import safeguards_eval as se
from tests import fixture


class ProjectCommandIdentity(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.project = self.brain.focus_create(
            "Harbor launch", "Prepare the launch.", principal="person:alex"
        ).data["id"]

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def context(self, request, **kwargs):
        return self.brain.context(request, principal="person:alex", record=False, **kwargs)

    def test_a_description_command_does_not_assign_unrelated_work_to_a_project(self):
        for command in ("Compose", "Rewrite", "Translate", "Design"):
            with self.subTest(command=command):
                se.set_meta(self.vault, [self.project], summary=command + " the launch material.")
                result = self.context(command + " a birthday greeting for my cousin.")
                self.assertIsNone(result.data.get("focus_id"))
                self.assertNotIn(self.project, result.data.get("note_ids", []))

    def test_a_real_project_name_still_assigns_its_work(self):
        se.set_meta(self.vault, [self.project], summary="Rewrite the launch material.")
        result = self.context("Rewrite the opening for Harbor launch.")
        self.assertEqual(result.data.get("focus_id"), self.project)

    def test_an_explicit_action_word_alias_still_names_the_project(self):
        se.set_meta(self.vault, [self.project], aliases=["Compose"])
        result = self.context("What is the status of Compose?")
        self.assertEqual(result.data.get("focus_id"), self.project)

    def test_a_real_entity_in_the_description_remains_discoverable(self):
        se.set_meta(self.vault, [self.project], summary="Glintvale needs the launch material.")
        result = self.context("What is the status of Glintvale?")
        self.assertEqual(result.data.get("focus_id"), self.project)

    def test_work_is_recognized_when_its_subject_matches_beyond_the_command(self):
        se.set_meta(self.vault, [self.project],
                    summary="Rewrite the pricing pages for membership programs.")
        result = self.context("Rewrite the pricing pages for membership options.")
        self.assertEqual(result.data.get("focus_id"), self.project)

    def test_meaning_confirmation_uses_calibrated_evidence_not_only_rank(self):
        from brainkit.calibration import Calibration
        from brainkit.router import Scored, analyze

        se.set_meta(self.vault, [self.project], summary="Rewrite the launch material.")
        state = self.brain.state()
        router = state.router
        focus = state.index.focuses[self.project]
        sig = analyze("Rewrite an unrelated invitation.", state.config.routing)
        router._calibration = Calibration([0.4, 0.5, 0.6], [1, 2, 3])
        for cosine, expected in ((0.5, None), (0.8, focus)):
            with self.subTest(cosine=cosine):
                ranked = [Scored(focus.note, 0.9, detail={"cos_raw": cosine, "bm_raw": 0})]
                with mock.patch.object(router, "calibrated", return_value=True), \
                        mock.patch.object(router, "score_notes", return_value=ranked):
                    found, _reason = router.find_focus(sig, [focus])
                self.assertIs(found, expected)
