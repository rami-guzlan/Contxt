"""The kernel compiled for a principal in layers (company, role, person), each with a budget;
the shared part written to AGENTS.md with CLAUDE.md importing it, and the person's layer never in
a shared file: it comes once per conversation, with the first brief or from Claude Code's
session-start hook, under the session id the hooks share. The prompt hook pushes a brief only
when the brain holds something new for the message.
"""
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import kernel as kernel_mod  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from brainkit.hooks import capture_prompt, session_start  # noqa: E402
from brainkit.vault import Vault  # noqa: E402
from tests import fixture  # noqa: E402

# A rule the design team keeps, and Alex's own way of working.
EXTRA = [
    fixture.note("rules-design-001", "rules", "design", "team:design",
                 "Every layout sits on the 12-column grid.", load="standing"),
    fixture.note("identity-alex-001", "identity", "identity", "person:alex",
                 "Alex wants answers that lead with the decision, details after.",
                 load="standing", startup_text="Lead with the decision; details after."),
]
SESSION = "5f0e7c1a-1111-4c2e-9a37-2f1d1c0e9b10"  # Claude Code's own id for a conversation


def build() -> str:
    vault = fixture.build()
    v = Vault(vault)
    levels = fixture.BRAIN["structure"]["scope_levels"]
    kinds = fixture.BRAIN["structure"]["partition_kinds"]
    for meta, body in EXTRA:
        v.write_note(v.note_path(meta, levels, kinds), dict(meta), body)
    return vault


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.vault = build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def compiled(self, principal="person:alex"):
        st = self.brain.state()
        return kernel_mod.compile(st.config, st.index, st.scopes, st.scopes.chain(principal))

    def test_the_layers_follow_the_scope_chain(self):
        found = self.compiled()
        layers = {layer.name: layer for layer in found.layers}
        self.assertEqual((layers["company"].scopes, layers["role"].scopes,
                          layers["person"].scopes),
                         (("company",), ("team:design",), ("person:alex",)))
        self.assertIn("Never send anything to a client without Alex's approval.", found.shared)
        self.assertIn("12-column grid", found.shared)  # a team's layer is shared with it
        self.assertNotIn("Lead with the decision", found.shared)  # a person's is not
        self.assertIn("Lead with the decision", found.person)
        self.assertNotIn("person:alex", found.shared)
        self.assertNotIn("## Skills", found.shared)  # the brief names the skill that fits
        self.assertIn(f"startup_fingerprint: {found.fingerprint}", found.shared)
        self.assertLessEqual(found.tokens, found.budget)
        self.assertEqual(found.over_budget(), [])
        # Someone with no team and no standing notes of their own has a company layer only.
        sam = self.compiled("person:sam")
        self.assertEqual((sam.person, [layer.tokens for layer in sam.layers][1:]), ("", [0, 0]))

    def test_each_layer_has_a_budget_the_health_check_watches(self):
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            shape = json.load(handle)
        shape["kernel"]["budgets"] = {"company": 20, "person": 5}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(shape, handle)
        self.brain.close()
        self.brain = Brain(self.vault, embeddings=False)
        over = self.compiled().over_budget()
        self.assertTrue(any(line.startswith("company layer") for line in over), over)
        self.assertTrue(any(line.startswith("person layer") for line in over), over)
        health = self.brain.health().text
        self.assertIn("kernel over its target", health)

    def test_startup_files_hold_one_shared_copy_and_never_the_persons_layer(self):
        self.brain.write_kernel()
        root = self.brain.repo_root
        with open(os.path.join(root, "CLAUDE.md"), encoding="utf-8") as handle:
            claude = handle.read()
        with open(os.path.join(root, "AGENTS.md"), encoding="utf-8") as handle:
            agents = handle.read()
        self.assertIn("@AGENTS.md", claude)  # Claude Code imports the shared kernel
        self.assertNotIn("Never send anything", claude)
        self.assertIn("Never send anything", agents)
        self.assertNotIn("Lead with the decision", claude + agents)
        self.assertEqual(kernel_mod.file_fingerprint(root), self.compiled().fingerprint)

    def test_the_first_brief_brings_the_persons_layer_once(self):
        shared = self.compiled().fingerprint
        first = self.brain.context("What services do we offer?", startup_fingerprint=shared)
        self.assertEqual((first.data["kernel_included"], first.data["person_included"]),
                         (False, True))
        self.assertIn("# Startup context, your own layer", first.text)
        self.assertIn("Lead with the decision", first.text)
        session = first.data["session_id"]
        later = self.brain.context("And the pricing bands?", session_id=session,
                                   startup_fingerprint=shared)
        self.assertFalse(later.data["person_included"])
        self.assertNotIn("Lead with the decision", later.text)
        # After a compaction the conversation holds nothing it got before.
        again = self.brain.context("The pricing bands again", session_id=session,
                                   startup_fingerprint=shared, fresh=True)
        self.assertTrue(again.data["person_included"])
        after = self.brain.context("And the timelines?", session_id=session,
                                   startup_fingerprint=shared)
        self.assertFalse(after.data["person_included"])
        held = self.brain.ledger.delivered(session)
        self.assertEqual(sum(1 for kind, _item in held if kind == "kernel-person"), 1)

    def test_a_stale_startup_file_gets_the_whole_kernel(self):
        res = self.brain.context("What services do we offer?", startup_fingerprint="0000")
        self.assertTrue(res.data["kernel_included"])
        self.assertIn("# Startup context (kernel", res.text)
        self.assertIn("Lead with the decision", res.text)
        self.assertIn("12-column grid", res.text)

    def test_a_model_without_tools_gets_every_layer_and_no_contract(self):
        text = self.brain.kernel(principal="person:alex", tools=False).text
        self.assertIn("Lead with the decision", text)
        self.assertIn("12-column grid", text)
        self.assertNotIn("gnomon_get_context", text)


