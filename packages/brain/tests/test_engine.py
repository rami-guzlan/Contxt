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

from brainkit import engine as engine_mod  # noqa: E402
from brainkit import machine, modellock, models_client, modelservice, safeguards_eval  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from brainkit.hooks import capture_prompt  # noqa: E402
from brainkit.vault import Vault  # noqa: E402
from tests import fixture  # noqa: E402

REPO = os.path.dirname(os.path.dirname(ROOT))
FILES = {"standin-reranker": b"a reranker that answers from a table",
         "standin-decider": b"a decision model that answers from a table"}
AGENT_FILE = b"a knowledge agent model that answers with fixed text"


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


class StandinAgent(modelservice.AgentBackend):
    """The knowledge agent's model, stood in: it answers with fixed text."""

    def __init__(self, pin, folder, text=""):
        super().__init__(pin, folder)
        self.text = text
        self.asked = []

    def generate(self, system, prompt, schema, max_tokens):
        self.asked.append((system, prompt, schema, max_tokens))
        return self.text


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


# A machine with a 12 GB GPU: the workstation setup, whose ceiling is the engine's default.
WORKSTATION = {"machine": {"ram_gb": 32.0, "gpu": "a stand-in GPU", "gpu_gb": 12.0,
                           "apple_silicon": False, "system": "Windows"},
               "setup": "workstation"}


