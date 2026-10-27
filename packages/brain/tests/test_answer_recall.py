"""The answer-recall eval (v4 backend plan, 16.4): what reached the AI by the end of its
answer, from its packets plus what it fetched, scored by code from a headless transcript."""
from __future__ import annotations

import json
import unittest

from brainkit import answer_recall as ar
from brainkit.api import Brain
from tests import fixture


def _use(call_id, tool, args):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": call_id, "name": f"mcp__contxt__{tool}", "input": args}]}})


def _result(call_id, text="ok", error=False):
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": text,
         "is_error": error}]}})


def _done(answer="Done.", cost=0.004):
    return json.dumps({"type": "result", "result": answer, "total_cost_usd": cost,
                       "usage": {"input_tokens": 100, "cache_read_input_tokens": 900,
                                 "output_tokens": 50}})


class ParseTest(unittest.TestCase):
    def test_context_requests_fetches_and_pointers(self):
        lines = [
            _use("1", "gnomon_get_context", {"request": "Draft the reminder"}), _result("1"),
            _use("2", "notes", {"action": "search", "query": "office phone"}), _result("2"),
            _use("3", "notes", {"action": "get", "id": "office-phone"}), _result("3"),
            _use("4", "gnomon", {"action": "open", "address": "hours#weekends"}), _result("4"),
            _use("5", "notes", {"action": "get", "id": "gone"}), _result("5", error=True),
            _done(),
        ]
        s = ar.parse(lines)
        self.assertEqual(s.requests, ["Draft the reminder"])
        self.assertEqual(s.fetched, {"office-phone", "hours"})  # the failed get is not
        self.assertEqual(s.fetches, 4)
        self.assertEqual(s.searches, ["office phone"])
        self.assertEqual(s.tokens, 1050)
        self.assertAlmostEqual(s.cost, 0.004)


class ScoreTest(unittest.TestCase):
    case = {"id": "c1", "must": [["office-phone"], ["hours", "hours-old"]],
            "must_holds": ["privacy"]}

    def test_a_needed_item_reached_by_a_fetch_counts(self):
        row = ar.score(self.case, packet={"hours"}, fetched={"office-phone"},
                       must_holds={"privacy", "premed"}, fetches=1, tokens=10, cost=0.0)
        self.assertEqual((row["packet_hits"], row["answer_hits"], row["needed"]), (1, 2, 2))
        self.assertTrue(row["complete"])

    def test_a_search_hit_alone_does_not(self):
        row = ar.score(self.case, packet={"hours"}, fetched=set(),
                       must_holds={"privacy"}, fetches=1, tokens=10, cost=0.0)
        self.assertEqual(row["answer_hits"], 1)
        self.assertFalse(row["complete"])
        self.assertEqual(row["missed"], [["office-phone"]])

    def test_a_must_hold_not_labeled_for_the_request_is_wrong(self):
        row = ar.score(self.case, packet={"hours", "privacy", "premed"},
                       fetched={"office-phone"}, must_holds={"privacy", "premed"},
                       fetches=0, tokens=10, cost=0.0)
        self.assertEqual(row["wrong_must_holds"], ["premed"])
        self.assertEqual(row["must_hold_chances"], 1)


class SummaryTest(unittest.TestCase):
    def test_aggregate_and_worst_brain(self):
        def row(complete, fetches, wrong=()):
            return {"needed": 1, "packet_hits": 0, "answer_hits": int(complete),
                    "complete": complete, "fetches": fetches, "tokens": 100,
                    "cost": 0.01, "wrong_must_holds": list(wrong), "must_hold_chances": 2,
                    "error": ""}
        brains = [{"name": "a", "rows": [row(True, 1), row(True, 0)]},
                  {"name": "b", "rows": [row(False, 2, ["x"]), row(True, 1)]}]
        out = ar.summary(brains)
        self.assertEqual(out["all"]["answer_recall"], [3, 4])
        self.assertEqual(out["all"]["complete"], [3, 4])
        self.assertEqual(out["all"]["fetches_per_answer"], 1.0)
        self.assertEqual(out["all"]["wrong_must_hold_cases"], [1, 4])
        self.assertEqual(out["worst"]["answer_recall"], ["b", 0.5])


class PacketTest(unittest.TestCase):
    def test_the_packet_is_what_the_brain_delivers_for_the_ais_own_request(self):
        vault = fixture.build()
        brain = Brain(vault, embeddings=False)
        try:
            got = ar.packet(brain, "How long do web projects take?")
            direct = brain.context("How long do web projects take?", record=False).data
            pointers = set(direct.get("pointer_ids") or [])
            self.assertTrue(set(direct.get("note_ids") or []) - pointers <= got)
            self.assertFalse(set(direct.get("pointer_ids") or []) & got
                             - set(direct.get("must_hold_ids") or []))
        finally:
            brain.close()
            fixture.remove(vault)


if __name__ == "__main__":
    unittest.main()
