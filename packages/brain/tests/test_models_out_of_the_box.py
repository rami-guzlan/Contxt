"""The local engine out of the box, without a 12 GB GPU (build step 9; brain-logic plan 5.11).

Kev's adapters run on a base model the lock pins with them; each setup's models have a backend
that runs on this kind of machine; models go where they fit (a small GPU while it has room, else
the CPU); and the model runtime is one separate environment, named, never PyPI's unrelated
`kev`. Proved with stand-in files and probes: the real models are measured on the PC
(`docs/evals/setups-a-to-e.md`).
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import machine, modellock, modelservice  # noqa: E402

ADAPTER = b"a decision model's adapter"
BASE = b"the base model it runs on"


def hf_folder(models: str, repository: str, revision: str, files: dict) -> str:
    """A model laid out the way a Hugging Face cache keeps it."""
    folder = os.path.join(models, "models--" + repository.replace("/", "--"), "snapshots",
                          revision)
    for rel, data in files.items():
        path = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
    return folder


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class BaseModelTests(unittest.TestCase):
    """An adapter is only as pinned as the base it runs on: the lock pins both."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="brain-base-")
        self.models = os.path.join(self.home, "models")
        self.adapter = hf_folder(self.models, "maker/decider-small", "a" * 40,
                                 {"adapter.safetensors": ADAPTER})
        self.base = hf_folder(self.models, "maker/base-small", "b" * 40,
                              {"model.safetensors": BASE, "tokenizer/vocab.json": b"{}"})
        self.lock_path = os.path.join(self.home, "models.lock.json")
        self.row = {"name": "decider-small", "role": "decide", "default": True,
                    "repository": "maker/decider-small", "revision": "a" * 40,
                    "files": {"adapter.safetensors": sha(ADAPTER)},
                    "base": {"repository": "maker/base-small", "revision": "b" * 40,
                             "files": {"model.safetensors": sha(BASE),
                                       "tokenizer/vocab.json": sha(b"{}")}}}
        self.write(self.row)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def write(self, row):
        with open(self.lock_path, "w", encoding="utf-8") as handle:
            json.dump({"models": [row]}, handle)
        return modellock.Lock.load(self.lock_path)

    def test_an_adapter_loads_only_when_its_base_matches_the_lock_too(self):
        lock = modellock.Lock.load(self.lock_path)
        self.assertTrue(lock.pin("decider-small").pinned)
        self.assertTrue(lock.verify("decider-small", self.adapter).ok)
        with open(os.path.join(self.base, "model.safetensors"), "ab") as handle:
            handle.write(b"!")
        found = lock.verify("decider-small", self.adapter)
        self.assertFalse(found.ok)
        self.assertEqual(found.reason, "decider-small: its base model maker/base-small: "
                                       "model.safetensors does not match the lock")
        shutil.rmtree(os.path.dirname(os.path.dirname(self.base)))
        found = lock.verify("decider-small", self.adapter)
        self.assertEqual(found.reason, "decider-small: its base model maker/base-small is not "
                                       "downloaded")

    def test_a_base_with_no_revision_or_checksums_is_not_pinned(self):
        row = dict(self.row, base={"repository": "maker/base-small", "revision": "",
                                   "files": {}})
        lock = self.write(row)
        self.assertFalse(lock.pin("decider-small").pinned)
        self.assertIn("not pinned yet", lock.verify("decider-small", self.adapter).reason)

    def test_the_fingerprint_covers_the_base(self):
        before = modellock.Lock.load(self.lock_path).fingerprint
        row = json.loads(json.dumps(self.row))
        row["base"]["revision"] = "c" * 40
        self.assertNotEqual(self.write(row).fingerprint, before)

    def test_pinning_records_the_base_from_the_same_cache(self):
        row = dict(self.row, revision="", files={}, base={})
        self.write(row)
        found = modellock.record_pin("decider-small", self.adapter, revision="a" * 40,
                                     base="maker/base-small@" + "b" * 40, path=self.lock_path)
        self.assertEqual(found["base"], {"repository": "maker/base-small",
                                         "revision": "b" * 40, "files": 2})
        lock = modellock.Lock.load(self.lock_path)
        self.assertEqual(lock.pin("decider-small").base["files"],
                         self.row["base"]["files"])
        self.assertTrue(lock.verify("decider-small", self.adapter).ok)
        with self.assertRaises(modellock.Refused):
            modellock.record_pin("decider-small", self.adapter, base="maker/nowhere@" + "d" * 40,
                                 path=self.lock_path)

    def test_downloading_fetches_the_base_at_its_pinned_revision(self):
        lock = modellock.Lock.load(self.lock_path)
        with mock.patch("huggingface_hub.snapshot_download") as fetch:
            machine._fetch(lock.pin("decider-small"), self.models)
        calls = [(c.kwargs["repo_id"], c.kwargs["revision"], c.kwargs["allow_patterns"])
                 for c in fetch.call_args_list]
        self.assertEqual(calls, [
            ("maker/decider-small", "a" * 40, ["adapter.safetensors"]),
            ("maker/base-small", "b" * 40, ["model.safetensors", "tokenizer/vocab.json"])])


