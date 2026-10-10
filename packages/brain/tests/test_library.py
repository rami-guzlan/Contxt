"""The Library on a document's card: what kind of item it is (a guide to follow, a reference to
read whole, an influence whose taste to borrow), where it was fetched from and when, and how
often it is fetched again. The fields are checked when the document is filed, a new version
brings them up to date, and the owner changes the kind and the refresh as a decision with an
undo point.
"""
import os
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import uploads  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from tests import test_layout  # noqa: E402

GUIDE = """# How we write release notes

Lead with what changed for the customer, in one sentence. Then the details, newest first.
Never promise a date the team has not agreed.
"""

PAGE = """# Field guide to sourdough

Source: https://example.org/sourdough

Feed the starter twice a day. Bake when it doubles in four hours.
"""


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.vault = test_layout.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def file(self, content, filename, library, **kwargs):
        kwargs.setdefault("principal", "person:ana")
        kwargs.setdefault("origin", "app")
        return self.brain.add_file(content=content, filename=filename, library=library, **kwargs)

    def card(self, path):
        return self.brain.state().index.cards.get(path)

    def test_a_document_keeps_its_library_fields_on_its_card(self):
        filed = self.file(PAGE, "sourdough.md", {
            "library": "influence", "source_url": "https://example.org/sourdough",
            "fetched_at": "2026-10-09", "refresh": "weekly"})
        self.assertEqual(filed.data.get("status"), "applied", filed.text)
        card = self.card(filed.data["path"])
        self.assertEqual(card.meta["library"], "influence")
        self.assertEqual(card.meta["source_url"], "https://example.org/sourdough")
        self.assertEqual(card.meta["fetched_at"], "2026-10-09")
        self.assertEqual(card.meta["refresh"], "weekly")
        self.assertIn("Feed the starter", self.brain.reference(filed.data["path"]).text)

    def test_the_fields_are_checked_before_anything_is_filed(self):
        for library, why in (
            ({"library": "manual"}, "a prompt or an asset"),
            ({"library": "guide", "source_url": "http://example.org"}, "https://"),
            ({"refresh": "daily"}, "never, weekly or monthly"),
            ({"owner": "person:ana"}, "not a Library field"),
        ):
            res = self.file(GUIDE, "notes.md", library)
            self.assertTrue(res.is_error, library)
            self.assertIn(why, res.text)
        asset = self.brain.add_file(content="a,b\n1,2\n", filename="table.csv",
                                    library={"library": "reference"}, principal="person:ana")
        self.assertTrue(asset.is_error)
        self.assertIn("only a document", asset.text)
        self.assertFalse(self.brain.state().index.cards)  # nothing was filed

    def test_a_new_version_brings_the_fetch_date_up_to_date_and_keeps_the_kind(self):
        first = self.file(PAGE, "sourdough.md", {
            "library": "reference", "source_url": "https://example.org/sourdough",
            "fetched_at": "2026-10-01", "refresh": "monthly"})
        path = first.data["path"]
        again = self.file(PAGE.replace("four hours", "five hours"), "sourdough.md",
                          {"fetched_at": "2026-10-09"}, replaces=path)
        self.assertEqual(again.data.get("status"), "applied", again.text)
        card = self.card(path)
        self.assertEqual(card.meta["fetched_at"], "2026-10-09")
        self.assertEqual((card.meta["library"], card.meta["refresh"]), ("reference", "monthly"))
        self.assertIn("five hours", self.brain.reference(path).text)
        same = self.file(PAGE.replace("four hours", "five hours"), "sourdough.md",
                         {"fetched_at": "2026-10-10"}, replaces=path)
        self.assertEqual(same.data.get("status"), "duplicate")  # nothing new: nothing changes
        self.assertEqual(self.card(path).meta["fetched_at"], "2026-10-09")

    def test_the_owner_changes_the_kind_and_refresh_with_an_undo_point(self):
        filed = self.file(GUIDE, "release-notes.md", {"library": "reference"})
        card = self.card(filed.data["path"])
        res = self.brain.decide([{"id": card.id, "action": "update",
                                  "fields": {"library": "guide", "refresh": "never"}}])
        self.assertFalse(res.is_error, res.text)
        self.assertTrue(res.data["checkpoint"])
        self.assertEqual(self.card(filed.data["path"]).meta["library"], "guide")
        wrong = self.brain.decide([{"id": card.id, "action": "update",
                                    "fields": {"library": "manual"}}])
        self.assertTrue(wrong.is_error)
        self.assertIn("library is one of", wrong.data["results"][0]["message"])
        note = next(n for n in self.brain.state().snapshot.notes.values()
                    if str(n.meta.get("type")) != "file")
        plain = self.brain.decide([{"id": note.id, "action": "update",
                                    "fields": {"library": "guide"}}])
        self.assertTrue(plain.is_error)
        self.assertIn("only a document's card", plain.data["results"][0]["message"])

    def test_every_filing_says_where_it_came_from(self):
        page = self.file(PAGE, "sourdough.md", {"library": "reference",
                                                "source_url": "https://example.org/sourdough"})
        self.assertEqual(self.card(page.data["path"]).meta["origin"], "library")
        upload = self.brain.add_file(content=GUIDE, filename="notes.md", principal="person:ana",
                                     origin="app")
        self.assertEqual(self.card(upload.data["path"]).meta["origin"], "upload")
        recording = self.brain.add_file(content=GUIDE.replace("release", "launch"),
                                        filename="call.md", principal="person:ana",
                                        origin="app", came_from="capture:recording")
        self.assertEqual(self.card(recording.data["path"]).meta["origin"], "capture:recording")
        wrong = self.brain.add_file(content="x", filename="x.md", principal="person:ana",
                                    came_from="somewhere")
        self.assertTrue(wrong.is_error)
        self.assertIn("origin is one of", wrong.text)
        # The owner sets an older file's origin, or corrects one, as a decision.
        card = self.card(upload.data["path"])
        res = self.brain.decide([{"id": card.id, "action": "update",
                                  "fields": {"origin": "capture:export"}}])
        self.assertFalse(res.is_error, res.text)
        self.assertEqual(self.card(upload.data["path"]).meta["origin"], "capture:export")

    def test_an_asset_joins_the_library_as_an_asset(self):
        asset = self.brain.add_file(content="a,b\n1,2\n", filename="prices.csv",
                                    principal="person:ana", origin="app",
                                    library={"library": "asset"})
        self.assertEqual(asset.data.get("status"), "applied", asset.text)
        card = self.brain.state().index.asset_cards[asset.data["path"]]
        self.assertEqual((card.meta["library"], card.meta["origin"]), ("asset", "library"))
        document = self.file(GUIDE, "guide.md", {"library": "asset"})
        self.assertTrue(document.is_error)
        self.assertIn("not an asset", document.text)
        res = self.brain.decide([{"id": card.id, "action": "update",
                                  "fields": {"library": "guide"}}])
        self.assertTrue(res.is_error)
        self.assertIn("an asset's kind is asset", res.data["results"][0]["message"])

    def test_a_prompt_is_kept_word_for_word_and_only_used_when_named(self):
        words = ("Summarize this week's bakery orders.\n\n- Group by loaf\n- Flag any order "
                 "over 40 dollars\n\nKeep it to five lines.")
        filed = self.file(words, "weekly-orders.md", {"library": "prompt",
                                                      "tags": "orders, weekly"},
                          title="Weekly orders recap", came_from="chat")
        self.assertEqual(filed.data.get("status"), "applied", filed.text)
        path = filed.data["path"]
        self.assertTrue(path.startswith("references/prompts/"), path)
        card = self.card(path)
        self.assertEqual((card.meta["library"], card.load, card.scope),
                         ("prompt", "manual", "person:ana"))
        self.assertEqual(card.meta["tags"], ["orders", "weekly"])
        self.assertIn(words, card.body)  # the card carries the words exactly
        # Never routed or quoted on its own; found by a search and opened by its id.
        ctx = self.brain.context("summarize this week's orders by loaf",
                                 principal="person:ana")
        self.assertNotIn(card.id, ctx.data.get("note_ids") or [])
        self.assertFalse([s for s in ctx.data.get("section_ids") or [] if s.startswith(path)])
        self.assertIn(card.id, [h["id"] for h in self.brain.search(
            "weekly orders recap", principal="person:ana").data.get("hits") or []])
        self.assertIn("Flag any order over 40 dollars", self.brain.note(card.id).text)
        # A new version keeps it a prompt and updates the words on its card.
        again = self.file(words.replace("five", "three"), "weekly-orders.md", {},
                          replaces=path)
        self.assertEqual(again.data.get("status"), "applied", again.text)
        self.assertIn("Keep it to three lines.", self.card(path).body)
        self.assertEqual(self.card(path).meta["library"], "prompt")
        # Its earlier words are a version, in a Brain without git too.
        versions = self.brain.versions(card.id, with_text=True).data["versions"]
        self.assertIn("Keep it to five lines.", versions[-1]["body"])
        # A file that came with it says so on its card.
        sheet = self.brain.add_file(content="loaf,price\nrye,8\n", filename="prices.csv",
                                    principal="person:ana", origin="app",
                                    library={"attached_to": path})
        self.assertEqual(sheet.data.get("status"), "applied", sheet.text)
        attached = self.brain.state().index.asset_cards[sheet.data["path"]]
        self.assertEqual(attached.meta["attached_to"], path)
        stray = self.brain.add_file(content="loaf\nrye\n", filename="loaves.csv",
                                    principal="person:ana", origin="app",
                                    library={"attached_to": "references/prompts/nope.md"})
        self.assertTrue(stray.is_error)
        self.assertIn("not a document the brain holds", stray.text)
        # Its tags change as a decision.
        res = self.brain.decide([{"id": card.id, "action": "update",
                                  "fields": {"tags": "orders, weekly, money"}}])
        self.assertFalse(res.is_error, res.text)
        self.assertEqual(self.card(path).meta["tags"], ["orders", "weekly", "money"])
        # It stays a prompt, keeps a title, and is for a project the Brain has.
        for fields, why in (({"library": "guide"}, "filed as a prompt"),
                            ({"title": ""}, "cannot be empty"),
                            ({"project_id": "nope"}, "no project")):
            res = self.brain.decide([{"id": card.id, "action": "update", "fields": fields}])
            self.assertTrue(res.is_error, fields)
            self.assertIn(why, res.data["results"][0]["message"])
        wrong = self.file(words, "weekly.pdf", {"library": "prompt"})
        self.assertTrue(wrong.is_error)

    def test_library_meta_drops_empty_fields_and_keeps_picked_paths(self):
        self.assertEqual(uploads.library_meta({"library": "influence", "source_url": "",
                                               "source_paths": ["README.md", " ", "src/a.ts"]}),
                         {"library": "influence", "source_paths": ["README.md", "src/a.ts"]})


if __name__ == "__main__":
    unittest.main()
