"""The area layout: naming, placement, projects, caveats, and new knowledge used at once.

A second small brain, a bakery, filed the way a new vault is: knowledge/<area>/<topic>/, with
kinds, titles and summaries, and a project folder holding its Focus. The design-studio fixture
keeps covering the older layer layout.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import frontmatter as fm
from brainkit import governance, util
from brainkit.api import Brain

BRAIN = {
    "schema": 1,
    "name": "Crumb Bakery Brain",
    "owner": "person:ana",
    "structure": {
        "scope_levels": [
            {"kind": "company", "label": "Company", "prefix": "", "container": ""},
            {"kind": "person", "label": "Person", "prefix": "person:", "container": "people",
             "principal": True},
        ],
        "areas": {
            "company": {"label": "Company", "order": 1},
            "customers": {"label": "Customers", "order": 2},
            "brand": {"label": "Brand", "order": 3},
            "marketing": {"label": "Marketing", "order": 4},
            "operations": {"label": "Operations", "order": 5},
            "projects": {"label": "Projects", "order": 6},
            "topics": {"label": "Topics", "order": 7},
        },
    },
    "scopes": {"company": {"label": "Crumb"}, "person:ana": {"parent": "company"}},
    "governance": {"approver": "person:ana", "auto_apply_own_scope": True},
    "git": {"auto_commit": False},
}

TOPICS = """# Topics

## Company

company/menu: what we bake and sell: breads, pastries, cakes, prices, seasonal specials
company/story: how to describe the bakery: founding, sourcing, what makes us different

## Brand

brand/voice: how we write: warm, plain, no hype words

## Marketing