class HookTests(unittest.TestCase):
    """Claude Code's hooks, run in this process against a vault named by BRAIN_VAULT."""

    def setUp(self):
        self.vault = build()
        env = {"BRAIN_VAULT": self.vault, "BRAIN_EMBEDDINGS": "0", "BRAIN_PRINCIPAL": "",
               "BRAIN_HOOK_PUSH": "1", "BRAIN_HOOK_ASK": "1"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.brain = Brain(self.vault, embeddings=False)
        self.brain.write_kernel()

    def tearDown(self):
        self.brain.close()
        self.env.stop()
        fixture.remove(self.vault)

    def run_hook(self, module, payload) -> str:
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(out):
            module.main()
        return out.getvalue()

    def prompt(self, text, session=SESSION) -> str:
        out = self.run_hook(capture_prompt, {"prompt": text, "session_id": session})
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_session_start_names_the_session_and_brings_the_persons_layer_once(self):
        first = self.run_hook(session_start, {"session_id": SESSION, "source": "startup"})
        self.assertIn("Lead with the decision", first)
        self.assertIn(f"Brain session_id: cc:{SESSION}", first)
        resumed = self.run_hook(session_start, {"session_id": SESSION, "source": "resume"})
        self.assertNotIn("Lead with the decision", resumed)  # the conversation still has it
        compacted = self.run_hook(session_start, {"session_id": SESSION, "source": "compact"})
        self.assertIn("Lead with the decision", compacted)
        # The model's own brief under that session does not send the layer again.
        shared = kernel_mod.file_fingerprint(self.brain.repo_root)
        brief = self.brain.context("What services do we offer?", session_id=f"cc:{SESSION}",
                                   startup_fingerprint=shared)
        self.assertFalse(brief.data["person_included"])

    def test_the_prompt_hook_pushes_a_brief_only_when_something_is_new(self):
        self.run_hook(session_start, {"session_id": SESSION, "source": "startup"})
        pushed = self.prompt("How should headlines be written for the studio?")
        self.assertIn(f"sent before you start under session_id cc:{SESSION}", pushed)
        self.assertIn("# Task context", pushed)
        self.assertIn("sentence case", pushed)
        logged = self.brain.ledger.requests(limit=1)[0]
        self.assertEqual((logged["session_id"], logged["data"]["delivery"]),
                         (f"cc:{SESSION}", "push"))
        # The model asks too, with the session id: nothing pushed is sent twice.
        shared = kernel_mod.file_fingerprint(self.brain.repo_root)
        pulled = self.brain.context("How should headlines be written for the studio?",
                                    session_id=f"cc:{SESSION}", startup_fingerprint=shared)
        self.assertEqual(pulled.data["note_ids"], [])
        # The same ask again holds nothing new: no push, the reminder instead.
        again = self.prompt("How should headlines be written for the studio?")
        self.assertNotIn("# Task context", again)
        self.assertIn("call gnomon_get_context", again)

    def test_push_can_be_turned_off(self):
        with mock.patch.dict(os.environ, {"BRAIN_HOOK_PUSH": "0"}):
            quiet = self.prompt("How should headlines be written for the studio?")
        self.assertNotIn("# Task context", quiet)
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            shape = json.load(handle)
        shape["hooks"] = {"push": "off"}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(shape, handle)
        self.assertNotIn("# Task context", self.prompt("How should headlines be written?"))
        # Without Claude Code's session id there is nothing to push under.
        shape["hooks"] = {"push": "words"}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(shape, handle)
        out = self.run_hook(capture_prompt, {"prompt": "How should headlines be written?"})
        self.assertNotIn("# Task context", out)


if __name__ == "__main__":
    unittest.main()