def write_lock(folder: str, *, tamper: bool = False, qualify=None, agent: bool = False) -> str:
    """A lock with the stand-ins pinned to the files written beside it. `qualify` names the
    Kev steps the stand-in decision model must qualify for (as Kev-0.8B must)."""
    models = []
    files = dict(FILES, **({"standin-agent": AGENT_FILE} if agent else {}))
    for name, data in files.items():
        target = os.path.join(folder, "models", name)
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "weights.bin"), "wb") as handle:
            handle.write(data + (b"!" if tamper and name == "standin-reranker" else b""))
        extra = {"ram_gb": 1.0, "size_gb": 0.5}
        if qualify and name == "standin-decider":
            extra["qualify"] = list(qualify)
        role = "rerank" if "reranker" in name else "agent" if "agent" in name else "decide"
        models.append({"name": name, "role": role,
                       "default": True, "repository": "", "revision": "1",
                       "files": {"weights.bin": hashlib.sha256(data).hexdigest()},
                       "dtype": "float32", "runtime": {}, "extra": extra})
    models.append({"name": "unpinned-model", "role": "rerank", "repository": "",
                   "revision": "", "files": {}})
    path = os.path.join(folder, "models.lock.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"models": models}, handle)
    return path


class Rig:
    """A model service with stand-ins, and the environment that points the engine at it."""

    def __init__(self, *, reranker=None, decider=None, choose=None, tamper=False,
                 settings=None, qualify=None, agent=None):
        self.folder = tempfile.mkdtemp(prefix="brain-engine-")
        self.lock_path = write_lock(self.folder, tamper=tamper, qualify=qualify,
                                    agent=agent is not None)
        self.lock = modellock.Lock.load(self.lock_path)
        # This machine's settings live in the rig's own model home, never the person's.
        self.env = mock.patch.dict(os.environ, {
            "BRAIN_MODELS_LOCK": self.lock_path,
            "BRAIN_MODEL_HOME": os.path.join(self.folder, "home")})
        self.env.start()
        machine.save(dict(WORKSTATION if settings is None else settings))
        self.reranker = reranker or TableReranker(None, "")
        self.decider = decider or TableDecider(None, "")

        def build(backend):
            def make(pin, folder):
                backend.pin, backend.folder = pin, folder
                return backend
            return make

        factories = {"standin-reranker": build(self.reranker),
                     "standin-decider": build(self.decider)}
        if agent is not None:
            factories["standin-agent"] = build(agent)
        service = modelservice.ModelService(
            lock=self.lock, models_dir=os.path.join(self.folder, "models"),
            factories=factories, choose=choose)
        self.running = modelservice.start(service, 0, announce=False)
        os.environ["BRAIN_MODEL_SERVICE"] = self.running.url  # undone with the patch
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
        # The laptop setup's models, pinned on the PC (build step 9).
        for name in ("qwen3-reranker-0.6b", "kev-0.8b", "qwen3.5-4b", "ms-marco-minilm-l-6-v2"):
            self.assertTrue(lock.pin(name).pinned, name)
        self.assertFalse(lock.pin("kev-4b").pinned)  # no files yet: a GPU with 12 GB runs it
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


class WhyTests(unittest.TestCase):
    """Activity reads back why each candidate went in or stayed out; the eval scores requests
    labeled "should get nothing"."""

    def setUp(self):
        self.vault = fixture.build()

    def tearDown(self):
        fixture.remove(self.vault)

    def test_activity_reads_back_why_each_candidate_went_in_or_stayed_out(self):
        set_engine(self.vault, floor=0.0)
        rig = Rig(reranker=TableReranker(None, "", {"rules-style-002": 0.95}))
        brain = Brain(self.vault, embeddings=False)
        try:
            res = brain.context("How should headlines be written?")
            why = brain.request(res.data["packet_id"]).data["why"]
            self.assertEqual((why["mode"], why["lock"]), ("on", rig.lock.fingerprint))
            self.assertEqual([r["item"] for r in why["in"]], ["rules-style-002"])
            self.assertTrue(why["out"])
            self.assertTrue(all("below the relevance cut" in r["reason"] for r in why["out"]))
            self.assertTrue(why["in"][0]["title"].startswith("Headlines use sentence case"))
        finally:
            brain.close()
            rig.stop()

    def test_the_eval_scores_correct_nothing_and_false_nothing(self):
        from brainkit import evalset, evaluate
        cases = {"cases": [
            {"id": "n1", "request": "What is the capital of Portugal?", "nothing": True,
             "must": []},
            {"id": "h1", "request": "How should headlines be written?",
             "must": [["rules-style-002"]]},
            {"id": "h2", "request": "What is the boiling point of mercury?",
             "must": [["facts-services-001"]]}]}
        path = os.path.join(os.path.dirname(self.vault), "eval.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cases, handle)
        with mock.patch.dict(os.environ, {"BRAIN_MODEL_SERVICE": "off"}):
            brain = Brain(self.vault, embeddings=False)
            try:
                result = evaluate.run(brain, path)
                every = result["all"]
                self.assertEqual(every["nothing_cases"], 1)
                self.assertEqual(every["correct_nothing"], 1.0)
                self.assertEqual(every["false_nothing"], 0.5)  # h2 needed a note, got nothing
                packet = brain.context("What is the capital of Portugal?").data["packet_id"]
                evalset.add(brain, "What is the capital of Portugal?", packet)
                case = evalset.label(brain, packet, nothing=True, noise=["rules-style-002"])
                self.assertTrue(case["nothing"])
                with self.assertRaises(ValueError):
                    evalset.label(brain, packet, nothing=True, needed=["rules-style-002"])
            finally:
                brain.close()


class SetupTests(unittest.TestCase):
    """The switches the comparison (5.11.11) runs setups A to E with."""

    def setUp(self):
        self.vault = fixture.build()

    def tearDown(self):
        fixture.remove(self.vault)

    def test_setup_a_keeps_a_brain_on_the_fallback_even_with_a_service(self):
        set_engine(self.vault, enabled=False)
        rig = Rig()
        brain = Brain(self.vault, embeddings=False)
        try:
            res = brain.context("How should headlines be written?")
            self.assertEqual(res.data["engine"]["mode"], "fallback")
            self.assertIn("off for this Brain", res.data["engine"]["reason"])
        finally:
            brain.close()
            rig.stop()

    def test_setup_b_is_the_reranker_alone(self):
        set_engine(self.vault, layers={"gate": False, "second_pass": False, "loop": False})
        decider = TableDecider(None, "")
        rig = Rig(reranker=TableReranker(None, "", {"rules-style-002": 0.95}), decider=decider)
        brain = Brain(self.vault, embeddings=False)
        try:
            res = brain.context("How should headlines be written?")
            # Without the decision model's gate, the reranker's best score against the cut
            # decides whether the request gets anything.
            self.assertEqual(res.data["engine"]["gate"]["by"], "reranker")
            self.assertEqual(res.data["engine"]["gate"]["yes"], 0.95)
            self.assertEqual(decider.asked, [])  # no gate, no second pass
            self.assertIn("rules-style-002", res.data["note_ids"])
        finally:
            brain.close()
            rig.stop()

    def test_setup_e_scores_relevance_with_the_decision_model(self):
        set_engine(self.vault, scorer="decide", floor=0.0)
        reranker = TableReranker(None, "")
        rig = Rig(reranker=reranker, decider=TableDecider(None, "", table={
            f"rel.{i}": 0.1 for i in range(400)}))
        brain = Brain(self.vault, embeddings=False)
        try:
            res = brain.context("How should headlines be written?")
            self.assertEqual(reranker.calls, [])  # the reranker never ran
            self.assertEqual(res.data["mode"], "nothing")  # every note scored 0.1 < 0.5
        finally:
            brain.close()
            rig.stop()


class MachineTests(unittest.TestCase):
    """Machine setups and the model settings (5.11.15, 5.11.16), on the shipped lock."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="brain-home-")
        self.env = mock.patch.dict(os.environ, {"BRAIN_MODEL_HOME": self.home})
        self.env.start()
        self.lock = modellock.Lock.load()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def test_each_machine_gets_the_setup_that_fits(self):
        cases = [(machine.Machine(ram_gb=15.8), "laptop"),
                 (machine.Machine(ram_gb=8.0), "small"),
                 (machine.Machine(ram_gb=16.0, apple_silicon=True), "laptop"),
                 (machine.Machine(ram_gb=32.0, gpu="g", gpu_gb=12.0), "workstation"),
                 (machine.Machine(ram_gb=32.0, apple_silicon=True), "workstation"),
                 (machine.Machine(ram_gb=64.0, apple_silicon=True), "large"),
                 (machine.Machine(ram_gb=32.0, gpu="g", gpu_gb=24.0), "large")]
        for found, setup in cases:
            self.assertEqual(found.setup, setup, found)
        self.assertEqual(machine.check(machine.Machine(ram_gb=15.8))["setup"], "laptop")
        self.assertEqual(machine.chosen("decide"), "kev-0.8b")
        self.assertEqual(machine.chosen("agent"), "qwen3.5-4b")
        self.assertEqual(machine.ceiling(), 100)
        machine.check(machine.Machine(ram_gb=8.0))
        self.assertIsNone(machine.chosen("decide"))  # code alone, bge-small and MiniLM
        self.assertEqual(machine.chosen("rerank"), "ms-marco-minilm-l-6-v2")

    def test_no_default_is_offered_that_will_not_fit(self):
        # A 16 GB machine that reports 15.0 GB has room for about 5.5 GB of models; the laptop
        # defaults need 5.6, so the small reranker gives way first.
        machine.check(machine.Machine(ram_gb=15.0))
        self.assertEqual(machine.chosen("rerank", lock=self.lock), "ms-marco-minilm-l-6-v2")
        self.assertEqual(machine.chosen("agent", lock=self.lock), "qwen3.5-4b")
        found = machine.overview(self.lock)
        self.assertEqual(found["ram_in_use_gb"], 4.5)
        self.assertIn("qwen3-reranker-0.6b does not fit beside the other defaults here",
                      found["fallbacks"][0])
        # Choosing it back is refused while the other defaults stay.
        with self.assertRaises(ValueError):
            machine.choose("rerank", "qwen3-reranker-0.6b", lock=self.lock)

    def test_a_choice_the_ram_check_says_will_not_fit_is_refused(self):
        machine.check(machine.Machine(ram_gb=15.8))  # 16 GB, no GPU
        with self.assertRaises(ValueError) as caught:
            machine.choose("agent", "qwen3.5-9b", lock=self.lock)
        self.assertIn("will not fit: these models need about 8.9 GB and this computer has "
                      "room for about 6.3 GB", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            machine.choose("decide", "qwen3.5-4b", lock=self.lock)
        self.assertIn("a knowledge agent model, not a decisions model", str(caught.exception))
        with self.assertRaises(modellock.Refused):
            machine.choose("agent", "a-model-nobody-pinned", lock=self.lock)
        machine.choose("rerank", "ms-marco-minilm-l-6-v2", lock=self.lock)
        self.assertEqual(machine.chosen("rerank"), "ms-marco-minilm-l-6-v2")
        # A GPU makes room; checking the machine again keeps the person's choices.
        machine.check(machine.Machine(ram_gb=32.0, gpu="g", gpu_gb=12.0))
        machine.choose("agent", "qwen3.5-9b", lock=self.lock)
        self.assertEqual(machine.chosen("rerank"), "ms-marco-minilm-l-6-v2")
        self.assertEqual(machine.chosen("agent"), "qwen3.5-9b")

    def test_settings_show_each_role_its_options_and_each_fallback(self):
        machine.check(machine.Machine(ram_gb=15.8))
        found = machine.overview(self.lock)
        self.assertEqual((found["setup"], found["setup_label"]), ("laptop", "Laptop"))
        roles = {r["role"]: r for r in found["roles"]}
        self.assertEqual(roles["decide"]["model"], "kev-0.8b")
        options = {o["name"]: o for o in roles["agent"]["options"]}
        self.assertTrue(options["qwen3.5-4b"]["in_use"])
        self.assertTrue(options["qwen3.5-4b"]["fits"])
        self.assertFalse(options["qwen3.6-35b-a3b"]["fits"])
        self.assertIn("need about", options["qwen3.6-35b-a3b"]["fit_reason"])
        self.assertFalse(options["qwen3.5-4b"]["downloaded"])  # nothing downloaded here
        self.assertEqual(found["ram_in_use_gb"], 5.6)
        self.assertFalse(found["engine"]["ready"])
        # Kev-0.8B has qualified for neither step on this machine yet: both fall back.
        self.assertEqual(len(found["fallbacks"]), 2)
        machine.record("kev-0.8b", speed_ms=180, quality=0.91, steps={"gate": True})
        found = machine.overview(self.lock)
        self.assertEqual(found["fallbacks"], ["kev-0.8b has not qualified for the second pass "
                                              "here: it is skipped"])
        roles = {r["role"]: r for r in found["roles"]}
        decide = {o["name"]: o for o in roles["decide"]["options"]}
        self.assertEqual(decide["kev-0.8b"]["measured"]["speed_ms"], 180.0)
        # Kev-4B and Kev-9B run every step from the start.
        self.assertTrue(machine.qualified("kev-4b", "gate", {}, self.lock))
        self.assertFalse(machine.qualified(None, "gate", {}, self.lock))


class QualifyTests(unittest.TestCase):
    """A decision model the lock says must qualify runs a Kev step only once it has, on this
    machine; until then the gate goes to the reranker and the second pass is skipped."""

    def setUp(self):
        self.vault = fixture.build()

    def tearDown(self):
        fixture.remove(self.vault)

    def test_an_unqualified_decision_model_hands_the_gate_to_the_reranker(self):
        decider = TableDecider(None, "", gate=0.05)  # it would say no
        rig = Rig(reranker=TableReranker(None, "", {"rules-style-002": 0.95}), decider=decider,
                  qualify=["gate", "second_pass"])
        brain = Brain(self.vault, embeddings=False)
        try:
            self.assertEqual(rig.running.service.health()["qualified"],
                             {"gate": False, "second_pass": False})
            res = brain.context("How should headlines be written?")
            engine = res.data["engine"]
            self.assertEqual(engine["mode"], "on")
            self.assertEqual(engine["gate"]["by"], "reranker")
            self.assertEqual(decider.asked, [])  # neither the gate nor the second pass ran
            self.assertIn("rules-style-002", res.data["note_ids"])
            self.assertEqual(engine["notes"], [
                "standin-decider has not qualified for the gate here: the reranker's best "
                "score against the cut decides instead",
                "standin-decider has not qualified for the second pass here: it is skipped"])
            # Once it qualifies for the gate on this machine, the gate is its own again.
            machine.record("standin-decider", steps={"gate": True})
            models_client.reload()
            res = brain.context("What is the capital of Portugal?")
            self.assertEqual(res.data["mode"], "nothing")
            self.assertEqual(res.data["engine"]["gate"]["yes"], 0.05)
            self.assertEqual(len(decider.asked), 1)
            self.assertEqual(list(decider.asked[0][1]), ["gate"])  # no second-pass questions
        finally:
            brain.close()
            rig.stop()

    def test_a_small_machine_runs_no_decision_model_so_retrieval_falls_back(self):
        rig = Rig(settings={"machine": {"ram_gb": 8.0}, "setup": "small"})
        brain = Brain(self.vault, embeddings=False)
        try:
            found = models_client.status(refresh=True)
            self.assertFalse(found.ready)
            self.assertIn("this computer's setup (small) runs no decide model", found.reason)
            res = brain.context("How should headlines be written?")
            self.assertEqual(res.data["engine"]["mode"], "fallback")
        finally:
            brain.close()
            rig.stop()

    def test_the_setup_sets_the_ceiling_unless_the_brain_names_one(self):
        brain = Brain(self.vault, embeddings=False)
        laptop = models_client.Status(ready=True, setup="laptop", ceiling=100)
        try:
            st = brain.state()
            found = engine_mod.Engine(st, engine_mod.Settings.of(st.config), None, None, "",
                                      laptop)
            self.assertEqual(found.settings.ceiling, 100)
        finally:
            brain.close()
        set_engine(self.vault, ceiling=250)
        brain = Brain(self.vault, embeddings=False)
        try:
            st = brain.state()
            found = engine_mod.Engine(st, engine_mod.Settings.of(st.config), None, None, "",
                                      laptop)
            self.assertEqual(found.settings.ceiling, 250)
        finally:
            brain.close()

    def test_cuts_fitted_for_other_models_give_way_to_the_defaults(self):
        set_engine(self.vault, cuts={"relevance": 0.8},
                   fitted={"date": "2026-10-01", "eval_run": "run-1",
                           "models": {"rerank": "another-reranker",
                                      "decide": "standin-decider"}})
        brain = Brain(self.vault, embeddings=False)

        def running(reranker):
            return models_client.Status(ready=True, roles={
                "rerank": {"model": reranker}, "decide": {"model": "standin-decider"}})

        try:
            st = brain.state()
            found = engine_mod.Engine(st, engine_mod.Settings.of(st.config), None, None, "",
                                      running("standin-reranker"))
            self.assertTrue(found.refit)
            self.assertEqual(found.settings.cuts["relevance"], engine_mod.CUTS["relevance"])
            self.assertIn("a refit on this Brain's labels is suggested", found.notes[0])
            found = engine_mod.Engine(st, engine_mod.Settings.of(st.config), None, None, "",
                                      running("another-reranker"))
            self.assertFalse(found.refit)
            self.assertEqual(found.settings.cuts["relevance"], 0.8)
        finally:
            brain.close()

    def test_a_new_default_takes_effect_on_reload_and_the_lock_still_decides(self):
        rig = Rig()
        try:
            self.assertTrue(models_client.status(refresh=True).ready)
            settings = machine.load()
            settings["models"] = {"rerank": "unpinned-model"}
            machine.save(settings)
            health = models_client.reload()
            self.assertEqual(health["roles"]["rerank"]["model"], "unpinned-model")
            self.assertFalse(health["roles"]["rerank"]["verified"])  # no files pinned
            self.assertFalse(models_client.status(refresh=True).ready)
        finally:
            rig.stop()


class AgentTests(unittest.TestCase):
    """The knowledge agent's local model behind the service (brain-logic plan 17), stood in."""

    SCHEMA = {"type": "object", "required": ["verdict", "why"],
              "properties": {"verdict": {"type": "string", "enum": ["keep", "change"]},
                             "why": {"type": "string"}}}

    def test_the_agent_answers_through_the_service_bound_to_a_schema(self):
        agent = StandinAgent(None, "", text='{"verdict": "keep", "why": "it still holds"}')
        rig = Rig(agent=agent)
        try:
            found = models_client.status(refresh=True)
            self.assertEqual(found.agent, "standin-agent")
            answer = models_client.Agent(found).generate(
                "Does the note still hold?", system="You check notes.", schema=self.SCHEMA)
            self.assertEqual(answer["json"], {"verdict": "keep", "why": "it still holds"})
            self.assertEqual(answer["problems"], [])
            self.assertEqual(answer["model"], "standin-agent")
            self.assertEqual(agent.asked[0][:3], ("You check notes.", "Does the note still hold?",
                                                  self.SCHEMA))
            agent.text = '{"verdict": "maybe"}'
            answer = models_client.Agent(found).generate("Again?", schema=self.SCHEMA)
            self.assertEqual(answer["problems"], ["it has no why",
                                                  "verdict is not one of keep, change"])
            agent.text = "not JSON at all"
            answer = models_client.Agent(found).generate("Again?", schema=self.SCHEMA)
            self.assertIsNone(answer["json"])
            self.assertEqual(answer["problems"], ["the answer is not an object"])
        finally:
            rig.stop()

    def test_without_an_agent_model_the_service_says_so(self):
        rig = Rig()
        try:
            found = models_client.status(refresh=True)
            self.assertTrue(found.ready)  # the engine needs no agent
            self.assertEqual(found.agent, "")
            with self.assertRaises(models_client.ServiceError):
                models_client.Agent(found).generate("Anything?")
        finally:
            rig.stop()


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
