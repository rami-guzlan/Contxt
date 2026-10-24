"""Release 1 ships auto-governed (design contracts, amendment 2026-10-23): a new Brain starts in
Auto, a Brain from before switches once with a notice it can reverse, the governing AI's changes
go in with an undo point and a reason, and what must wait still waits."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import governance
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class AutoDefaultTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def edit_config(self, change):
        self.brain.close()
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
        change(config)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(config, handle)
        self.brain = se.open_brain(self.vault)

    def mode(self):
        return governance.policies(self.brain)["mode"]

    def propose(self, text, *, area="work", topic="status", origin="connector", **extra):
        return governance.propose_note(
            self.brain, area=area, topic=topic, text=text, title=text[:40], scope="company",
            capture_origin=origin, reason="HubSpot: registrations went from 364 to 388",
            **extra)

    # ------------------------------------------------------------ the default and the switch

    def test_a_brain_from_before_switches_to_auto_once_with_a_notice_it_can_reverse(self):
        self.assertEqual(self.mode(), "governed")
        notice = governance.migrate(self.brain)
        self.assertEqual(self.mode(), "auto")
        self.assertEqual(notice["was"], "governed")
        self.assertEqual(governance.policies(self.brain)["auto_notice"]["was"], "governed")
        governance.set_policies(self.brain, {"mode": "governed"})
        self.assertIsNone(governance.migrate(self.brain))  # once only: the choice stands
        self.assertEqual(self.mode(), "governed")

    def test_a_new_brain_starts_auto_governed_without_a_notice(self):
        self.assertIsNone(governance.migrate(self.brain, fresh=True))
        self.assertEqual(self.mode(), "auto")
        self.assertIsNone(governance.policies(self.brain)["auto_notice"])

    def test_the_one_time_notice_can_be_dismissed(self):
        governance.migrate(self.brain)
        governance.set_policies(self.brain, {"auto_notice": None})
        self.assertIsNone(governance.policies(self.brain)["auto_notice"])
        self.assertEqual(self.mode(), "auto")

    # ------------------------------------------------------------ what Auto does

    def test_in_auto_the_governor_applies_a_connector_change_with_its_reason(self):
        governance.migrate(self.brain, fresh=True)
        done = self.propose("388 of 450 are registered for the Oct 22 session.")
        self.assertEqual(done.data["status"], "applied")
        self.assertTrue(done.data["checkpoint"])  # an undo point
        record = [r for r in self.brain.vault.decisions()
                  if r.get("action") == "auto-applied"][-1]
        self.assertEqual(record["applied_by"], "governor")
        self.assertIn("364 to 388", record["reason"])

    def test_governed_a_connector_change_waits(self):
        governance.migrate(self.brain, fresh=True)
        governance.set_policies(self.brain, {"mode": "governed"})
        self.assertEqual(self.propose("388 of 450 are registered.").data["status"], "pending")

    def test_in_auto_what_must_wait_still_waits(self):
        governance.migrate(self.brain, fresh=True)
        self.edit_config(lambda c: c.setdefault("partitions", {}).update(
            {"client:acme": {"label": "Acme", "owner": "company", "sealed": True}}))
        waits = {
            "must-hold": self.propose("Never share pricing until it is final.",
                                      load="domain", applies_to=["work"]),
            "private": self.propose("Dana's home number is in the drive.",
                                    extra={"classification": "restricted"}),
            "customer-facing": self.propose("Tell the attendees the session moved.",
                                            extra={"customer_facing": True}),
            "spends": self.propose("Raise the ad budget to 900 a month.",
                                   extra={"spends": True}),
            "sealed project": self.propose("Acme renewal is at risk.", partition="client:acme"),
        }
        for why, result in waits.items():
            with self.subTest(why):
                self.assertEqual(result.data["status"], "pending", result.text)
                self.assertIn(why, result.data["waits"])

    def test_an_area_handed_back_is_governed_by_the_owner_until_given_back(self):
        governance.migrate(self.brain, fresh=True)
        governance.set_policies(self.brain, {"self_governed": ["area:work"]})
        held = self.propose("The launch moved to Nov 10.")
        self.assertEqual(held.data["status"], "pending")
        self.assertIn("governed by you", held.data["waits"])
        self.assertEqual(self.propose("Morgan is out Friday.", area="people",
                                      topic="team").data["status"], "applied")
        governance.set_policies(self.brain, {"self_governed": []})
        self.assertEqual(self.propose("The launch moved to Nov 12.", topic="dates")
                         .data["status"], "applied")


if __name__ == "__main__":
    unittest.main()
