"""The knowledge agent's map and evidence: made by code from the brain as it is, every action's
candidates with the text a model needs and a short reference to answer by."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import agent, util
from brainkit.api import Brain
from brainkit.vault import Vault
from tests import fixture


def days_ago(days: int) -> str:
    return (util.today_date() - dt.timedelta(days=days)).isoformat()


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def add(self, note_id, layer, topic, body, **extra):
        meta, text = fixture.note(note_id, layer, topic, "company", body, **extra)
        v = Vault(self.vault)
        levels = fixture.BRAIN["structure"]["scope_levels"]
        kinds = fixture.BRAIN["structure"]["partition_kinds"]
        v.write_note(v.note_path(meta, levels, kinds), dict(meta), text)
        self.brain.state()  # the next read sees it

    def test_the_map_lists_every_live_note_with_what_upkeep_cares_about(self):
        self.add("facts-team-001", "facts", "services", "The studio has 12 people.",
                 valid_until=days_ago(3))
        found = self.brain.agent_outline().data
        ids = [n["id"] for a in found["areas"] for t in a["topics"] for n in t["notes"]]
        self.assertIn("rules-style-002", ids)
        self.assertNotIn("facts-services-000", ids)  # archived
        self.assertNotIn("state-focus-website-redesign", ids)  # a project, listed apart
        self.assertEqual(found["counts"]["notes"], len(ids))
        team = next(n for a in found["areas"] for t in a["topics"] for n in t["notes"]
                    if n["id"] == "facts-team-001")
        self.assertTrue(any(f.startswith("stale") for f in team["flags"]))
        self.assertIn("in every chat", next(
            n for a in found["areas"] for t in a["topics"] for n in t["notes"]
            if n["id"] == "rules-style-001")["flags"])
        text = found["text"]
        self.assertIn("`rules-style-002`", text)
        self.assertIn("Website Redesign", text)
        self.assertIn("/brand-sheet", text)
        self.assertIn("Not said yet", text)  # no goals in the fixture
        brief = self.brain.agent_outline(brief=True).data["text"]
        self.assertLess(len(brief), len(text))
        self.assertIn("`facts-team-001`", brief)  # flagged notes stay in the brief map
        self.assertNotIn("`rules-style-002`", brief)

    def test_repeats_come_as_pairs_with_both_texts_and_a_reference(self):
        self.add("rules-style-009", "rules", "style",
                 "Headlines use sentence case, stay under nine words, and state one benefit.")
        found = self.brain.agent_gather("tidy-repeats").data
        (first, *_) = found["candidates"]
        self.assertEqual(first["ref"], "c1")
        self.assertEqual(sorted(first["ids"]), ["rules-style-002", "rules-style-009"])
        self.assertIn("Note A:", first["text"])
        self.assertIn("Note B:", first["text"])

    def test_drift_reads_an_older_dated_value_against_a_newer_one(self):
        self.add("facts-team-001", "facts", "services", "The studio has 12 people.",
                 as_of=days_ago(200))
        self.add("facts-team-002", "facts", "services", "The studio has 15 people.",
                 as_of=days_ago(10))
        candidates = self.brain.agent_gather("check-drift").data["candidates"]
        pair = next(c for c in candidates if set(c["ids"]) == {"facts-team-001", "facts-team-002"})
        self.assertIn("Older value", pair["text"])
        self.assertTrue(pair["text"].index("facts-team-001") < pair["text"].index("facts-team-002"))

    def test_stale_notes_quiet_projects_unused_skills_and_gaps_are_candidates(self):
        self.add("facts-team-001", "facts", "services", "The studio has 12 people.",
                 valid_until=days_ago(3))
        stale = self.brain.agent_gather("freshen-up").data["candidates"]
        self.assertIn(["facts-team-001"], [c["ids"] for c in stale])
        projects = self.brain.agent_gather("tidy-projects").data["candidates"]
        # the redesign last moved in September; the podcast is paused, quiet on purpose
        self.assertEqual([c["ids"] for c in projects], [["state-focus-website-redesign"]])
        self.assertIn("Write the case studies", projects[0]["text"])
        skills = self.brain.agent_gather("tidy-skills").data["candidates"]
        self.assertIn(["brand-sheet"], [c["ids"] for c in skills])
        self.brain.context("What is the office parking policy for visitors?")
        gaps = self.brain.agent_gather("fill-gaps").data["candidates"]
        self.assertTrue(any("parking" in c["text"] for c in gaps))
        alignment = self.brain.agent_gather("check-alignment").data["candidates"]
        self.assertEqual(alignment[0]["kind"], "goals")

    def test_limits_and_unknown_actions(self):
        for number in range(4):
            self.add(f"rules-style-01{number}", "rules", "style",
                     "Headlines use sentence case, stay under nine words, and state one benefit.")
        found = self.brain.agent_gather("tidy-repeats", limit=2).data
        self.assertEqual([c["ref"] for c in found["candidates"]], ["c1", "c2"])
        self.assertGreater(found["found"], 2)
        missing = self.brain.agent_gather("tidy-everything")
        self.assertTrue(missing.is_error)

    def test_the_agents_procedures_ship_with_the_engine_and_a_brain_skill_replaces_one(self):
        names = [s["name"] for s in self.brain.agent_skills().data["skills"]]
        self.assertEqual(names, [agent.CHAT, *agent.ACTIONS])
        text = self.brain.agent_skill("tidy-repeats").data["text"]
        self.assertIn('"verdict": "merge"', text)
        self.assertTrue(self.brain.agent_skill("brand-sheet").is_error)
        folder = os.path.join(self.vault, "skills", "brain", "tidy-repeats")
        os.makedirs(folder)
        with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("---\nname: tidy-repeats\ndescription: Mine.\n---\n# /tidy-repeats\n\nMy way.\n")
        self.brain.state()
        self.assertIn("My way.", self.brain.agent_skill("tidy-repeats").data["text"])
        own = next(s for s in self.brain.agent_skills().data["skills"] if s["name"] == "tidy-repeats")
        self.assertTrue(own["own"])


if __name__ == "__main__":
    unittest.main()
