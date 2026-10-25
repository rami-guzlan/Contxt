"""The State tier (brain-logic plan 8) and its gates (8.9): sheets from templates, typed cells
with their history, who may write what, computed columns against a reference, the brief's
"Current state" for named rows, staleness, sealed partitions, working contexts."""
from __future__ import annotations

import datetime as dt
import os
import shutil
import unittest
from unittest import mock

from brainkit import formulas, governance, sheetstore, state, util
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")
# The Brain's clock, pinned: midday UTC is the same date in nearly every time zone, and a run
# that crosses midnight (CI once did, between collecting these tests and running them) still
# counts days from one today.
NOW = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)
TODAY = util.local(NOW).date()


def days(n: int) -> str:
    return (TODAY + dt.timedelta(days=n)).isoformat()


class StateTest(unittest.TestCase):
    def setUp(self):
        clock = mock.patch.object(util, "now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)
        self.owner = self.brain.state().config.owner
        made = self.brain.state_act("create_sheet", {"template": "accounts"})
        self.assertFalse(made.is_error, made.text)
        for key, values, aliases in (
                ("Northwind", {"Health": "green", "Renewal date": days(23), "Value": "12000",
                               "Stage": "active"}, ["NW"]),
                ("Contoso", {"Health": "red", "Renewal date": days(90), "Value": "8000",
                             "Stage": "renewing"}, []),
                ("Fabrikam", {"Health": "amber", "Stage": "prospect"}, [])):
            done = self.brain.state_act("add_row", {"sheet": "accounts", "key": key,
                                                    "values": values, "aliases": aliases})
            self.assertFalse(done.is_error, done.text)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def row(self, key):
        return next(r for r in state.rows(self.brain, "accounts") if r.key == key)

    def test_a_sheet_from_a_template_keeps_typed_values_and_their_history(self):
        sheet = state.sheet(self.brain, "accounts")
        self.assertEqual(sheet.key, "Account")
        north = self.row("Northwind")
        self.assertEqual(north.value("Value"), 12000)
        self.assertEqual(north.computed["Days until renewal"], 23)
        bad = self.brain.state_act("write", {"sheet": "accounts", "row": "Northwind",
                                             "values": {"Renewal date": "next spring",
                                                        "Health": "purple"}})
        self.assertTrue(bad.is_error)
        self.assertIn("is a date", bad.text)
        self.assertIn("one of green, amber, red", bad.text)
        self.brain.state_act("write", {"sheet": "accounts", "row": "NW",
                                       "values": {"Health": "amber"}})
        history = state.history(self.brain, "accounts", north.id, "Health")
        self.assertEqual([e["value"] for e in history], ["amber", "green"])
        by_alias = state.history(self.brain, "accounts", "NW", "Health")
        self.assertEqual([e["value"] for e in by_alias], ["amber", "green"])
        snapshot = open(os.path.join(self.vault, "state", "accounts", "SNAPSHOT.md"),
                        encoding="utf-8").read()
        self.assertIn("| Northwind |", snapshot)
        summary = state.summary(state.sheet(self.brain, "accounts"),
                                state.rows(self.brain, "accounts"))
        self.assertEqual(summary["columns"]["Value"]["sum"], 20000)
        self.assertEqual(summary["columns"]["Health"]["by_status"],
                         {"amber": 2, "red": 1})

    def test_an_ai_writes_free_columns_waits_on_confirm_and_never_on_locked(self):
        self.brain.state_act("add_column", {"sheet": "accounts", "column": {
            "name": "Contract owner", "friction": "confirm"}})
        self.brain.state_act("add_column", {"sheet": "accounts", "column": {
            "name": "Discount", "type": "number", "friction": "locked"}})
        done = self.brain.update_state([
            {"sheet": "accounts", "row": "Northwind", "column": "Next step",
             "value": "Send the renewal deck"},
            {"sheet": "accounts", "row": "Northwind", "column": "Contract owner",
             "value": "Dana"},
            {"sheet": "accounts", "row": "Northwind", "column": "Discount", "value": "10"}],
            evidence="the Tuesday call")
        self.assertIn("1 written, 1 wait for the owner", done.text)
        self.assertIn("an AI cannot change it", done.text)
        north = self.row("Northwind")
        self.assertTrue(north.cells["Next step"].ai)
        self.assertNotIn("Contract owner", north.cells)
        waiting = state.waiting(self.brain)
        self.assertEqual([w["column"] for w in waiting], ["Contract owner"])
        self.brain.state_act("decide", {"sheet": "accounts", "row": "Northwind",
                                        "event": waiting[0]["event"], "accept": True})
        self.assertEqual(self.row("Northwind").value("Contract owner"), "Dana")
        self.brain.state_act("touch", {"sheet": "accounts", "row": "Northwind",
                                       "column": "Next step"})
        self.assertFalse(self.row("Northwind").cells["Next step"].ai)
        computed = self.brain.update_state([{"sheet": "accounts", "row": "Northwind",
                                             "column": "Days until renewal", "value": "5"}])
        self.assertIn("computed", computed.text)

    def test_under_regulated_every_ai_write_waits(self):
        governance.set_policies(self.brain, {"preset": "regulated"}, reason="test",
                                actor=self.owner)
        done = self.brain.update_state([{"sheet": "accounts", "row": "Contoso",
                                         "column": "Next step", "value": "Call legal"}])
        self.assertIn("wait for the owner", done.text)
        self.assertNotIn("Next step", self.row("Contoso").cells)

    def test_a_named_row_reaches_the_brief_dated_and_small(self):
        brief = self.brain.context("Where do we stand with Northwind before the renewal?",
                                   record=False).text
        self.assertIn("## Current state", brief)
        self.assertIn("**Accounts: Northwind**", brief)
        self.assertIn("Days until renewal: 23 (computed", brief)
        self.assertNotIn("Contoso", brief.split("## Current state")[1])
        block, _ = state.brief_block(self.brain, "Northwind")
        self.assertLessEqual(len(block.split("**Accounts: Northwind**")[1]) // 4, 300)
        named = ["Northwind", "NW", "Contoso", "Fabrikam", "contoso"]
        found = [bool(state.named_rows(self.brain, f"what about {n} this week")) for n in named]
        self.assertEqual(found, [True] * 5)  # rows retrieved for named entities: 100%
        self.assertEqual(state.named_rows(self.brain, "how is the website going"), [])

    def test_seeded_stale_cells_are_flagged(self):
        self.brain.state_act("write", {"sheet": "accounts", "row": "Contoso",
                                       "values": {"Health": "amber"}, "as_of": days(-60)})
        self.brain.state_act("write", {"sheet": "accounts", "row": "Fabrikam",
                                       "values": {"Next step": "Demo"}, "as_of": days(-20)})
        stale = {(r.key, c) for r in state.rows(self.brain, "accounts")
                 for c, cell in r.cells.items() if cell.stale}
        self.assertEqual(stale, {("Contoso", "Health"), ("Fabrikam", "Next step")})
        block, _ = state.brief_block(self.brain, "Contoso")
        self.assertIn("may be out of date", block)

    def test_partitions_stay_sealed(self):
        made = self.brain.state_act("create_sheet", {
            "title": "Client contacts", "key": "Name", "partition_by": "Client",
            "columns": [{"name": "Name"}, {"name": "Client"}, {"name": "Role"}]})
        self.assertFalse(made.is_error, made.text)
        for name, client in (("Ana Ruiz", "acme"), ("Bo Lind", "globex")):
            self.brain.state_act("add_row", {"sheet": "client-contacts", "key": name,
                                             "values": {"Client": client}})
        seen = [r.key for r in state.rows(self.brain, "client-contacts", partitions=["acme"])]
        self.assertEqual(seen, ["Ana Ruiz"])
        block, _ = state.brief_block(self.brain, "Bo Lind and Ana Ruiz", partitions=["acme"])
        self.assertIn("Ana Ruiz", block)
        self.assertNotIn("Bo Lind", block.split("##")[1].split("\n", 1)[1])

    def test_a_working_context_carries_its_row_until_changed(self):
        first = self.brain.context("What should I prepare?", context="accounts/Contoso")
        self.assertIn("**Accounts: Contoso**", first.text)
        session = first.text.split("session_id: ")[1].split(" ")[0]
        later = self.brain.context("And the next step?", session_id=session)
        self.assertIn("**Accounts: Contoso**: unchanged since this conversation", later.text)
        self.brain.state_act("write", {"sheet": "accounts", "row": "Contoso",
                                       "values": {"Next step": "Call legal"}})
        changed = self.brain.context("Anything new?", session_id=session)
        self.assertIn("Call legal", changed.text)
        self.assertIn("changed since this conversation last saw it", changed.text)
        with self.brain.ledger._connect() as conn:
            conn.execute("UPDATE contexts SET last_used = ? WHERE name = ?",
                         (days(-20) + "T00:00:00Z", "accounts/Contoso"))
        again = self.brain.context("Back to it", context="accounts/Contoso")
        self.assertIn("20 days ago", again.text)
        unknown = self.brain.context("hello", context="no-such-thing", record=False)
        self.assertIn("No task, goal, project or State row", unknown.text)

    def test_settled_values_are_offered_as_notes(self):
        self.brain.state_act("write", {"sheet": "accounts", "row": "Fabrikam",
                                       "values": {"Owner": "Sam"}})
        with sheetstore._db(self.brain) as conn:  # the Owner value, written 200 days ago
            conn.execute("UPDATE events SET body = REPLACE(body, ?, ?) WHERE row = 'fabrikam'",
                         (TODAY.isoformat(), days(-200)))
        offers = [o for o in state.promotions(self.brain) if o["kind"] == "to_note"]
        self.assertTrue(any(o["row"] == "Fabrikam" and o["column"] == "Owner"
                            for o in offers))


class FormulaTest(unittest.TestCase):
    """Computed values match a reference calculation on a seeded set: 100%."""

    COLUMNS = ["Renewal date", "Health", "Value", "Owner", "Signed"]

    def run_one(self, formula, values, **row):
        tree, names = formulas.parse(formula, self.COLUMNS)
        return formulas.evaluate(tree, names, formulas.Row(values, **row),
                                 dt.date(2026, 10, 10))

    def test_the_reference_set(self):
        linked = [{"Points": "3"}, {"Points": "5"}, {"Points": ""}]
        cases = [
            ("[Renewal date] - TODAY()", {"Renewal date": "2026-11-02"}, 23),
            ("DAYS([Renewal date], [Signed])", {"Renewal date": "2026-11-02",
                                                "Signed": "2026-01-01"}, 305),
            ("ADD_DAYS([Signed], 30)", {"Signed": "2026-01-01"}, "2026-01-31"),
            ('IF(AND([Renewal date] - TODAY() < 30, [Health] = "red"), "At risk", "")',
             {"Renewal date": "2026-10-20", "Health": "Red"}, "At risk"),
            ('IF([Health] <> "red", "Fine", "At risk")', {"Health": "green"}, "Fine"),
            ("[Value] * 1.1", {"Value": "1000"}, 1100),
            ("ROUND([Value] / 3, 2)", {"Value": "1000"}, 333.33),
            ('COUNT("issues")', {}, 3),
            ('SUM("issues", "Points")', {}, 8),
            ('AVERAGE("issues", "Points")', {}, 4),
            ('MAX("issues", "Points")', {}, 5),
            ('AGE("Health")', {}, 12),
            ('LOOKUP([Owner], "Email")', {"Owner": "Dana"}, "dana@example.com"),
            ('JOIN([Owner], "owns it")', {"Owner": "Dana"}, "Dana owns it"),
            ("[Renewal date] - TODAY()", {}, None),
        ]
        for formula, values, expected in cases:
            got = self.run_one(formula, values, ages={"Health": 12},
                               linked=lambda sheet: linked if sheet == "issues" else [],
                               lookup=lambda ref, col: "dana@example.com"
                               if (ref, col) == ("Dana", "Email") else None)
            self.assertEqual(got, expected, formula)

    def test_anything_else_is_refused(self):
        for formula in ("__import__('os').system('x')", "[Value].__class__",
                        "open('x')", "[Nope] + 1", "lambda: 1", "[Value] ** 2",
                        "(1 for x in [Value])"):
            with self.assertRaises(formulas.FormulaError, msg=formula):
                formulas.parse(formula, self.COLUMNS)

    def test_a_formula_reads_in_plain_words(self):
        self.assertEqual(formulas.describe("[Renewal date] - TODAY()"),
                         "Renewal date minus today")


if __name__ == "__main__":
    unittest.main()
