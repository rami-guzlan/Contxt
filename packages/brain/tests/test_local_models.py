"""No Brain fetches a model on its own, its MCP server included: it uses one already in
vault/.brain/models, or matches by words until the owner downloads one (models --download, or
the app's Settings). BRAIN_LOCAL_MODELS=0 lets it fetch on first use."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit.api import Brain
from tests import fixture


class LocalModelsTests(unittest.TestCase):
    """A Brain never fetches a model on its own, its MCP server included: it matches by words
    until the owner downloads one."""

    def setUp(self):
        self.vault = fixture.build()

    def tearDown(self):
        fixture.remove(self.vault)

    def test_a_brain_never_fetches_a_model_on_its_own(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("BRAIN_LOCAL_MODELS", None)
            brain = Brain(self.vault)  # matching by meaning on, the default
        try:
            self.assertTrue(brain.embedder.local_only)
            try:
                import fastembed
            except ImportError:  # without it nothing could load a model anyway
                fastembed = None
            if fastembed is not None:
                with mock.patch.object(fastembed, "TextEmbedding") as model:
                    found = brain.context("How long do web design projects run?")
                model.assert_not_called()  # no model was loaded, so none was fetched
            else:
                found = brain.context("How long do web design projects run?")
            self.assertFalse(found.is_error, found.text)
            status = brain.embedder.status()
            self.assertFalse(status["available"])
            self.assertIn("contxt models --download", status["reason"])
            self.assertFalse(brain.embedder.present())  # nothing landed in the model folder
        finally:
            brain.close()

    def test_the_owner_downloads_on_purpose_or_lets_it_fetch(self):
        with mock.patch.dict(os.environ, {"BRAIN_LOCAL_MODELS": "0"}):
            fetching = Brain(self.vault)
        try:
            self.assertFalse(fetching.embedder.local_only)
        finally:
            fetching.close()
        brain = Brain(self.vault)
        try:
            with mock.patch.object(brain.embedder, "_load", return_value=None) as load:
                brain.embedder.download()  # an explicit download fetches even when local-only
            load.assert_called_once()
            self.assertTrue(brain.embedder.local_only)  # and the Brain stays local-only after
        finally:
            brain.close()


if __name__ == "__main__":
    unittest.main()
