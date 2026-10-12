"""The local model service: one process on this machine that loads each pinned model once.

    python -m brainkit.modelservice [--port 8791] [--models <folder>]

The retrieval engine (brain-logic plan 5.11) asks small local models two kinds of thing: how
relevant a passage is to a request (a reranker) and typed decisions (Kev). Loading a 4B model
in every MCP server, one per client, would be slow and wasteful, so one service loads each
model once and the engine, the app and every MCP session share it. It binds to 127.0.0.1 only.

- A model loads only when the lock (`models.lock.json`) lists it and its files match the lock's
  checksums; anything else is refused, with the reason in `/v1/health`.
- `GET /v1/health`: the lock's fingerprint and, per role, the model, whether it was verified and
  loaded, and why not.
- `POST /v1/rerank`: `{"model", "query", "instruction", "documents": [text]}` in;
  `{"model", "results": [{"index", "relevance_score"}], "latency_ms"}` out (scores 0 to 1).
- `POST /v1/systemone`: System One, Jev's request format, which Kev speaks:
  `{"model", "state", "questions"}` in; `{"model", "answers", "usage", "latency_ms"}` out.
- `POST /v1/generate`: the knowledge agent's model (brain-logic plan 17): `{"model", "system",
  "prompt", "schema", "max_tokens"}` in; `{"model", "text", "json", "latency_ms"}` out, the
  answer bound to the JSON schema while it is generated where the runtime can, and checked
  again here.
- `POST /v1/reload`: choose and load the models again (after the person changes a default).

Which model serves a role: the person's choice on this machine, else the machine setup's
default (machine.py), else the lock's default for the role.
- On start it writes `<model home>/modelservice.json` (its address, process and lock), which is
  how every client finds it; it removes the file when it stops.

Backends: Qwen3-Reranker through transformers, MiniLM (the small reranker) through ONNX on the
CPU, Kev through its own server (`python -m kev.serve`), started once on a private port with the
verified local copy and no downloads, and the agent through llama.cpp (MLX on a Mac). Each
imports its libraries only when a verified model needs them, so on a machine without models the
service runs, says so, and the engine falls back. Tests pass stand-ins.

No 12 GB GPU is needed (build step 9). Each model goes where it fits: a GPU while it has room
(models load in role order, so a small GPU fills up and the rest run on the CPU), else the CPU.
The precision follows the device: bf16 where the GPU has it natively, fp16 on an older NVIDIA GPU
(on a GTX 1060 it gave the same scores as fp32 in half the memory and ran faster than emulated
bf16), fp32 on the CPU. `BRAIN_MODEL_DEVICE` (cpu, cuda or mps) names a device instead.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import modellock, models_client

DEFAULT_PORT = 8791
MAX_BODY = 32 * 1024 * 1024  # bytes in one request
GPU_ROOM_GB = 0.8  # what a model needs on a GPU beyond its weights: activations, a cache
QWEN_SYSTEM = ("Judge whether the Document meets the requirements based on the Query and the "
               "Instruct provided. Note that the answer can only be \"yes\" or \"no\".")


def probe() -> dict:
    """This process's accelerators, read through torch: an NVIDIA GPU (its free memory and
    whether it has bf16 natively), or Apple's. Without torch, the CPU alone."""
    found = {"cuda": False, "free_gb": 0.0, "bf16": False, "mps": False}
    try:
        import torch
    except ImportError:
        return found
    if torch.cuda.is_available():
        free, _total = torch.cuda.mem_get_info()
        found.update(cuda=True, free_gb=free / 2 ** 30,
                     bf16=bool(torch.cuda.is_bf16_supported(including_emulation=False)))
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        found.update(mps=True, bf16=True)
    return found


def place(size_gb: float, found: dict | None = None) -> tuple[str, str]:
    """Where a model of `size_gb` (its weights in 16 bits) runs here, and in what precision:
    (device, torch dtype name). A GPU while it has room for the weights and GPU_ROOM_GB more,
    else the CPU in fp32. `BRAIN_MODEL_DEVICE` names a device instead."""
    found = probe() if found is None else found
    named = os.environ.get("BRAIN_MODEL_DEVICE", "").strip().lower()
    if named == "cpu":
        return "cpu", "float32"
    if found.get("mps") and named in ("", "mps"):
        return "mps", "bfloat16"
    if found.get("cuda") and (named == "cuda" or (
            not named and found.get("free_gb", 0.0) >= size_gb + GPU_ROOM_GB)):
        return "cuda", "bfloat16" if found.get("bf16") else "float16"
    return "cpu", "float32"


