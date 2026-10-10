"""Measuring the brain (brain-logic plan, phase 0): what context costs on each line, the request
type of every brief, the replay of a logged brief against another brain state, and the owner's
private eval set of labeled real requests.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import costs, evalset, replay, report  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from tests import test_layout  # noqa: E402


def _assistant(message_id, at, *, model="claude-opus-5-5", tools=(), cache_1h=False,
               usage=None):
    usage = dict(usage or {"input_tokens": 10, "output_tokens": 50,
                           "cache_read_input_tokens": 9000,
                           "cache_creation_input_tokens": 300})
    if cache_1h:
        usage["cache_creation"] = {"ephemeral_1h_input_tokens": usage[
            "cache_creation_input_tokens"], "ephemeral_5m_input_tokens": 0}
    content = [{"type": "tool_use", "id": tid, "name": name, "input": {}}
               for tid, name in tools] or [{"type": "text", "text": "ok"}]
    return {"type": "assistant", "timestamp": at, "isSidechain": False,
            "cwd": "C:/elsewhere", "message": {"id": message_id, "model": model,
                                               "content": content, "usage": usage}}


def _result(tool_id, text, at):
    return {"type": "user", "timestamp": at, "isSidechain": False, "message": {
        "role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id,
                                     "content": [{"type": "text", "text": text}]}]}}


class PriceTests(unittest.TestCase):
    def test_the_longest_known_model_id_sets_the_price(self):
        self.assertEqual(costs.price_for("claude-opus-5-5").input, 4.0)
        self.assertEqual(costs.price_for("claude-opus-5").input, 5.0)
        self.assertEqual(costs.price_for("claude-fable-5-1[1m]").cache_read, 0.25)
        self.assertEqual(costs.price_for("ollama:qwen3:1.7b"), costs.FREE)
        self.assertIsNone(costs.price_for("some-other-model"))

    def test_a_call_costs_its_tokens_at_their_rates(self):
        # 1M in at $4, 100k out at $20, 2M cache reads at $0.20, 100k written at $5 (5 min).
        self.assertAlmostEqual(costs.call_cost("claude-opus-5-5", 1_000_000, 100_000,
                                               2_000_000, 100_000), 4 + 2 + 0.4 + 0.5)
        self.assertEqual(costs.call_cost("unknown", 1000, 1000), 0.0)


class LedgerAndTypeTests(unittest.TestCase):
    def setUp(self):
        self.vault = test_layout.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_background_calls_are_kept_by_day_with_their_cost(self):
        ledger = self.brain.ledger
        ledger.record_model_call("check", "claude-opus-5-5", tokens_in=1000, tokens_out=200)
        ledger.record_model_call("check", "claude-opus-5-5", tokens_in=1000, tokens_out=200,
                                 cost=0.5)
        ledger.record_model_call("agent", "ollama:qwen3:1.7b", tokens_in=5000, tokens_out=300)
        rows = {r["job"]: r for r in ledger.model_usage("2000-01-01")}
        self.assertEqual(rows["check"]["calls"], 2)
        self.assertAlmostEqual(rows["check"]["cost"], 0.5 + (1000 * 4 + 200 * 20) / 1e6)
        self.assertEqual(rows["agent"]["cost"], 0.0)

    def test_every_brief_says_what_kind_of_request_it_answered(self):
        kinds = {}
        for request in ("How much is the rye loaf?",
                        "Write an Instagram caption for the seeded loaf",
                        "Should we raise cake deposits or keep them? Compare the options",
                        "Fix the bug in the order form script"):
            res = self.brain.context(request, principal="person:ana")
            kinds[request] = res.data.get("request_type")
        self.assertEqual(kinds["How much is the rye loaf?"], "lookup")
        self.assertEqual(kinds["Write an Instagram caption for the seeded loaf"], "writing")
        self.assertEqual(kinds["Should we raise cake deposits or keep them? Compare the options"],
                         "planning")
        self.assertEqual(kinds["Fix the bug in the order form script"], "code")
        self.assertIn("note_tokens", res.data)

    def test_the_report_counts_briefs_and_jobs_by_day(self):
        self.brain.context("Write an Instagram caption for the seeded loaf",
                           principal="person:ana")
        self.brain.ledger.record_model_call("check", "claude-opus-5-5", tokens_in=1000,
                                            tokens_out=100)
        found = report.card(self.brain, days=2, quality=False)
        today = found["spend"]["days"][-1]
        self.assertEqual(today["packets"], 1)
        self.assertGreater(today["lines"]["briefs"]["tokens"], 0)
        self.assertEqual(today["sources"]["rereads"], "estimated")
        self.assertGreater(today["lines"]["jobs"]["usd"], 0)
        text = report.render(found)
        self.assertIn("not calibrated", text)
        self.assertIn("writing", text)

    def test_calibration_multiplies_every_estimate(self):
        detail = costs.set_factor(self.brain.ledger, [(100, 120), (300, 360)],
                                  method="claude code")
        self.assertEqual(detail["factor"], 1.2)
        self.assertEqual(costs.factor(self.brain.ledger), 1.2)
        self.assertTrue(costs.calibration(self.brain.ledger)["measured"])
        with self.assertRaises(ValueError):
            costs.set_factor(self.brain.ledger, [(0, 5)], method="x")


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="brain-transcripts-")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def write(self, name, entries):
        project = os.path.join(self.folder, "C--work-project")
        os.makedirs(project, exist_ok=True)
        with open(os.path.join(project, name), "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")

    def test_brain_answers_are_written_once_reread_after_and_rewritten_after_a_pause(self):
        brief = "x" * 4000  # 1,000 estimated tokens
        self.write("a.jsonl", [
            _assistant("m1", "2026-10-09T10:00:00Z",
                       tools=[("t1", "mcp__contxt__get_task_context")]),
            _result("t1", brief, "2026-10-09T10:00:01Z"),
            _assistant("m2", "2026-10-09T10:00:05Z"),   # writes the brief
            _assistant("m2", "2026-10-09T10:00:05Z"),   # same API call, another block
            _assistant("m3", "2026-10-09T10:01:00Z"),   # re-reads it
            _assistant("m4", "2026-10-09T10:20:00Z"),   # after a pause: rewrites it
            {"type": "system", "subtype": "compact_boundary",
             "timestamp": "2026-10-09T10:30:00Z", "isSidechain": False},
            _assistant("m5", "2026-10-09T10:31:00Z"),   # nothing held after compaction
        ])
        self.write("b.jsonl", [_assistant("n1", "2026-10-09T11:00:00Z")])  # no brain at all
        found = costs.claude_code(self.folder, "2026-10-09", fixed_tokens=100)
        self.assertEqual(found["sessions"], 1)
        day = found["days"]["2026-10-09"]
        self.assertEqual(day["briefs"], 1)
        self.assertEqual(day["lines"]["briefs"]["tokens"], 1000)
        self.assertEqual(day["lines"]["rereads"]["tokens"], 1000)        # m3 only
        self.assertEqual(day["lines"]["rewrites"]["tokens"], 1100)       # m4: brief + fixed
        self.assertEqual(day["calls"], 3)                                # m2, m3, m4
        self.assertEqual(found["later_calls"], [2])
        price = costs.price_for("claude-opus-5-5")
        self.assertAlmostEqual(day["lines"]["rereads"]["usd"], 1000 * price.cache_read / 1e6,
                               places=6)

    def test_an_hour_long_cache_is_only_rewritten_after_an_hour(self):
        self.write("c.jsonl", [
            _assistant("m1", "2026-10-09T10:00:00Z", cache_1h=True,
                       tools=[("t1", "mcp__brain__get_task_context")]),
            _result("t1", "y" * 400, "2026-10-09T10:00:01Z"),
            _assistant("m2", "2026-10-09T10:00:05Z", cache_1h=True),
            _assistant("m3", "2026-10-09T10:20:00Z", cache_1h=True),   # 20 minutes: re-read
            _assistant("m4", "2026-10-09T11:30:00Z", cache_1h=True),   # 70 minutes: rewrite
        ])
        day = costs.claude_code(self.folder, "2026-10-09")["days"]["2026-10-09"]
        self.assertEqual(day["lines"]["rereads"]["tokens"], 100)
        self.assertEqual(day["lines"]["rewrites"]["tokens"], 100)


class ReplayAndEvalTests(unittest.TestCase):
    def setUp(self):
        self.vault = test_layout.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def ask(self, request):
        return self.brain.context(request, principal="person:ana")

    def test_a_replay_against_the_same_brain_finds_nothing_changed(self):
        packet = self.ask("How much notice does a celebration cake need?").data["packet_id"]
        found = replay.replay(self.brain, packet)
        self.assertEqual((found["replayed"], found["changed"]), (1, 0))
        self.assertTrue(found["rows"][0]["diff"]["same"])

    def test_a_replay_with_a_proposal_shows_what_it_would_bring_in(self):
        packet = self.ask("How much notice does a celebration cake need?").data["packet_id"]
        proposed = self.brain.propose(area="company", topic="menu", title="Cake notice in June",
                                      text="In June, celebration cakes need ten days of notice "
                                           "because of weddings.", principal="person:ana",
                                      evidence="Ana said so", note_kind="fact")
        proposal = proposed.data.get("proposal_id")
        self.assertTrue(proposal, proposed.text)
        found = replay.replay(self.brain, packet, proposal=proposal)
        row = found["rows"][0]
        brought = [i for i in row["diff"]["notes"]["entered"] + row["after"]["related"]
                   if i.startswith("cake-notice")]
        self.assertTrue(brought, row)
        self.assertEqual(found["against"], f"with {proposal}")
        # The live brain is untouched: the proposal still waits.
        self.assertIsNone(self.brain.state().index.note(brought[0]))

    def test_the_owner_labels_real_requests_and_the_set_scores_them(self):
        for request in ("How much notice does a celebration cake need?",
                        "What do we post on Instagram and when?",
                        "When was the bakery founded?"):
            self.ask(request)
        added = evalset.sample(self.brain, 10)
        self.assertEqual(added["added"], 3)
        self.assertEqual(evalset.sample(self.brain, 10)["added"], 0)   # no repeats
        case = next(c for c in evalset.load(self.brain)["cases"]
                    if "cake" in c["request"])
        labeled = evalset.label(self.brain, case["id"], needed=["celebration-cakes"],
                                noise=["instagram-rhythm"])
        self.assertTrue(labeled["labeled"])
        self.assertEqual(labeled["must"], [["celebration-cakes"]])
        with self.assertRaises(ValueError):
            evalset.label(self.brain, case["id"], needed=["no-such-note"])
        result = evalset.run(self.brain)
        self.assertEqual(result["all"]["cases"], 1)
        self.assertEqual(result["all"]["must_recall"], 1.0)
        status = evalset.status(self.brain)
        self.assertEqual((status["cases"], status["labeled"]), (3, 1))
        self.assertTrue(status["path"].startswith(self.brain.vault.runtime_dir))
        # The run used a throwaway ledger and gave the brain its own back.
        self.assertEqual(len(self.brain.ledger.packet_rows("2000-01-01")), 3)


if __name__ == "__main__":
    unittest.main()
