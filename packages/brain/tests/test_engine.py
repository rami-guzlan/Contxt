"""The local retrieval engine (brain-logic plan 5.11), proved with stand-in models.

A real model service runs on 127.0.0.1 with a lock of its own (real checksums of stand-in model
files) and stand-in backends: a reranker and a decision model that answer from fixed tables. The
engine is driven end to end through `Brain.context`, so these show, without the real models:
the lock refusing what it does not list or what does not match; no count cap, only a ceiling;
the link loop's stop rule; pointers, never drops; must-holds that bypass the gate and the cut;
the one-line brief for a request that should get nothing; and every decision's scores in the
ledger. Without a verified service, retrieval falls back and the parity test (test_parity.py)
shows briefs unchanged.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import modellock, models_client, modelservice, safeguards_eval  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from brainkit.hooks import capture_prompt  # noqa: E402
from brainkit.vault import Vault  # noqa: E402
from tests import fixture  # noqa: E402

REPO = os.path.dirname(os.path.dirname(ROOT))
FILES = {"standin-reranker": b"a reranker that answers from a table",
         "standin-decider": b"a decision model that answers from a table"}


class TableReranker(modelservice.RerankBackend):
    """Scores each document by the id at its head (`[note-id] Title`), else a default."""

    def __init__(self, pin, folder, table=None, default=0.1, fail=False):
        super().__init__(pin, folder)
        self.table = dict(table or {})
        self.default = default
        self.fail = fail
        self.calls = []

    def scores(self, query, instruction, documents):
        if self.fail:
            raise RuntimeError("the stand-in reranker is broken on purpose")
        self.calls.append((query, instruction, len(documents)))
        out = []
        for doc in documents:
            found = re.match(r"\[([^\]]+)\]", doc)
            out.append(self.table.get(found.group(1) if found else "", self.default))
        return out


class TableDecider(modelservice.DecideBackend):
    """System One answers from a table: `noul` questions by id (default yes 0.9), `choice`
    questions by id naming the chosen option (default "none")."""

    def __init__(self, pin, folder, gate=0.9, table=None):
        super().__init__(pin, folder)
        self.gate = gate
        self.table = dict(table or {})
        self.asked = []

    def answers(self, state, questions):
        self.asked.append((state, dict(questions)))
        out = {}
        for name, question in questions.items():
            if question["type"] == "noul":
                p = self.gate if name == "gate" else self.table.get(name, 0.9)
                if name.startswith("domain."):
                    p = self.table.get(name, 0.1)
                out[name] = {"type": "noul", "noul": p}
            else:
                options = list(question["criteria"])
                chosen = self.table.get(name, "none")
                rest = (0.1 / (len(options) - 1)) if len(options) > 1 else 0.0
                probs = {o: (0.9 if o == chosen else rest) for o in options}
                out[name] = {"type": "choice", "choice": chosen, "probabilities": probs,
                             "confidence": 0.8}
        return out


def write_lock(folder: str, *, tamper: bool = False) -> str:
    """A lock with the two stand-ins pinned to the files written beside it."""
    models = []
    for name, data in FILES.items():
        target = os.path.join(folder, "models", name)
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "weights.bin"), "wb") as handle:
            handle.write(data + (b"!" if tamper and name == "standin-reranker" else b""))
        models.append({"name": name, "role": "rerank" if "reranker" in name else "decide",
                       "default": True, "repository": "", "revision": "1",
                       "files": {"weights.bin": hashlib.sha256(data).hexdigest()},
                       "dtype": "float32", "runtime": {}, "extra": {}})
    models.append({"name": "unpinned-model", "role": "rerank", "repository": "",
                   "revision": "", "files": {}})
    path = os.path.join(folder, "models.lock.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"models": models}, handle)
    return path


class Rig:
    """A model service with stand-ins, and the environment that points the engine at it."""

    def __init__(self, *, reranker=None, decider=None, choose=None, tamper=False):
        self.folder = tempfile.mkdtemp(prefix="brain-engine-")
        self.lock_path = write_lock(self.folder, tamper=tamper)
        self.lock = modellock.Lock.load(self.lock_path)
        self.reranker = reranker or TableReranker(None, "")
        self.decider = decider or TableDecider(None, "")

        def build(backend):
            def make(pin, folder):
                backend.pin, backend.folder = pin, folder
                return backend
            return make

        service = modelservice.ModelService(
            lock=self.lock, models_dir=os.path.join(self.folder, "models"),
            factories={"standin-reranker": build(self.reranker),
                       "standin-decider": build(self.decider)}, choose=choose)
        self.running = modelservice.start(service, 0, announce=False)
        self.env = mock.patch.dict(os.environ, {"BRAIN_MODEL_SERVICE": self.running.url,
                                                "BRAIN_MODELS_LOCK": self.lock_path})
        self.env.start()
        models_client.forget()

    def stop(self):
        self.env.stop()
        self.running.stop()
        models_client.forget()
        shutil.rmtree(self.folder, ignore_errors=True)


def extra_notes(vault: str, notes) -> None:
    v = Vault(vault)
    levels = fixture.BRAIN["structure"]["scope_levels"]
    kinds = fixture.BRAIN["structure"]["partition_kinds"]
    for meta, body in notes:
        v.write_note(v.note_path(meta, levels, kinds), dict(meta), body)


def set_engine(vault: str, **settings) -> None:
    path = os.path.join(vault, "brain.json")
    with open(path, encoding="utf-8") as handle:
        shape = json.load(handle)
    shape.setdefault("engine", {}).update(settings)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(shape, handle)


class LockTests(unittest.TestCase):
    def test_the_service_refuses_a_model_the_lock_does_not_list(self):
        rig = Rig(choose={"rerank": "a-model-nobody-pinned"})
        try:
            health = rig.running.service.health()
            self.assertFalse(health["roles"]["rerank"]["loaded"])
            self.assertIn("not in the model lock", health["roles"]["rerank"]["reason"])
            found = models_client.status(refresh=True)
            self.assertFalse(found.ready)
            self.assertIn("no verified model for rerank", found.reason)
        finally:
            rig.stop()

    def test_a_listed_model_whose_files_differ_is_refused(self):
        rig = Rig(tamper=True)
        try:
            row = rig.running.service.health()["roles"]["rerank"]
            self.assertEqual((row["verified"], row["loaded"]), (False, False))
            self.assertIn("does not match the lock", row["reason"])
            unpinned = rig.lock.verify("unpinned-model", rig.folder)
            self.assertIn("not pinned yet", unpinned.reason)
        finally:
            rig.stop()

    def test_a_service_on_another_lock_is_refused(self):
        rig = Rig()
        try:
            other = modellock.Lock({}, "")
            found = models_client.status(refresh=True, lock=other)
            self.assertFalse(found.ready)
            self.assertIn("refused", found.reason)
            self.assertTrue(models_client.status(refresh=True).ready)
        finally:
            rig.stop()

    def test_the_shipped_lock_pins_what_it_can_and_names_the_rest(self):
        lock = modellock.Lock.load(modellock.LOCK_PATH)
        self.assertTrue(lock.pin("bge-small-en-v1.5").pinned)
        self.assertEqual(lock.pin("kev-4b").revision, "139fdd94")
        self.assertFalse(lock.pin("qwen3-reranker-0.6b").pinned)  # pinned on the PC
        with self.assertRaises(modellock.Refused):
            lock.pin("laya")


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.rig = None

    def tearDown(self):
        if self.rig is not None:
            self.rig.stop()
        fixture.remove(self.vault)

    def brain(self, **rig):
        self.rig = Rig(**rig)
        return Brain(self.vault, embeddings=False)

    def test_without_a_service_retrieval_falls_back_and_writes_down_what_exists(self):
        with mock.patch.dict(os.environ, {"BRAIN_MODEL_SERVICE": "off"}):
            models_client.forget()
            brain = Brain(self.vault, embeddings=False)
            try:
                res = brain.context("How should headlines be written?")
                engine = res.data["engine"]
                self.assertEqual(engine["mode"], "fallback")
                self.assertIn("no model service", engine["reason"])
                rows = brain.ledger.decisions(res.data["packet_id"])
                self.assertTrue(rows)
                top = next(r for r in rows if r["item"] == "rules-style-002")
                self.assertEqual(top["outcome"], "body")
                self.assertIsNotNone(top["keyword"])
                self.assertIsNone(top["rerank"])  # no reranker ran
                self.assertTrue(all(r["outcome"] in ("body", "pointer", "listed", "held", "out")
                                    for r in rows))
                self.assertIn("fallback", brain.health().text)
            finally:
                brain.close()

    def test_every_decision_is_scored_and_kept(self):
        set_engine(self.vault, floor=0.0)  # every note the caller may see is a candidate
        brain = self.brain(reranker=TableReranker(None, "", {"rules-style-002": 0.95}))
        try:
            res = brain.context("How should headlines be written?")
            engine = res.data["engine"]
            self.assertEqual(engine["mode"], "on")
            self.assertEqual(engine["lock"], self.rig.lock.fingerprint)
            self.assertEqual(engine["gate"]["passed"], True)
            self.assertTrue({"gate", "find", "cut"} <= set(engine["timings"]))
            rows = brain.ledger.decisions(res.data["packet_id"])
            self.assertTrue(rows and all(r["rerank"] is not None for r in rows
                                         if r["found_by"] != "" and not r["reason"].startswith(
                                             "past the ceiling")))
            kept = next(r for r in rows if r["item"] == "rules-style-002")
            self.assertEqual(kept["outcome"], "body")
            self.assertIn("current", kept["kev"])
            out = [r for r in rows if r["outcome"] == "out"]
            self.assertTrue(out and all("below the relevance cut" in r["reason"] for r in out))
            self.assertEqual(res.data["note_ids"], ["rules-style-002"])
            self.assertIn("health", brain.health().text.lower())
            self.assertIn("retrieval engine: on", brain.health().text)
        finally:
            brain.close()

    def test_there_is_no_count_cap_only_a_ceiling_for_speed(self):
        notes = [fixture.note(f"facts-palette-{i:03d}", "facts", "services", "company",
                              f"Palette study {i}: brand palettes for small companies, "
                              f"swatch set {i}.") for i in range(60)]
        extra_notes(self.vault, notes)
        table = {meta["id"]: 0.9 for meta, _body in notes}
        brain = self.brain(reranker=TableReranker(None, "", table))
        try:
            res = brain.context("Which brand palettes did we study for small companies?")
            sent = set(res.data["note_ids"])
            self.assertEqual(len(sent & set(table)), 60)  # all of them, whole or as pointers
            self.assertGreater(len(res.data["pointer_ids"]), 0)  # past the budget: pointers
            self.assertFalse(res.data["engine"]["ceiling_hit"])
            set_engine(self.vault, ceiling=25)
            brain.close()
            brain = Brain(self.vault, embeddings=False)
            capped = brain.context("Which brand palettes did we study for small companies?")
            self.assertTrue(capped.data["engine"]["ceiling_hit"])
            rows = brain.ledger.decisions(capped.data["packet_id"])
            self.assertTrue(any("past the ceiling of 25" in r["reason"] for r in rows))
        finally:
            brain.close()

    def test_what_does_not_fit_becomes_a_pointer_never_a_drop(self):
        long_text = " ".join(["Grid spacing detail."] * 120)
        notes = [fixture.note(f"facts-grid-{i}", "facts", "services", "company",
                              f"Grid system {i}: {long_text}") for i in range(6)]
        extra_notes(self.vault, notes)
        table = {meta["id"]: 0.9 - i * 0.01 for i, (meta, _b) in enumerate(notes)}
        brain = self.brain(reranker=TableReranker(None, "", table))
        try:
            res = brain.context("Explain our grid system for layouts")
            sent = set(res.data["note_ids"])
            self.assertTrue(set(table) <= sent)  # every survivor is in the brief
            pointers = set(res.data["pointer_ids"])
            self.assertTrue(pointers and pointers < set(table))
            self.assertIn("facts-grid-0", sent - pointers)  # the best one whole
            rows = {r["item"]: r for r in brain.ledger.decisions(res.data["packet_id"])}
            self.assertEqual({rows[i]["outcome"] for i in pointers}, {"pointer"})
        finally:
            brain.close()

    def test_the_link_loop_stops_when_a_round_adds_nothing(self):
        notes = [
            fixture.note("facts-launch-plan", "facts", "services", "company",
                         "The launch plan for the redesign follows `facts-sequence-a`."),
            fixture.note("facts-sequence-a", "facts", "clients", "company",
                         "Kickoff, wireframes, review; then see `facts-sequence-b`."),
            fixture.note("facts-sequence-b", "facts", "clients", "company",
                         "Optional extras that matter to nobody here; see `facts-sequence-c`."),
            fixture.note("facts-sequence-c", "facts", "clients", "company",
                         "A detail only an optional extra needs."),
        ]
        extra_notes(self.vault, notes)
        table = {"facts-launch-plan": 0.9, "facts-sequence-a": 0.8, "facts-sequence-b": 0.2,
                 "facts-sequence-c": 0.9}
        brain = self.brain(reranker=TableReranker(None, "", table))
        try:
            res = brain.context("What is the launch plan for the redesign?")
            engine = res.data["engine"]
            # The router lists what the plan names (sequence-a); round 1 brings what that names
            # (sequence-b), which falls below the cut, so the loop stops: sequence-c, which only
            # sequence-b names, is never fetched, however relevant it would score.
            self.assertEqual(engine["rounds"], 1)
            sent = set(res.data["note_ids"])
            self.assertIn("facts-sequence-a", sent)
            self.assertNotIn("facts-sequence-b", sent)
            rows = {r["item"]: r for r in brain.ledger.decisions(res.data["packet_id"])}
            self.assertEqual(rows["facts-sequence-b"]["found_by"],
                             "linked from facts-sequence-a")
            self.assertEqual(rows["facts-sequence-b"]["round"], 1)
            self.assertNotIn("facts-sequence-c", rows)
        finally:
            brain.close()

    def test_the_loop_runs_three_rounds_at_most(self):
        chain = [fixture.note(f"facts-link-{i}", "facts", "clients", "company",
                              f"Stage {i}." + (f" Then `facts-link-{i + 1}`." if i < 6 else ""))
                 for i in range(1, 7)]
        chain.append(fixture.note("facts-onboarding-start", "facts", "services", "company",
                                  "The onboarding sequence starts here, then `facts-link-1`."))
        extra_notes(self.vault, chain)
        table = {meta["id"]: 0.9 for meta, _b in chain}
        brain = self.brain(reranker=TableReranker(None, "", table))
        try:
            res = brain.context("Walk me through the onboarding sequence")
            self.assertEqual(res.data["engine"]["rounds"], 3)
            sent = set(res.data["note_ids"])
            # link-1 is listed by the router itself; three rounds bring 2, 3 and 4, and stop.
            self.assertTrue({"facts-link-2", "facts-link-3", "facts-link-4"} <= sent)
            self.assertNotIn("facts-link-5", sent)
        finally:
            brain.close()

    def test_a_note_that_adds_nothing_goes_out_and_a_contradiction_travels_as_a_pair(self):
        notes = [
            fixture.note("facts-price-a", "facts", "services", "company",
                         "Brand identity projects cost 12,000 dollars."),
            fixture.note("facts-price-b", "facts", "services", "company",
                         "A brand identity project costs 12,000 dollars, same as before."),
            fixture.note("facts-price-c", "facts", "services", "company",
                         "Brand identity projects now cost 15,000 dollars."),
        ]
        extra_notes(self.vault, notes)
        table = {"facts-price-a": 0.95, "facts-price-b": 0.9, "facts-price-c": 0.85}
        decider = TableDecider(None, "", table={
            "adds.note.facts-price-b": "n1",          # says what facts-price-a says
            "contradicts.note.facts-price-c": "n1"})  # disagrees with facts-price-a
        brain = self.brain(reranker=TableReranker(None, "", table), decider=decider)
        try:
            res = brain.context("What does a brand identity project cost?")
            sent = set(res.data["note_ids"])
            self.assertEqual(sent & set(table), {"facts-price-a", "facts-price-c"})
            self.assertIn("`facts-price-a` and `facts-price-c` disagree", res.text)
            rows = {r["item"]: r for r in brain.ledger.decisions(res.data["packet_id"])}
            self.assertEqual(rows["facts-price-b"]["reason"], "adds nothing beyond facts-price-a")
            self.assertIn("disputed with facts-price-a", rows["facts-price-c"]["reason"])
        finally:
            brain.close()

    def test_a_request_that_should_get_nothing_gets_one_line(self):
        brain = self.brain(decider=TableDecider(None, "", gate=0.05))
        try:
            res = brain.context("What is the capital of Portugal?")
            self.assertEqual(res.data["mode"], "nothing")
            self.assertTrue(res.text.split("# Task context\n\n", 1)[1].startswith(
                "Nothing in this Brain applies to this request"))
            self.assertEqual(res.data["note_ids"], [])
            self.assertEqual(res.data["engine"]["gate"]["passed"], False)
        finally:
            brain.close()

    def test_nothing_above_the_cut_is_one_line_too(self):
        brain = self.brain(reranker=TableReranker(None, "", default=0.05))
        try:
            res = brain.context("How should headlines be written?")
            self.assertEqual(res.data["mode"], "nothing")
            self.assertEqual(res.data["engine"]["reason"], "nothing cleared the relevance cut")
        finally:
            brain.close()

    def test_a_failing_service_leaves_retrieval_as_it_was(self):
        with mock.patch.dict(os.environ, {"BRAIN_MODEL_SERVICE": "off"}):
            models_client.forget()
            plain = Brain(self.vault, embeddings=False)
            before = plain.context("How should headlines be written?", record=False).text
            plain.close()
        brain = self.brain(reranker=TableReranker(None, "", fail=True))
        try:
            res = brain.context("How should headlines be written?", record=False)
            self.assertEqual(res.data["engine"]["mode"], "fallback")
            self.assertIn("failed on this request", res.data["engine"]["reason"])
            cut = "\n\n## Continuity"
            self.assertEqual(res.text.split(cut)[0], before.split(cut)[0])
        finally:
            brain.close()


class MustHoldTests(unittest.TestCase):
    """Must-holds bypass relevance: a gate's no and an empty cut never remove one in play."""

    def setUp(self):
        self.vault = safeguards_eval.copy_vault(os.path.join(REPO, "brains", "personal",
                                                             "vault"))
        self.rig = None

    def tearDown(self):
        if self.rig is not None:
            self.rig.stop()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_the_gate_and_the_cut_never_remove_a_must_hold_in_play(self):
        self.rig = Rig(decider=TableDecider(None, "", gate=0.05))
        brain = Brain(self.vault, embeddings=False)
        try:
            res = brain.context("Plan Saturday's dinner menu for the kids")
            self.assertEqual(res.data["mode"], "nothing")
            self.assertIn("family-ollie", res.data["must_hold_ids"])
            self.assertIn("peanuts", res.text)
        finally:
            brain.close()
        self.rig.stop()
        self.rig = Rig(reranker=TableReranker(None, "", default=0.01))
        brain = Brain(self.vault, embeddings=False)
        try:
            res = brain.context("Plan Saturday's dinner menu for the kids")
            self.assertIn("family-ollie", res.data["must_hold_ids"])
        finally:
            brain.close()

    def test_the_decision_model_can_add_a_must_hold_domain_never_remove_one(self):
        decider = TableDecider(None, "", table={"domain.money": 0.9})
        self.rig = Rig(decider=decider)
        brain = Brain(self.vault, embeddings=False)
        try:
            res = brain.context("Should we book the cabin for the long weekend?")
            self.assertIn("money-budget", res.data["must_hold_ids"])
            self.assertGreaterEqual(res.data["engine"]["domains"].get("money", 0), 0.9)
        finally:
            brain.close()


class PushTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.env = mock.patch.dict(os.environ, {"BRAIN_VAULT": self.vault,
                                                "BRAIN_EMBEDDINGS": "0", "BRAIN_HOOK_PUSH": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        fixture.remove(self.vault)

    def test_a_push_goes_through_the_gate(self):
        rig = Rig(decider=TableDecider(None, "", gate=0.05))
        try:
            payload = {"session_id": "5f0e7c1a-2222-4c2e-9a37-2f1d1c0e9b10"}
            self.assertEqual(capture_prompt.push("What is the capital of Portugal?", payload),
                             "")
        finally:
            rig.stop()
        rig = Rig(reranker=TableReranker(None, "", {"rules-style-002": 0.95}))
        try:
            payload = {"session_id": "5f0e7c1a-3333-4c2e-9a37-2f1d1c0e9b10"}
            pushed = capture_prompt.push("How should headlines be written?", payload)
            self.assertIn("sentence case", pushed)
        finally:
            rig.stop()


if __name__ == "__main__":
    unittest.main()