def kev_dtype(dtype: str) -> str:
    """Kev's name for a torch dtype (its KEV_DTYPE)."""
    return {"bfloat16": "bf16", "float16": "fp16"}.get(dtype, "fp32")


def cuda_libraries() -> None:
    """On Windows, llama.cpp's CUDA build needs the CUDA runtime's DLLs; the CUDA build of torch
    in the same environment ships them, so a machine needs no CUDA toolkit."""
    if sys.platform != "win32":
        return
    try:
        import torch
    except ImportError:
        return
    folder = os.path.join(os.path.dirname(torch.__file__), "lib")
    if os.path.isdir(folder):
        os.add_dll_directory(folder)


class Backend:
    """A loaded model serving one role."""
    role = ""

    def __init__(self, pin: modellock.Pin, folder: str):
        self.pin = pin
        self.folder = folder

    @property
    def model(self) -> str:
        return self.pin.name

    def load(self) -> None:
        """Load the model once; raise with the reason when it cannot run here."""

    def close(self) -> None:
        """Release what `load` took."""


class RerankBackend(Backend):
    role = "rerank"

    def scores(self, query: str, instruction: str, documents: list[str]) -> list[float]:
        raise NotImplementedError


class DecideBackend(Backend):
    role = "decide"

    def answers(self, state, questions: dict) -> dict:
        """System One answers: {question id: answer}."""
        raise NotImplementedError


class AgentBackend(Backend):
    role = "agent"

    def generate(self, system: str, prompt: str, schema: dict | None,
                 max_tokens: int) -> str:
        """The model's answer as text; with a schema, JSON bound to it."""
        raise NotImplementedError


class LlamaCppAgent(AgentBackend):
    """A 4-bit GGUF build through llama.cpp, its answer bound to the JSON schema while it is
    generated: every layer on the GPU when the GPU has room left for it, else the CPU (on a
    GTX 1060 an answer took 2.6 s on the GPU and 3.9 s on a Ryzen 7 9700X)."""

    def load(self) -> None:
        cuda_libraries()
        from llama_cpp import Llama
        files = sorted(f for f in os.listdir(self.folder) if f.endswith(".gguf"))
        if not files:
            raise RuntimeError("no .gguf file in the model's folder")
        path = os.path.join(self.folder, files[0])
        self.device, _dtype = place(os.path.getsize(path) / 2 ** 30)
        self.net = Llama(model_path=path, n_ctx=8192,
                         n_gpu_layers=-1 if self.device != "cpu" else 0, verbose=False)

    def generate(self, system: str, prompt: str, schema: dict | None,
                 max_tokens: int) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        kwargs: dict = {"max_tokens": max_tokens, "temperature": 0.2}
        if schema:
            kwargs["response_format"] = {"type": "json_object", "schema": schema}
        found = self.net.create_chat_completion(messages=messages, **kwargs)
        usage = found.get("usage") or {}
        self.usage = {"tokens_in": int(usage.get("prompt_tokens") or 0),
                      "tokens_out": int(usage.get("completion_tokens") or 0)}
        return str(found["choices"][0]["message"]["content"] or "")


class MlxAgent(AgentBackend):
    """A 4-bit MLX build on a Mac. MLX has no schema-bound decoding here, so the answer is
    checked against the schema in code (one retry in the agent's loop)."""

    def load(self) -> None:
        from mlx_lm import load
        self.net, self.tokenizer = load(self.folder)

    def generate(self, system: str, prompt: str, schema: dict | None,
                 max_tokens: int) -> str:
        from mlx_lm import generate
        text = self.tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            add_generation_prompt=True, tokenize=False)
        return str(generate(self.net, self.tokenizer, prompt=text, max_tokens=max_tokens))


def _agent_backend(pin, folder):
    """MLX on a Mac with Apple Silicon, llama.cpp elsewhere."""
    import platform
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return MlxAgent(pin, folder)
    return LlamaCppAgent(pin, folder)


