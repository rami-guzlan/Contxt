"""The hooks that keep a run the app starts on its contract: scope and budget before each tool
call, the contract back as the run goes, and a finishing check before it stops."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit.hooks import run as hooks

FINISH = "Finish with complete_task, or a blocker."


class RunHookTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="run-hooks-")
        self.work = os.path.join(self.folder, "work")
        os.makedirs(self.work)
        self.contract = {
            "objective": "Draft the launch notes",
            "checks": ["Claim the task first.", FINISH],
            "finish": [{"check": FINISH, "any": ["complete_task", "append_task_event"]}],
            "must_holds": [{"id": "family-ollie", "line": "Ollie is allergic to peanuts.",
                            "triggers": ["dinner", "peanut"]}],
            "scope": {"folder": self.work, "tools": ["Read", "Write"]},
            "budget": {"steps": 3, "minutes": 20},
            "every": 2,
            "events": os.path.join(self.folder, "run-events.jsonl"),
            "state": os.path.join(self.folder, "run-state.json"),
        }

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def events(self):
        with open(self.contract["events"], encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def call(self, tool, **arguments):
        return hooks.scope(self.contract, {"tool_name": tool, "tool_input": arguments})

    def test_a_file_outside_the_runs_folder_and_a_guarded_command_are_refused(self):
        self.assertIsNone(self.call("Write", file_path=os.path.join(self.work, "notes.md")))
        self.assertIsNone(self.call("Read", file_path="notes.md"))  # relative: inside
        refused = self.call("Read", file_path=os.path.join(self.folder, "contract.json"))
        decision = refused["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("outside this run's folder", decision["permissionDecisionReason"])
        self.assertEqual(self.events()[-1]["event"], "blocked")

    def test_past_its_budget_a_run_may_only_finish(self):
        for _ in range(3):
            self.assertIsNone(self.call("mcp__contxt-app__search_context", query="x"))
        refused = self.call("mcp__contxt-app__search_context", query="x")
        self.assertIn("budget of 3 tool calls", refused["hookSpecificOutput"][
            "permissionDecisionReason"])
        self.assertIsNone(self.call("mcp__contxt-app__complete_task", summary="Done."))

    def test_the_contract_comes_back_on_its_cadence_and_a_must_hold_at_once(self):
        self.call("Read", file_path="a.md")
        found = hooks.anchor(self.contract, {"tool_name": "Read",
                                             "tool_input": {"file_path": "a.md"},
                                             "tool_response": "Plan Tuesday dinner."})
        context = found["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Must hold here (dinner): Ollie is allergic to peanuts.", context)
        self.assertNotIn("Run contract", context)
        self.call("Read", file_path="b.md")
        found = hooks.anchor(self.contract, {"tool_name": "Read", "tool_response": "Lunch."})
        context = found["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Run contract, after 2 tool calls: Draft the launch notes", context)
        self.assertIn("- Must hold: Ollie is allergic to peanuts.", context)
        self.assertEqual([e["why"] for e in self.events()], ["must-hold family-ollie", "cadence"])

    def test_a_run_that_never_finished_is_sent_back_once(self):
        self.call("mcp__contxt-app__claim_task", task_id="t1")
        back = hooks.gate(self.contract, {"stop_hook_active": False})
        self.assertEqual(back["decision"], "block")
        self.assertIn(FINISH, back["reason"])
        self.assertIsNone(hooks.gate(self.contract, {"stop_hook_active": True}))
        self.assertEqual(self.events()[-1], dict(self.events()[-1], event="gate", passed=False,
                                                 sent_back=False))
        self.call("mcp__contxt-app__complete_task", summary="Done.")
        self.assertIsNone(hooks.gate(self.contract, {"stop_hook_active": False}))
        self.assertTrue(self.events()[-1]["passed"])

    def test_without_a_contract_a_hook_does_nothing(self):
        self.assertEqual(hooks.main(["gate", "--contract", os.path.join(self.folder, "x")]), 0)


if __name__ == "__main__":
    unittest.main()
