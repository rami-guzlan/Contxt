"""A large Brain is read from disk again at most every few seconds; its own writes and a
small Brain's every change are seen at once."""
from __future__ import annotations

import os
import shutil
import unittest
from unittest import mock

from brainkit import api
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class RecheckTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "personal", "vault"))
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def _walks(self):
        calls = []
        real = self.brain.vault.listing

        def counted():
            calls.append(1)
            return real()
        return calls, counted

    def test_a_small_brain_is_checked_on_every_request(self):
        calls, counted = self._walks()
        with mock.patch.object(self.brain.vault, "listing", counted):
            self.brain.state()
            self.brain.state()
        self.assertEqual(len(calls), 2)

    def test_a_large_brain_reuses_its_last_look_for_a_moment(self):
        calls, counted = self._walks()
        with mock.patch.object(api, "RECHECK_FILES", 1), \
                mock.patch.object(self.brain.vault, "listing", counted):
            self.brain.state()
            self.brain.state()
            self.assertEqual(len(calls), 1)
            se.add_notes(self.vault, [{"id": "outside", "area": "me", "topic": "notes",
                                       "body": "Written by an editor, not the app."}])
            with mock.patch.object(api.time, "monotonic",
                                   return_value=api.time.monotonic() + api.RECHECK_SECONDS + 1):
                # The look happens beside the request, which is served what it had.
                self.assertIsNone(self.brain.state().index.note("outside"))
                self.brain._walker.join(10)
                st = self.brain.state()
            self.assertIsNotNone(st.index.note("outside"))
            self.assertEqual(len(calls), 2)