def schema_problems(value, schema: dict | None) -> list[str]:
    """What keeps a JSON answer from matching a schema's top level: its type, the keys it
    requires, and each property's type. The agent's loop retries once on a problem."""
    if not schema:
        return []
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
             "boolean": bool}

    def a(word: str) -> str:
        return f"{'an' if word[:1] in 'aeiou' else 'a'} {word}"

    if kind in types and not isinstance(value, types[kind]):
        return [f"the answer is not {a(kind)}"]
    problems = []
    if isinstance(value, dict):
        for key in schema.get("required") or []:
            if key not in value:
                problems.append(f"it has no {key}")
        for key, spec in (schema.get("properties") or {}).items():
            want = (spec or {}).get("type")
            if key in value and want in types and not isinstance(value[key], types[want]):
                problems.append(f"{key} is not {a(want)}")
            allowed = (spec or {}).get("enum")
            if key in value and allowed and value[key] not in allowed:
                problems.append(f"{key} is not one of {', '.join(map(str, allowed))}")
    return problems


class QwenReranker(RerankBackend):
    """Qwen3-Reranker: the probability that the answer to "does the document meet the request,
    given the instruction?" is yes, read from the model's next-token logits for "yes" and "no",
    as its model card shows (only the last position's logits are computed). It runs on the CPU
    too, slowly: on a machine without a GPU the speed check hands the cut to MiniLM."""

    BATCH = 8

    def load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        device, dtype = place(float(self.pin.extra.get("size_gb") or 1.2))
        self.torch = torch
        self.device, self.dtype = device, dtype
        self.tokenizer = AutoTokenizer.from_pretrained(self.folder, padding_side="left",
                                                       local_files_only=True)
        self.net = AutoModelForCausalLM.from_pretrained(
            self.folder, dtype=getattr(torch, dtype), local_files_only=True).to(device).eval()
        self.yes_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.no_id = self.tokenizer.convert_tokens_to_ids("no")
        self.max_length = int(self.pin.extra.get("max_length") or 8192)
        self.prefix = f"<|im_start|>system\n{QWEN_SYSTEM}<|im_end|>\n<|im_start|>user\n"
        self.suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def scores(self, query: str, instruction: str, documents: list[str]) -> list[float]:
        torch = self.torch
        out: list[float] = []
        for start in range(0, len(documents), self.BATCH):
            texts = [f"{self.prefix}<Instruct>: {instruction}\n<Query>: {query}\n"
                     f"<Document>: {doc}{self.suffix}" for doc in documents[start:start + self.BATCH]]
            inputs = self.tokenizer(texts, padding=True, truncation=True,
                                    max_length=self.max_length, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                logits = self.net(**inputs, logits_to_keep=1).logits[:, -1, :]
            pair = torch.stack([logits[:, self.no_id], logits[:, self.yes_id]], dim=1)
            out += torch.nn.functional.log_softmax(pair.float(), dim=1)[:, 1].exp().tolist()
        return out

    def close(self) -> None:
        self.net = None


class KevServer(DecideBackend):
    """Kev through its own server, started once on a private port with the verified local copy
    (the adapter and its pinned base, in the same cache) and downloads turned off, and asked in
    System One's format. The checkpoint carries its fitted temperature, pinned by checksum, so
    none is set here. On a GTX 1060 a gate took 149 ms in fp16 (434 ms on a Ryzen 7 9700X)."""

    def load(self) -> None:
        import importlib.util
        if importlib.util.find_spec("kev") is None:
            raise RuntimeError("Kev is not installed in the model runtime: run `brain models "
                               "runtime` (Kev comes from github.com/jaredpalmer/kev; PyPI's "
                               "`kev` is an unrelated package)")
        self.port = free_port()
        self.device, dtype = place(float(self.pin.extra.get("size_gb") or 2.0))
        env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   HF_HUB_CACHE=modellock.cache_of(self.folder), KEV_DTYPE=kev_dtype(dtype))
        env.pop("KEV_TEMPERATURE", None)
        target = f"{self.pin.repository}@{self.pin.revision}"
        self.process = subprocess.Popen(
            [sys.executable, "-m", "kev.serve", "--run", target, "--port", str(self.port),
             "--host", "127.0.0.1", "--device", "auto" if self.device == "mps" else self.device],
            env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"kev.serve stopped with code {self.process.returncode}")
            with contextlib.suppress(OSError, ValueError):
                models_client._get(f"http://127.0.0.1:{self.port}/v1/models", 1.0)
                return
            time.sleep(1.0)
        raise RuntimeError("kev.serve did not start within ten minutes")

    def answers(self, state, questions: dict) -> dict:
        found = models_client._post(f"http://127.0.0.1:{self.port}/v1/systemone",
                                    {"model": "kev-latest", "state": state,
                                     "questions": questions}, models_client.CALL_TIMEOUT)
        return dict(found.get("answers") or {})

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            process.terminate()


