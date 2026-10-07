"""Presets and the capture policy: what the owner's own AI notes in a chat goes in at once or
waits, by what it is, and how a preset is chosen."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import checkpoints, governance
from brainkit.api import Brain
from tests import fixture


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def choose(self, preset, **more):
        changed = self.brain.set_policies(dict(preset=preset, **more), actor="person:alex")
        self.assertFalse(changed.is_error, changed.text)
        return changed

    def decisions(self):
        path = os.path.join(self.vault, "journal", "decisions.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def chat(self, layer, topic, text, **more):
        return self.brain.propose(layer=layer, topic=topic, scope="company", text=text,
                                  session_id="sess-abc123", capture_origin="chat", **more)

    def test_a_brain_without_a_preset_is_careful_and_chat_facts_wait(self):
        policy = self.brain.policies().data
        self.assertEqual(policy["preset"], "careful")
        self.assertEqual(policy["capture"]["fact"]["chat"], "wait")
        self.assertEqual(policy["capture"]["file"]["chat"], "apply")
        made = self.chat("facts", "services", "Motion retainers renew every quarter.")
        self.assertEqual(made.data["status"], "pending", made.text)
        (proposal,) = self.brain.state().snapshot.proposals.values()
        self.assertEqual(proposal.meta.get("capture"), "fact:chat")

    def test_personal_lets_a_chat_fact_in_at_once_as_an_undo_point(self):
        self.choose("personal")
        made = self.chat("facts", "services", "Motion retainers renew every quarter.")
        self.assertEqual(made.data["status"], "applied", made.text)
        self.assertIn("lets fact from chat in", made.text)
        note_id = made.data["id"]
        self.assertIn(note_id, self.brain.state().index.notes)
        record = self.decisions()[-1]
        self.assertEqual((record["action"], record["capture"]), ("auto-applied", "fact:chat"))
        point = made.data["checkpoint"]
        self.assertTrue(point and point["label"].startswith("Went in on its own"))
        undone = checkpoints.undo(self.brain, point["id"], actor="person:alex")
        self.assertFalse(undone.is_error, undone.text)
        self.assertNotIn(note_id, self.brain.state().index.notes)

    def test_personal_still_holds_what_shapes_every_ai_or_changes_what_is_there(self):
        self.choose("personal")
        rule = self.chat("rules", "style", "Always end a client email with the next step.")
        self.assertEqual(rule.data["status"], "pending", rule.text)
        clash = self.chat("facts", "services", "Web design projects take twelve weeks.",
                          conflicts="facts-services-002")
        self.assertEqual(clash.data["status"], "pending", clash.text)
        replacing = self.chat("facts", "services", "Web projects run eight weeks, kickoff to "
                              "launch.", supersedes="facts-services-002")
        self.assertEqual(replacing.data["status"], "pending", replacing.text)
        flagged = self.chat("facts", "services", r"Rate cards live in C:\Users\alex\rates.xlsx.")
        self.assertEqual(flagged.data["status"], "pending", flagged.text)
        change = self.brain.propose(target_id="facts-services-001", text="Northwind offers "
                                    "brand identity and web design.", session_id="sess-abc123",
                                    capture_origin="chat")
        self.assertEqual(change.data["status"], "pending", change.text)

    def test_a_person_can_let_one_more_type_in(self):
        self.choose("personal")
        changed = self.brain.set_policies({"capture": {"rule": {"chat": "apply"}}},
                                          actor="person:alex")
        self.assertFalse(changed.is_error, changed.text)
        with open(os.path.join(self.vault, "brain.json"), encoding="utf-8") as handle:
            governed = json.load(handle)["governance"]
        self.assertEqual(governed["capture"], {"rule": {"chat": "apply"}})  # only what differs
        made = self.chat("rules", "style", "Always end a client email with the next step.")
        self.assertEqual(made.data["status"], "applied", made.text)

    def test_regulated_holds_everything_a_chat_brings_even_the_owners_own(self):
        self.choose("personal")
        self.brain.set_policies({"capture": {"rule": {"chat": "apply"}}}, actor="person:alex")
        changed = self.choose("regulated")
        policy = changed.data["policy"]
        self.assertEqual(policy["preset"], "regulated")
        self.assertFalse(policy["auto_apply_own_scope"])
        self.assertEqual(policy["capture"]["rule"]["chat"], "wait")  # the override went
        self.assertEqual(policy["capture"]["file"]["chat"], "wait")
        fact = self.chat("facts", "services", "Motion retainers renew every quarter.")
        self.assertEqual(fact.data["status"], "pending", fact.text)
        own = self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                                 text="Give me the answer first, reasoning after.",
                                 session_id="sess-abc123", capture_origin="chat")
        self.assertEqual(own.data["status"], "pending", own.text)
        filed = self.brain.add_file(content="# Rates\n\nDay rate: 900.", filename="rates.md",
                                    principal="person:alex", origin="chat")
        self.assertEqual(filed.data["status"], "pending", filed.text)

    def test_a_preset_is_checked_and_reported(self):
        bad = self.brain.set_policies({"preset": "reckless"}, actor="person:alex")
        self.assertTrue(bad.is_error)
        self.assertIn("preset is one of", bad.text)
        self.choose("personal")
        policy = self.brain.policies().data
        self.assertEqual((policy["preset"], policy["presets"]),
                         ("personal", ["personal", "careful", "regulated"]))
        self.assertEqual(policy["capture"]["decision"]["chat"], "apply")
        self.assertEqual(policy["capture"]["rule"]["chat"], "wait")

    def test_remember_from_a_chat_files_in_the_owners_scope_unless_regulated(self):
        self.choose("personal")
        made = self.brain.remember("Our studio closes the last week of December.",
                                   capture_origin="chat")
        self.assertEqual(made.data["status"], "applied", made.text)
        self.choose("regulated")
        held = self.brain.remember("Our studio reopens on the second of January.",
                                   capture_origin="chat")
        self.assertEqual(held.data["status"], "pending", held.text)

    def test_the_journal_says_which_capture_a_rejected_proposal_was(self):
        made = self.chat("facts", "services", "Motion retainers renew every quarter.")
        rejected = governance.reject(self.brain, made.data["proposal_id"], "Not true")
        self.assertFalse(rejected.is_error, rejected.text)
        record = self.decisions()[-1]
        self.assertEqual((record["action"], record["capture"]), ("rejected", "fact:chat"))

    def test_capture_types(self):
        cases = [
            ("note.update", {"kind": "fact"}, "change"),
            ("note.create", {"kind": "rule"}, "rule"),
            ("note.create", {"layer": "rules"}, "rule"),
            ("note.create", {"kind": "identity"}, "convention"),
            ("note.create", {"kind": "state"}, "progress"),
            ("note.create", {"kind": "fact", "type": "decision"}, "decision"),
            ("note.create", {"layer": "facts"}, "fact"),
        ]
        for kind, target, expected in cases:
            self.assertEqual(governance.capture_type(kind, target), expected, (kind, target))


if __name__ == "__main__":
    unittest.main()