class ShippedLockTests(unittest.TestCase):
    def test_every_model_a_setup_names_has_a_backend(self):
        lock = modellock.Lock.load()
        for setup, shape in machine.SETUPS.items():
            for role, name in shape["models"].items():
                if role in modelservice.SERVED and name:
                    self.assertIn(name, modelservice.BACKENDS, f"{setup} names {name}")
                    self.assertIn(name, lock.pins)

    def test_kev_adapters_pin_their_base(self):
        lock = modellock.Lock.load()
        pin = lock.pin("kev-0.8b")
        self.assertEqual(pin.base["repository"], "Qwen/Qwen3.5-0.8B-Base")
        self.assertTrue(pin.pinned)


class PlacementTests(unittest.TestCase):
    """Models go where they fit, in the precision the device runs best."""

    NONE = {"cuda": False, "free_gb": 0.0, "bf16": False, "mps": False}

    def place(self, size_gb, **found):
        return modelservice.place(size_gb, dict(self.NONE, **found))

    def test_without_an_accelerator_a_model_runs_on_the_cpu_in_fp32(self):
        self.assertEqual(self.place(1.2), ("cpu", "float32"))

    def test_a_small_gpu_takes_models_while_it_has_room(self):
        # A GTX 1060: 6 GB, about 5 GB free, no native bf16 (fp16 measured best there).
        self.assertEqual(self.place(1.2, cuda=True, free_gb=5.1), ("cuda", "float16"))
        self.assertEqual(self.place(2.7, cuda=True, free_gb=2.9), ("cpu", "float32"))
        self.assertEqual(self.place(1.2, cuda=True, free_gb=24.0, bf16=True),
                         ("cuda", "bfloat16"))
        self.assertEqual(self.place(1.2, mps=True, bf16=True), ("mps", "bfloat16"))

    def test_a_named_device_wins(self):
        with mock.patch.dict(os.environ, {"BRAIN_MODEL_DEVICE": "cpu"}):
            self.assertEqual(self.place(1.2, cuda=True, free_gb=5.1), ("cpu", "float32"))
        with mock.patch.dict(os.environ, {"BRAIN_MODEL_DEVICE": "cuda"}):
            self.assertEqual(self.place(9.0, cuda=True, free_gb=5.1), ("cuda", "float16"))

    def test_kev_gets_the_same_precision_by_its_own_name(self):
        self.assertEqual([modelservice.kev_dtype(d) for d in ("bfloat16", "float16", "float32")],
                         ["bf16", "fp16", "fp32"])


MODELS = os.environ.get("BRAIN_TEST_MODELS", "")


@unittest.skipUnless(MODELS and modellock.snapshot(
    MODELS, "Xenova/ms-marco-MiniLM-L-6-v2",
    modellock.Lock.load().pin("ms-marco-minilm-l-6-v2").revision),
    "needs BRAIN_TEST_MODELS with MiniLM (scripts/fetch_test_models.py)")
class MiniLMTests(unittest.TestCase):
    def test_minilm_reranks_from_its_pinned_files_on_the_cpu(self):
        lock = modellock.Lock.load()
        pin = lock.pin("ms-marco-minilm-l-6-v2")
        folder = modelservice.snapshot(MODELS, pin)
        self.assertTrue(lock.verify(pin.name, folder).ok)
        backend = modelservice.BACKENDS[pin.name](pin, folder)
        backend.load()
        found = backend.scores("How should headlines be written?", "Judge whether this helps", [
            "Headlines use sentence case and stay under 70 characters.",
            "The office plants are watered on Fridays."])
        self.assertEqual(len(found), 2)
        self.assertTrue(all(0.0 <= s <= 1.0 for s in found))
        self.assertGreater(found[0], found[1])


class KevInstallTests(unittest.TestCase):
    def test_a_missing_kev_points_at_the_runtime_never_at_pypi(self):
        pin = modellock.Pin(name="kev-0.8b", role="decide", repository="jaredpalmer/kev-0.8b",
                            revision="r")
        with mock.patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(RuntimeError) as caught:
                modelservice.KevServer(pin, "").load()
        self.assertIn("brain models runtime", str(caught.exception))
        self.assertNotIn("pip install kev", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