class MiniLMReranker(RerankBackend):
    """MiniLM (ms-marco-MiniLM-L-6-v2), the small reranker, from its pinned ONNX file on the
    CPU: a cross-encoder's logit per (request, passage), as a probability. It reads words more
    than meaning, and it is fast: 50 passages in under 0.1 s on a Ryzen 7 9700X, where
    Qwen3-Reranker took 16 s on the same CPU. The reranker of machines without a GPU."""

    MAX_TOKENS = 512

    def load(self) -> None:
        import onnxruntime
        from tokenizers import Tokenizer
        self.device = "cpu"
        self.tokenizer = Tokenizer.from_file(os.path.join(self.folder, "tokenizer.json"))
        self.tokenizer.enable_truncation(self.MAX_TOKENS)
        self.tokenizer.enable_padding()
        self.session = onnxruntime.InferenceSession(
            os.path.join(self.folder, "onnx", "model.onnx"), providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}

    def scores(self, query: str, instruction: str, documents: list[str]) -> list[float]:
        import math

        import numpy
        found = self.tokenizer.encode_batch([(query, doc) for doc in documents])
        feed = {"input_ids": [e.ids for e in found],
                "attention_mask": [e.attention_mask for e in found],
                "token_type_ids": [e.type_ids for e in found]}
        logits = self.session.run(None, {name: numpy.array(rows, dtype=numpy.int64)
                                         for name, rows in feed.items()
                                         if name in self.inputs})[0]
        return [1.0 / (1.0 + math.exp(-float(row[0]))) for row in logits]

    def close(self) -> None:
        self.session = None


BACKENDS = {"qwen3-reranker-0.6b": QwenReranker, "ms-marco-minilm-l-6-v2": MiniLMReranker,
            "kev-0.8b": KevServer, "kev-4b": KevServer,
            "kev-9b": KevServer, "qwen3.5-4b": _agent_backend, "qwen3.5-9b": _agent_backend,
            "qwen3.8-27b": _agent_backend, "qwen3.6-35b-a3b": _agent_backend}
SERVED = ("rerank", "decide", "agent")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def snapshot(models_dir: str, pin: modellock.Pin) -> str:
    """The folder of a model's pinned revision in a Hugging Face style cache, or ""."""
    return modellock.snapshot(models_dir, pin.repository, pin.revision)