marketing/social: Instagram posting rhythm, photo style, and captions
"""

ROUTING = {
    "house_style_topics": ["brand/voice"],
    "topics": {"marketing/social": {"with_notes": ["social-plan-on-hold"]}},
}

NOTES = [
    ({"id": "sourdough-loaves", "title": "Sourdough loaves", "area": "company", "topic": "menu",
      "kind": "fact", "summary": "Three sourdough loaves and their prices.",
      "added": "2026-08-01"},
     "We bake three sourdough loaves daily: country, rye and seeded, each 8 dollars."),
    ({"id": "celebration-cakes", "title": "Celebration cakes", "area": "company",
      "topic": "menu", "kind": "fact", "summary": "Custom cakes need five days' notice.",
      "added": "2026-08-01"},
     "Celebration cakes are custom and need five days of notice and a deposit."),
    ({"id": "founding-story", "title": "Founding story", "area": "company", "topic": "story",
      "kind": "fact", "summary": "Founded in 2019 by Ana in a converted garage.",
      "added": "2026-08-01"},
     "Crumb was founded in 2019 by Ana, baking from a converted garage before the shop."),
    ({"id": "plain-warm-voice", "title": "Plain, warm voice", "area": "brand",
      "topic": "voice", "kind": "rule", "summary": "Write warmly and plainly; no hype words.",
      "added": "2026-08-01"},
     "Write warmly and plainly. Never use hype words such as artisanal or elevated."),
    ({"id": "instagram-rhythm", "title": "Instagram rhythm", "area": "marketing",
      "topic": "social", "kind": "fact", "summary": "Post on Instagram three mornings a week.",
      "added": "2026-08-01"},
     "Post on Instagram on Monday, Wednesday and Friday mornings with a fresh bake photo."),
    ({"id": "social-plan-on-hold", "title": "Social plan on hold", "area": "marketing",
      "topic": "social", "kind": "fact", "summary": "The social plan is being rewritten.",
      "added": "2026-08-01"},
     "The Instagram plan is being rewritten; ask Ana before changing the posting rhythm."),
    ({"id": "spring-market", "title": "Spring market stall", "area": "projects",
      "topic": "spring-market", "kind": "focus", "project": "Spring market stall",
      "summary": "Booking the stall and planning the menu", "added": "2026-08-10",
      "scope": "person:ana"},
     "Spring market stall: book the Saturday pitch, plan a six-item menu, print signs."),
    ({"id": "market-stall-permit", "title": "Market stall permit", "area": "projects",
      "topic": "spring-market", "kind": "fact", "summary": "The stall needs a food permit.",
      "added": "2026-08-10", "scope": "person:ana"},
     "The market stall needs a temporary food permit from the council, two weeks ahead."),
]


def build():
    base = tempfile.mkdtemp(prefix="brain-layout-")
    vault = os.path.join(base, "vault")
    os.makedirs(vault)
    with open(os.path.join(vault, "brain.json"), "w", encoding="utf-8") as handle:
        json.dump(BRAIN, handle, indent=2)
    with open(os.path.join(vault, "topics.md"), "w", encoding="utf-8") as handle:
        handle.write(TOPICS)
    with open(os.path.join(vault, "routing.json"), "w", encoding="utf-8") as handle:
        json.dump(ROUTING, handle, indent=2)
    for meta, body in NOTES:
        meta = dict(meta)
        meta.setdefault("scope", "company")
        meta.setdefault("status", "approved")
        meta.setdefault("load", "on-demand")
        folder = os.path.join(vault, "knowledge", meta["area"], meta["topic"])
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{meta['added']}-{meta['id']}.md")
        util.atomic_write(path, fm.dump(meta, body + "\n"))
    return vault


class AreaLayoutTests(unittest.TestCase):
    def setUp(self):
        self.vault = build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def ctx(self, request, **kwargs):
        return self.brain.context(request, principal="person:ana", record=False, **kwargs)

    def test_notes_carry_area_kind_title_and_projects_are_focus_by_kind(self):
        st = self.brain.state()
        note = st.index.note("plain-warm-voice")
        self.assertEqual((note.area, note.topic, note.kind), ("brand", "voice", "rule"))
        self.assertEqual(note.title, "Plain, warm voice")
        self.assertIn("spring-market", st.index.focuses)
        self.assertEqual(st.index.focuses["spring-market"].title, "Spring market stall")
        health = self.brain.health()
        self.assertTrue(health.data.get("ok"), health.text)

    def test_new_note_is_named_for_its_purpose_and_dated(self):
        res = self.brain.propose(area="company", topic="menu", title="Gluten-free brownies",
                                 text="We bake gluten-free brownies on Thursdays.",
                                 scope="person:ana")
        self.assertFalse(res.is_error, res.text)
        self.assertEqual(res.data["id"], "gluten-free-brownies")
        path = res.data["path"]
        self.assertEqual(path, f"knowledge/company/menu/{util.today()}-gluten-free-brownies.md")
        meta, _body, _errors = fm.parse(util.read_text(os.path.join(self.vault, path)))
        self.assertEqual(meta["title"], "Gluten-free brownies")
        self.assertEqual(meta["kind"], "fact")
        self.assertTrue(meta["summary"])
        self.assertNotIn("layer", meta)

    def test_a_rule_is_recognized_and_an_untitled_note_gets_a_title(self):
        res = self.brain.propose(area="brand", topic="voice", scope="person:ana",
                                 text="Never call a cake moist in a caption.")
        self.assertEqual(res.data["id"], "never-call-cake-moist-caption")
        note = self.brain.state().index.note(res.data["id"])
        self.assertEqual(note.kind, "rule")

    def test_a_new_topic_comes_back_with_the_closest_existing_ones(self):
        res = self.brain.propose(area="company", topic="breads", scope="company",
                                 title="Rye loaf flour",
                                 text="Our rye loaf uses stone-ground rye flour from a local mill.")
        self.assertEqual(res.data["status"], "pending", res.text)
        self.assertIn("company/breads is a new topic", res.text)
        self.assertIn("company/menu", res.data["suggested"])
        inbox = self.brain.inbox().data["proposals"]
        self.assertIn("company/menu", inbox[0]["suggested"])

    def test_approved_note_in_a_brand_new_topic_is_used_on_the_next_call(self):
        res = self.brain.propose(area="operations", topic="deliveries", scope="company",
                                 title="Wholesale delivery days",
                                 text="Wholesale bread deliveries to cafes go out on Tuesdays "
                                      "and Fridays before 7am.")
        proposal = res.data["proposal_id"]
        self.assertNotIn(res.data["id"], self.ctx("When do wholesale deliveries go out?")
                         .data["note_ids"])
        approved = governance.approve(self.brain, proposal)
        self.assertFalse(approved.is_error, approved.text)
        data = self.ctx("When do wholesale deliveries go out to cafes?").data
        self.assertIn("wholesale-delivery-days", data["note_ids"])
        text = self.ctx("When do wholesale deliveries go out to cafes?").text
        self.assertIn("Wholesale delivery days (new)", text)

    def test_owner_can_move_a_note_when_approving_and_later(self):
        res = self.brain.propose(area="company", topic="breads", scope="company",
                                 title="Baguette bake times",
                                 text="Baguettes come out of the oven at 7am and noon.")
        approved = governance.approve(self.brain, res.data["proposal_id"],
                                      edits={"topic": "menu"})
        self.assertFalse(approved.is_error, approved.text)
        self.assertTrue(approved.data["path"].startswith("knowledge/company/menu/"))
        moved = self.brain.propose(target_id="baguette-bake-times", topic="story",
                                   scope="company")
        governance.approve(self.brain, moved.data["proposal_id"])
        note = self.brain.state().index.note("baguette-bake-times")
        self.assertEqual(note.route_key, "company/story")
        self.assertFalse(os.path.exists(os.path.join(self.vault, *approved.data["path"]
                                                     .split("/"))))

    def test_a_new_title_or_place_keeps_the_note_as_new_as_its_text(self):
        res = self.brain.propose(area="company", topic="menu", scope="company",
                                 title="Brownie days",
                                 text="We bake gluten-free brownies on Thursdays.")
        governance.approve(self.brain, res.data["proposal_id"])
        note_id = res.data["id"]
        revised = self.brain.state().index.note(note_id).meta["revised"]
        time.sleep(1.1)  # stamps are to the second
        renamed = self.brain.propose(target_id=note_id, title="Gluten-free brownie day",
                                     summary="Which day the gluten-free brownies are baked.",
                                     topic="story", scope="company")
        governance.approve(self.brain, renamed.data["proposal_id"])
        note = self.brain.state().index.note(note_id)
        self.assertEqual((note.title, note.route_key), ("Gluten-free brownie day", "company/story"))
        self.assertEqual(note.meta["revised"], revised)
        self.assertNotEqual(note.meta["approved_at"], revised)
        rewritten = self.brain.propose(target_id=note_id, scope="company",
                                       text="We bake gluten-free brownies on Fridays.")
        governance.approve(self.brain, rewritten.data["proposal_id"])
        self.assertNotEqual(self.brain.state().index.note(note_id).meta["revised"], revised)

    def test_a_note_without_a_summary_gets_its_first_sentence(self):
        res = self.brain.propose(area="company", topic="menu", scope="company",
                                 title="Cake deposits",
                                 text="Celebration cakes need a deposit. The rest is paid on "
                                      "pickup, by card or cash.")
        governance.approve(self.brain, res.data["proposal_id"])
        note = self.brain.state().index.note(res.data["id"])
        self.assertEqual(note.meta["summary"], "Celebration cakes need a deposit.")
        long = governance.summary_from("word " * 80 + "end.")
        self.assertLessEqual(len(long), 200)
        self.assertTrue(long.endswith("word..."))

    def test_a_rule_you_set_for_yourself_rides_in_your_startup_context(self):
        mine = self.brain.propose(area="brand", topic="voice", scope="person:ana",
                                  title="Plain-text drafts",
                                  text="I prefer plain-text drafts with no formatting.")
        self.assertEqual(mine.data["status"], "applied", mine.text)
        note = self.brain.state().index.note(mine.data["id"])
        self.assertEqual((note.kind, note.load), ("rule", "standing"))
        said = self.brain.propose(area="brand", topic="voice", scope="person:ana",
                                  load="on-demand", title="Short captions",
                                  text="Never write captions longer than two lines.")
        self.assertEqual(self.brain.state().index.note(said.data["id"]).load, "on-demand")

    def test_remember_files_a_personal_preference_in_the_persons_folder(self):
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["structure"]["areas"]["people"] = {"label": "People", "order": 8}
        data["scopes"]["person:ana"]["label"] = "Ana Ruiz"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        self.brain.close()
        self.brain = Brain(self.vault, embeddings=False)
        res = self.brain.remember("I prefer short answers with the price first.")
        note = self.brain.state().index.note(res.data["id"])
        self.assertEqual(note.route_key, "people/ana-ruiz")
        self.assertEqual(note.load, "standing")

    def test_a_chosen_place_clears_placement_guessed(self):
        res = self.brain.remember("The sourdough starter is fed twice a day.")
        note_id = res.data["id"]
        self.assertEqual(self.brain.state().index.note(note_id).meta.get("placement"), "guessed")
        moved = self.brain.propose(target_id=note_id, area="company", topic="story",
                                   scope="person:ana")
        self.assertFalse(moved.is_error, moved.text)
        self.assertEqual(self.brain.state().index.note(note_id).meta.get("placement"), "chosen")

    def test_create_focus_gets_its_own_project_folder(self):
        res = self.brain.focus_create("Holiday gift boxes", "Design and price a gift box.")
        self.assertFalse(res.is_error, res.text)
        st = self.brain.state()
        self.assertIn("holiday-gift-boxes", st.index.focuses)
        focus = st.index.focuses["holiday-gift-boxes"]
        self.assertEqual(focus.note.route_key, "projects/holiday-gift-boxes")
        self.assertEqual(focus.note.kind, "focus")
        update = self.brain.focus_update("holiday gift boxes", "Box supplier chosen")
        self.assertFalse(update.is_error, update.text)

    def test_a_named_project_brings_its_own_notes(self):
        data = self.ctx("Draft the plan for the spring market stall").data
        self.assertEqual(data["focus_id"], "spring-market")
        self.assertIn("market-stall-permit", data["note_ids"])

    def test_a_topic_caveat_travels_with_its_notes(self):
        data = self.ctx("When should we post on Instagram?").data
        self.assertIn("instagram-rhythm", data["note_ids"])
        self.assertIn("social-plan-on-hold", data["note_ids"])

    def test_old_ids_resolve_through_aliases(self):
        with open(os.path.join(self.vault, "aliases.json"), "w", encoding="utf-8") as handle:
            json.dump({"facts-menu-001": "sourdough-loaves"}, handle)
        note = self.brain.note("facts-menu-001")
        self.assertFalse(note.is_error, note.text)
        self.assertIn("Sourdough loaves", note.text)


if __name__ == "__main__":
    unittest.main()
