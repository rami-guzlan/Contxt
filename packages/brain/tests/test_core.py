"""Front matter, config, scopes, partitions and vault reading."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import config as config_mod
from brainkit import frontmatter as fm
from brainkit.api import Brain
from brainkit.scopes import Scopes
from tests import fixture


class FrontMatterTests(unittest.TestCase):
    def test_round_trip_every_shape(self):
        text = ("---\nid: a-1\nquoted: \"has: colon\"\nsingle: 'it''s'\nitems:\n  - one\n"
                "  - \"two: 2\"\ninline: [x, \"y z\"]\nfolded: >\n  line one\n  line two\n"
                "literal: |\n  keep\n  lines\n---\nBody text.\n")
        meta, body, errors = fm.parse(text)
        self.assertEqual(errors, [])
        self.assertEqual(meta["quoted"], "has: colon")
        self.assertEqual(meta["single"], "it's")
        self.assertEqual(meta["items"], ["one", "two: 2"])
        self.assertEqual(meta["inline"], ["x", "y z"])
        self.assertEqual(meta["folded"], "line one line two")
        self.assertEqual(meta["literal"], "keep\nlines")
        self.assertEqual(body.strip(), "Body text.")
        again, body2, _ = fm.parse(fm.dump(meta, body))
        self.assertEqual(again, meta)
        self.assertEqual(body2.strip(), "Body text.")

    def test_no_front_matter_and_crlf(self):
        meta, body, errors = fm.parse("just text")
        self.assertEqual((meta, body, errors), ({}, "just text", []))
        meta, body, _ = fm.parse("---\r\nid: x\r\n---\r\nhello\r\n")
        self.assertEqual(meta, {"id": "x"})
        self.assertEqual(body.strip(), "hello")


class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = fixture.build()
        cls.config = config_mod.load(cls.vault)
        cls.scopes = Scopes(cls.config)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'brain'):
            cls.brain.close()
        fixture.remove(cls.vault)

    def test_chain_walks_declared_parents_with_custom_prefix(self):
        self.assertEqual(self.scopes.chain("person:alex"),
                         ["company", "team:design", "person:alex"])
        self.assertEqual(self.scopes.chain("alex"), ["company", "team:design", "person:alex"])
        self.assertEqual(self.scopes.chain("person:sam"), ["company", "person:sam"])
        self.assertIsNone(self.scopes.chain("person:nobody"))
        self.assertEqual(self.scopes.scope_path("team:design"), "teams/design")

    def test_partitions_are_sealed_and_owned(self):
        alex = self.scopes.chain("person:alex")
        sam = self.scopes.chain("person:sam")
        self.assertEqual(self.scopes.partition_chain("client:acme", alex), ["client:acme"])
        self.assertIsNone(self.scopes.partition_chain("client:acme", sam))
        self.assertIsNone(self.scopes.partition_chain("client:nope", alex))
        self.assertTrue(Scopes.admits("person:alex", "client:acme", alex, ["client:acme"]))
        self.assertFalse(Scopes.admits("person:alex", "client:acme", alex, ["client:globex"]))
        self.assertFalse(Scopes.admits("person:alex", "client:acme", alex, []))


class VaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = fixture.build()
        cls.brain = Brain(cls.vault, embeddings=False)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'brain'):
            cls.brain.close()
        fixture.remove(cls.vault)

    def test_scan_reads_notes_skills_references_and_journal(self):
        st = self.brain.state()
        self.assertEqual(st.snapshot.problems, [])
        self.assertIn("facts-services-001", st.index.notes)
        self.assertIn("facts-services-000", st.index.archived)
        self.assertNotIn("facts-services-000", st.index.notes)
        self.assertIn("brand-sheet", st.index.skills)
        self.assertEqual(st.index.skills["brand-sheet"].category, "design")
        self.assertIn("references/style-guide.md", st.index.references)
        focus = st.index.focuses["state-focus-website-redesign"]
        self.assertEqual(focus.current()["current"], "Prototype approved; building pages")
        self.assertEqual(focus.title, "Website Redesign")

    def test_health_is_clean_on_the_fixture(self):
        report = self.brain.health()
        self.assertEqual(report.data["problems"], [], report.text)


class ByteOrderMarkTests(unittest.TestCase):
    """Files saved by some Windows editors start with a UTF-8 byte order mark."""

    def setUp(self):
        self.vault = fixture.build()
        bom = "﻿"
        with open(os.path.join(self.vault, "references", "handbook.md"), "w",
                  encoding="utf-8") as handle:
            handle.write(bom + "# Studio handbook\n\n## Pre-flight\n\nCheck the grid.\n")
        folder = os.path.join(self.vault, "knowledge", "facts", "services")
        with open(os.path.join(folder, "facts-services-bom.md"), "w", encoding="utf-8") as handle:
            handle.write(bom + "---\nid: facts-services-bom\nlayer: facts\ntopic: services\n"
                         "scope: company\nstatus: approved\nload: on-demand\n---\n"
                         "Rush jobs cost a quarter more.\n")
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_a_reference_keeps_its_first_heading_as_title(self):
        reference = self.brain.state().index.references["references/handbook.md"]
        self.assertEqual(reference.title, "Studio handbook")
        self.assertFalse(reference.body.startswith("﻿"))

    def test_a_note_with_front_matter_is_read(self):
        st = self.brain.state()
        self.assertEqual(st.snapshot.problems, [])
        self.assertIn("facts-services-bom", st.index.notes)


if __name__ == "__main__":
    unittest.main()