class ModelService:
    """The models this machine may run, verified against the lock and loaded once each.

    `factories` maps a model name to what builds its backend (tests pass stand-ins); the lock
    still decides: a model it does not list, or whose files do not match, never loads."""

    def __init__(self, lock: modellock.Lock | None = None, models_dir: str | None = None,
                 factories: dict | None = None, choose: dict | None = None):
        self.lock = lock or modellock.Lock.load()
        self.models_dir = models_dir or os.path.join(models_client.model_home(), "models")
        self.factories = dict(BACKENDS if factories is None else factories)
        self.wanted = dict(choose or {})  # role: model name, before this machine's choices
        self.choose: dict = {}
        self.backends: dict[str, Backend] = {}
        self.roles: dict[str, dict] = {}
        self.started = time.time()

    def prepare(self) -> dict:
        """Verify and load one model per role. Returns {role: health row}."""
        from . import machine
        self.settings = machine.load()
        self.setup = machine.setup_of(self.settings)
        self.choose = {}
        for role in SERVED:
            named = machine.chosen(role, self.settings, self.lock)
            if self.wanted.get(role):
                self.choose[role] = self.wanted[role]  # the lock still refuses what it lacks
            elif named and named in self.lock.pins:
                self.choose[role] = named
            elif not named and role in machine.SETUPS[self.setup]["models"]:
                self.choose[role] = None  # this setup runs no model for the role
        self.close()
        for role in SERVED:
            self.roles[role] = self._prepare(role)
        return self.roles

    def reload(self) -> dict:
        return self.prepare()

    def _prepare(self, role: str) -> dict:
        wanted = self.choose.get(role)
        if role in self.choose and wanted is None:
            return {"model": None, "verified": False, "loaded": False,
                    "reason": f"this computer's setup ({self.setup}) runs no {role} model"}
        try:
            pin = self.lock.pin(wanted) if wanted else next(
                (p for p in self.lock.for_role(role) if p.default), None)
        except modellock.Refused as exc:
            return {"model": wanted, "verified": False, "loaded": False, "reason": str(exc)}
        if pin is None:
            return {"model": None, "verified": False, "loaded": False,
                    "reason": f"the lock names no default {role} model"}
        if pin.role != role:
            return {"model": pin.name, "verified": False, "loaded": False,
                    "reason": f"{pin.name} is a {pin.role} model, not a {role} model"}
        folder = snapshot(self.models_dir, pin) or os.path.join(self.models_dir, pin.name)
        verdict = self.lock.verify(pin.name, folder)
        row = {"model": pin.name, "verified": verdict.ok, "loaded": False,
               "reason": verdict.reason}
        if not verdict.ok:
            return row
        factory = self.factories.get(pin.name)
        if factory is None:
            row["reason"] = f"no backend runs {pin.name} here"
            return row
        try:
            backend = factory(pin, folder)
            backend.load()
        except Exception as exc:  # a model that cannot run here: said, never fatal
            row["reason"] = f"{pin.name} could not load: {exc}"
            return row
        self.backends[role] = backend
        row.update(loaded=True, reason="")
        return row

    def health(self) -> dict:
        from . import machine
        decider = (self.roles.get("decide") or {}).get("model")
        settings = getattr(self, "settings", {})
        return {"lock": self.lock.fingerprint, "roles": self.roles,
                "setup": getattr(self, "setup", ""),
                "ceiling": machine.SETUPS.get(getattr(self, "setup", ""), {}).get("ceiling"),
                "qualified": {step: machine.qualified(decider, step, settings, self.lock)
                              for step in machine.STEPS},
                "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started))}

    def generate(self, body: dict) -> dict:
        backend = self._backend("agent", body)
        schema = body.get("schema") if isinstance(body.get("schema"), dict) else None
        started = time.perf_counter()
        text = backend.generate(str(body.get("system") or ""), str(body.get("prompt") or ""),
                                schema, int(body.get("max_tokens") or 800))
        found = None
        if schema:
            try:
                found = json.loads(text)
            except ValueError:
                found = None
        return {"model": backend.model, "text": text, "json": found,
                "problems": schema_problems(found, schema) if schema else [],
                "usage": dict(getattr(backend, "usage", None) or {}),
                "latency_ms": round((time.perf_counter() - started) * 1000, 1)}

    def rerank(self, body: dict) -> dict:
        backend = self._backend("rerank", body)
        documents = [str(d) for d in body.get("documents") or []]
        started = time.perf_counter()
        scores = backend.scores(str(body.get("query") or ""), str(body.get("instruction") or ""),
                                documents) if documents else []
        return {"model": backend.model, "latency_ms": round((time.perf_counter() - started)
                                                            * 1000, 1),
                "results": [{"index": i, "relevance_score": round(float(s), 6)}
                            for i, s in enumerate(scores)]}

    def decide(self, body: dict) -> dict:
        backend = self._backend("decide", body)
        questions = body.get("questions") or {}
        if not isinstance(questions, dict):
            raise ValueError("questions is an object keyed by question id")
        for name, question in questions.items():
            kind = (question or {}).get("type")
            if kind not in ("noul", "choice", "score"):
                raise ValueError(f"{name}: a question is noul, choice or score")
            options = (question or {}).get("criteria")
            if kind in ("choice", "score") and not 1 <= len(options or ()) <= 255:
                raise ValueError(f"{name}: a {kind} question takes 1 to 255 options")
        started = time.perf_counter()
        answers = backend.answers(body.get("state"), questions)
        return {"model": backend.model, "answers": answers,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "usage": {"input_tokens": 0, "output_tokens": 0}}

    def _backend(self, role: str, body: dict) -> Backend:
        backend = self.backends.get(role)
        if backend is None:
            raise Unavailable((self.roles.get(role) or {}).get("reason")
                              or f"no {role} model is loaded")
        asked = str(body.get("model") or "").strip()
        if asked and asked != backend.model:
            raise Unavailable(f"{asked} is not the {role} model this service runs "
                              f"({backend.model})")
        return backend

    def close(self) -> None:
        for backend in self.backends.values():
            with contextlib.suppress(Exception):
                backend.close()
        self.backends.clear()


class Unavailable(Exception):
    """A role with no verified, loaded model."""


def handler_for(service: ModelService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "brainkit-models/1"

        def log_message(self, *_args):  # quiet: the engine's ledger is the record
            return

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.rstrip("/") == "/v1/health":
                self._send(200, service.health())
            else:
                self._send(404, {"error": f"no {self.path}"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(413, {"error": "request too large"})
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if self.path.rstrip("/") == "/v1/rerank":
                    self._send(200, service.rerank(body))
                elif self.path.rstrip("/") == "/v1/systemone":
                    self._send(200, service.decide(body))
                elif self.path.rstrip("/") == "/v1/generate":
                    self._send(200, service.generate(body))
                elif self.path.rstrip("/") == "/v1/reload":
                    service.reload()
                    models_client.forget()
                    self._send(200, service.health())
                else:
                    self._send(404, {"error": f"no {self.path}"})
            except Unavailable as exc:
                self._send(503, {"error": str(exc)})
            except (ValueError, TypeError) as exc:
                self._send(422, {"error": str(exc)})
            except Exception as exc:  # a backend failure answers, never hangs the client
                self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


class Running:
    """A started service: its address, and how to stop it."""

    def __init__(self, service: ModelService, server: ThreadingHTTPServer, discovery: str):
        self.service = service
        self.server = server
        self.discovery = discovery
        self.url = f"http://127.0.0.1:{server.server_address[1]}"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.service.close()
        if self.discovery:
            with contextlib.suppress(OSError):
                with open(self.discovery, encoding="utf-8") as handle:
                    mine = json.load(handle).get("pid") == os.getpid()
                if mine:
                    os.remove(self.discovery)


def start(service: ModelService, port: int = 0, *, announce: bool = True) -> Running:
    """Prepare the models and serve them on 127.0.0.1 in a background thread."""
    service.prepare()
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_for(service))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    discovery = ""
    if announce:
        discovery = os.path.join(models_client.model_home(), models_client.DISCOVERY)
        os.makedirs(os.path.dirname(discovery), exist_ok=True)
        with open(discovery, "w", encoding="utf-8") as handle:
            json.dump({"url": f"http://127.0.0.1:{server.server_address[1]}",
                       "pid": os.getpid(), "lock": service.lock.fingerprint,
                       "roles": service.roles}, handle, indent=1)
    models_client.forget()
    return Running(service, server, discovery)


def running() -> bool:
    """Is a service already answering at the discovered address?"""
    url = models_client.address()
    if not url:
        return False
    try:
        models_client._get(f"{url}/v1/health", models_client.HEALTH_TIMEOUT)
        return True
    except (OSError, ValueError):
        return False


def ensure(python: str | None = None) -> str:
    """Start the service in its own process unless one answers already (the app calls this when
    it starts). Returns what happened, in words."""
    if os.environ.get("BRAIN_MODEL_SERVICE", "").strip().lower() in ("off", "0", "none", "false"):
        return "the model service is off (BRAIN_MODEL_SERVICE)"
    if running():
        return f"the model service is running at {models_client.address()}"
    from . import machine
    settings, lock = machine.load(), modellock.Lock.load()
    missing = [role for role in models_client.NEEDED
               if not machine.here(machine.chosen(role, settings, lock), lock)]
    if missing:
        return ("the local models for this computer's setup are not downloaded yet ("
                + ", ".join(machine.ROLE_WORDS[r] for r in missing)
                + "): retrieval runs on words and meaning")
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    subprocess.Popen([python or sys.executable, "-m", "brainkit.modelservice"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, creationflags=flags)
    return "the model service is starting"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The local model service (127.0.0.1 only).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--models", default=None, help="the folder pinned models live in")
    args = parser.parse_args(argv)
    service = ModelService(models_dir=args.models)
    handle = start(service, args.port)
    rows = ", ".join(f"{role}: {row.get('model')} "
                     f"({'ready' if row.get('loaded') else row.get('reason')})"
                     for role, row in service.roles.items())
    print(f"Model service on {handle.url} (lock {service.lock.fingerprint}); {rows}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        handle.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
