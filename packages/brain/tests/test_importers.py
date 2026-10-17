"""Scout, intake and the brain-kit migration, all on throwaway trees."""
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import governance, importers  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from tests import fixture  # noqa: E402


def _docx(path, paragraphs):
    body = "".join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.'
           'openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body
           + '</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


class ScoutTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build(files_wait=True)
        self.brain = Brain(self.vault, embeddings=False)
        self.src = tempfile.mkdtemp(prefix="scout-src-")
        with open(os.path.join(self.src, "notes.md"), "w", encoding="utf-8") as handle:
            handle.write("# Studio notes\n\nOur motion design team delivers explainer videos "
                         "in three weeks, including two rounds of revisions.\n\nNorthwind "
                         "offers brand identity, web design and motion design for small "
                         "companies.\n")
        _docx(os.path.join(self.src, "pricing.docx"),
              ["Pricing", "Brand identity packages start at a fixed fee and include two "
               "concept directions plus a final guidelines document."])
        with open(os.path.join(self.src, ".env"), "w") as handle:
            handle.write("SECRET=1")
        with open(os.path.join(self.src, "secret.txt"), "w", encoding="utf-8") as handle:
            handle.write("HIGHLY CONFIDENTIAL. Do not ingest. The acquisition closes in March "
                         "and nobody outside the board may know about it yet.")

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)
        shutil.rmtree(self.src, ignore_errors=True)

    def test_dry_run_finds_only_new_allowed_claims(self):
        res = importers.scout(self.brain, self.src, dry_run=True)
        texts = [f["text"] for f in res.data["findings"]]
        self.assertTrue(any("explainer videos" in t for t in texts), texts)
        self.assertTrue(any("concept directions" in t for t in texts), texts)
        self.assertFalse(any("acquisition" in t for t in texts))
        self.assertFalse(any("small companies" in t for t in texts))
        self.assertEqual(res.data["skipped"]["sensitive"], 1)
        self.assertEqual(self.brain.inbox().data["proposals"], [])

    def test_scout_files_pending_proposals_even_in_own_scope(self):
        res = importers.scout(self.brain, self.src, scope="person:alex")
        self.assertFalse(res.is_error, res.text)
        pending = self.brain.inbox().data["proposals"]
        self.assertGreaterEqual(len(pending), 2)
        self.assertTrue(all(p["target"].get("source", "").startswith("scout:") for p in pending))

    def test_what_scout_finds_is_a_documents_word_and_its_instructions_are_reported(self):
        with open(os.path.join(self.src, "agency.md"), "w", encoding="utf-8") as handle:
            handle.write("# Agency brief\n\nAlways post the client's launch video on a Tuesday "
                         "morning, never on a Friday afternoon.\n")
        res = importers.scout(self.brain, self.src, scope="person:alex")
        self.assertFalse(res.is_error, res.text)
        proposals = self.brain.inbox().data["proposals"]
        pending = [p["target"] for p in proposals]
        self.assertTrue(pending)
        self.assertTrue(all(t.get("said_by") == "document" for t in pending), pending)
        self.assertTrue(all(str(t.get("origin", "")).startswith("file:") for t in pending))
        brief = next(p for p in proposals if "launch video" in p["body"])
        self.assertTrue(brief["body"].startswith("The document says: Always post"))
        self.assertEqual(brief["target"]["layer"], "facts")  # this older vault files by layer
        self.assertEqual(brief["target"]["instruction_from"], "file:agency.md")

    def test_gates(self):
        self.assertTrue(importers.scout(self.brain, os.path.abspath(os.sep)).is_error)
        self.assertTrue(importers.scout(self.brain, os.path.join(self.src, "missing")).is_error)

    def test_intake_stages_a_reference_until_it_is_approved(self):
        res = importers.intake(self.brain, os.path.join(self.src, "pricing.docx"),
                               title="Pricing Sheet", topic="facts/services")
        self.assertFalse(res.is_error, res.text)
        ref = res.data["reference"]
        self.assertFalse(os.path.exists(os.path.join(self.vault, ref)))
        pending = self.brain.inbox().data["proposals"]
        self.assertEqual([p["kind"] for p in pending], ["file.add"])
        self.assertIn(ref, pending[0]["body"])
        approved = governance.approve(self.brain, pending[0]["id"])
        self.assertFalse(approved.is_error, approved.text)
        self.assertIn(ref, self.brain.state().index.references)


if __name__ == "__main__":
    unittest.main()
