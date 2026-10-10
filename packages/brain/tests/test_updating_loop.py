"""The updating loop (brain-logic plan 9) and its gates as seeded tests: correction suspects,
the exceptions ledger, approval health, output checks against must-holds, single-source flags,
independent evidence, admins per scope, the blast radius through the replay harness, and wrong
beliefs found."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest

from brainkit import agent, governance, loop, measures, outputcheck
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)
        self.owner = self.brain.state().config.owner

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def note(self, text, *, area="marketing", topic="voice", kind="rule", extra=None,
             title=None):
        made = self.brain.propose(area=area, topic=topic, text=text, title=title,
                                  note_kind=kind, principal=self.owner, extra=extra,
                                  force_pending=True)
        self.assertFalse(made.is_error, made.text)
        done = self.brain.approve(made.data["proposal_id"], actor=self.owner)
        self.assertFalse(done.is_error, done.text)
        return made.data.get("id") or done.data.get("id")

    def test_a_correction_names_the_note_behind_it(self):
        """Correction suspects right 60% or more on a seeded set."""
        cases = [
            ("Plan the next webinar promo", "No, the webinars run on Thursdays, not Tuesdays",
             "Webinars run on Tuesdays at noon."),
            ("Draft the procurement email", "Wrong: procurement wants a W-9 and a PO, not only "
             "an invoice", "Procurement asks for a W-9 and an invoice."),
            ("Who approves landing pages", "Actually Morgan no longer approves landing pages, "
             "Dana does", "Morgan approves landing pages and promo posts."),
            ("Write the newsletter intro", "That's wrong, the newsletter goes out monthly now",
             "The newsletter goes out every other Thursday."),
            ("Price the workshop", "No, the workshop costs 900 dollars, not 750",
             "The supervisor workshop costs 750 dollars a seat."),
        ]
        right = 0
        for request, correction, belief in cases:
            target = self.note(belief, kind="fact", topic="facts-" + str(len(belief)))
            brief = self.brain.context(request + " " + belief.split()[0])
            session = brief.text.split("session_id: ")[1].split(" ")[0]
            # The brief carried the belief (named in the request) among others.
            found = self.brain.correction(correction, session_id=session)
            if found.data["card"] and found.data["card"]["id"] == target:
                right += 1
        self.assertGreaterEqual(right / len(cases), 0.6)
        status = self.brain.loop_status().data
        self.assertTrue(status["corrections"])
        closed = self.brain.close_correction(status["corrections"][0]["id"], "fixed")
        self.assertFalse(closed.is_error)

    def test_an_exception_sequence_is_flagged_at_the_third(self):
        rule = self.note("Never discount the workshop below 750 dollars a seat.",
                         topic="pricing")
        for n, text in enumerate(["We discount the workshop below 750 dollars a seat for "
                                  "returning teams.",
                                  "We discount the workshop below 750 dollars a seat in Q4.",
                                  "We discount the workshop below 750 dollars a seat for "
                                  "nonprofits."], start=1):
            self.note(text, topic="pricing", kind="fact")
            flagged = [r["rule"] for r in loop.bent_rules(self.brain)]
            self.assertEqual(rule in flagged, n >= 3, n)
        self.assertEqual(loop.exceptions(self.brain, rule), 3)

    def test_approval_health_suggests_fewer_weightier_decisions(self):
        for n in range(12):
            self.note(f"Fact number {n}: the booth needs {n + 2} chairs.", kind="fact",
                      topic=f"booth-{n}")
        health = loop.approval_health(self.brain)
        self.assertEqual(health["decided"] >= 12, True)
        self.assertLessEqual(health["median_seconds"], loop.FAST_SECONDS)
        self.assertIn("apply with undo", health["advice"])

    def test_every_seeded_deterministic_violation_is_caught(self):
        holds = [
            self.note("Never say 25+ years: say 40+ years.", topic="claims",
                      extra={"load": "domain", "applies_to": ["marketing"],
                             "triggers": ["years"]}),
            self.note("Delivered copy uses no em dashes or en dashes.", topic="punctuation",
                      extra={"load": "domain", "applies_to": ["marketing"],
                             "triggers": ["copy"]}),
            self.note("Never write \"world-class\" about ourselves.", topic="words",
                      extra={"load": "domain", "applies_to": ["marketing"],
                             "triggers": ["copy"]}),
        ]
        notes = [self.brain.state().index.note(h) for h in holds]
        self.assertTrue(all(n.must_hold for n in notes), [n.load for n in notes])
        seeded = [
            ("With 25+ years in training, we know plants.", "figure"),
            ("Our approach — simple and fast.", "dash"),
            ("A world-class team for your floor.", "phrase"),
            ("Short shifts – long results.", "dash"),
        ]
        for text, kind in seeded:
            found = outputcheck.check(text, notes)
            self.assertEqual([v.kind for v in found], [kind], text)
        self.assertEqual(outputcheck.check("With 40+ years, a simple plan.", notes), [])
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "draft.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("Our copy has 25+ years of trust.")
            recorded = self.brain.record_output(path, title="Draft")
            self.assertEqual(recorded.data["status"], "flagged")
            self.assertIn("25+ years", recorded.text)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        # G3's signals: the flagged output and a draft sent back both count, as does a
        # correction.
        back = self.brain.check_output("Copy with 25+ years.", domains=["marketing"],
                                       sent_back="run:1")
        self.assertTrue(back.data["violations"])
        self.brain.correction("No, it is 40+ years.")
        self.assertEqual(measures.value(self.brain, {"kind": "at_most", "signal": "sent_back"}),
                         2.0)
        self.assertEqual(measures.value(self.brain, {"kind": "at_most",
                                                     "signal": "corrections"}), 1.0)

    def test_independent_evidence_counts_a_lineage_once(self):
        folder = tempfile.mkdtemp()
        try:
            brief = self.brain.context("Draft the webinar promo")
            session = brief.text.split("session_id: ")[1].split(" ")[0]
            paths = []
            for name in ("a.md", "b.md"):
                path = os.path.join(folder, name)
                open(path, "w", encoding="utf-8").write(name)
                self.brain.record_output(path, title=name, session_id=session)
                paths.append(path)
            other = os.path.join(folder, "c.md")
            open(other, "w", encoding="utf-8").write("c")
            self.brain.record_output(other, title="c")
            found = loop.independent(self.brain, paths + [other])
            self.assertEqual((found["given"], found["independent"]), (3, 2))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_an_admin_decides_only_in_their_scope(self):
        config = os.path.join(self.vault, "brain.json")
        data = json.load(open(config, encoding="utf-8"))
        scopes = list((data.get("scopes") or {}).keys())
        dept = next((s for s in scopes if s.startswith("dept:")), None)
        if dept is None:
            self.skipTest("this demo Brain has no department scope")
        data["admins"] = {dept: ["person:helper"]}
        json.dump(data, open(config, "w", encoding="utf-8"), indent=2)
        self.brain.close()
        self.brain = Brain(self.vault, embeddings=False)
        st = self.brain.state()
        self.assertEqual(governance.admins_of(st, dept), {"person:helper"})
        self.assertEqual(governance.admins_of(st, "company"), set())

    def test_twenty_briefs_replay_in_ten_seconds(self):
        target = self.note("Webinars run on Tuesdays at noon.", kind="fact", topic="webinars")
        for n in range(20):
            self.brain.context(f"When do webinars run? ({n})")
        made = self.brain.propose(area="marketing", topic="webinars",
                                  text="Webinars run on Thursdays at noon.", target_id=target,
                                  principal=self.owner, force_pending=True)
        self.assertFalse(made.is_error, made.text)
        began = time.monotonic()
        radius = self.brain.blast_radius(made.data["proposal_id"])
        self.assertFalse(radius.is_error, radius.text)
        self.assertLessEqual(time.monotonic() - began, 10.0)
        self.assertGreaterEqual(radius.data["briefs"], 1)

    def test_seeded_wrong_beliefs_are_found(self):
        """8 of 8 seeded wrong beliefs (older values a newer one replaced) reach the drift
        check within two cycles; between cycles the owner retires what the first found."""
        subjects = [
            ("The Austin plant tour takes {} minutes.", 20, 40, "austin-tour"),
            ("The Denver warehouse holds {} pallets.", 300, 450, "denver-warehouse"),
            ("Our newsletter list has {} subscribers.", 4000, 5200, "newsletter-list"),
            ("The supervisor workshop seats {} people.", 12, 16, "workshop-seats"),
            ("The trade show booth rental costs {} dollars.", 900, 1200, "booth-rental"),
            ("The webinar platform allows {} attendees.", 500, 1000, "webinar-platform"),
            ("The quarterly report runs {} pages.", 10, 14, "quarterly-report"),
            ("The onboarding call lasts {} minutes.", 30, 45, "onboarding-call"),
        ]
        olds = []
        for text, old, new, topic in subjects:
            olds.append(self.note(text.format(old), kind="fact", topic=topic,
                                  extra={"as_of": "2026-01-01"}))
            self.note(text.format(new), kind="fact", topic=topic,
                      extra={"as_of": "2026-09-01"})
        found = set()
        for _cycle in range(2):
            ids = {i for c in agent.gather(self.brain, "check-drift")["candidates"]
                   for i in c["ids"]}
            found |= ids
            for old in olds:
                if old in ids and self.brain.state().index.note(old) is not None:
                    governance.archive(self.brain, old, reason="A newer value replaced it.",
                                       actor=self.owner)
        self.assertEqual(sum(1 for o in olds if o in found), 8)


class ReviewDueTest(unittest.TestCase):
    def test_the_quarterly_review_waits_a_quarter_even_for_a_new_brain(self):
        import datetime as dt
        today = dt.date(2026, 10, 10)
        self.assertFalse(loop.review_due("", today=today))
        self.assertFalse(loop.review_due("", since="2026-09-30T10:00:00Z", today=today))
        self.assertTrue(loop.review_due("", since="2026-06-01T10:00:00Z", today=today))
        self.assertFalse(loop.review_due("2026-09-01T10:00:00Z", since="2026-01-01",
                                         today=today))
        self.assertTrue(loop.review_due("2026-07-01T10:00:00Z", today=today))


if __name__ == "__main__":
    unittest.main()
