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
- On start it writes `<model home>/modelservice.json` (its address, process and lock), which is
  how every client finds it; it removes the file when it stops.

Backends: Qwen3-Reranker through transformers (CUDA, or MPS on a Mac), and Kev through its own
server (`python -m kev.serve`), started once on a private port with the verified local copy and
no downloads. Both import their libraries only when a verified model needs them, so on a machine
without models the service runs, says so, and the engine falls back. Tests pass stand-ins.
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
ROLES = ("rerank", "decide")
MAX_BODY = 32 * 1024 * 1024  # bytes in one request
QWEN_SYSTEM = ("Judge whether the Document meets the requirements based on the Query and the "
               "Instruct provided. Note that the answer can only be \"yes\" or \"no\".")


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


class QwenReranker(RerankBackend):
    """Qwen3-Reranker: the probability that the answer to "does the document meet the request,
    given the instruction?" is yes, read from the model's next-token logits for "yes" and "no",
    as its model card shows. Not run on a machine without a GPU or Apple Silicon."""

    BATCH = 8

    def load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            raise RuntimeError("no CUDA or Apple GPU: the reranker does not run on this CPU")
        dtype = getattr(torch, self.pin.dtype or "bfloat16", torch.bfloat16)
        self.torch = torch
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(self.folder, padding_side="left",
                                                       local_files_only=True)
        self.net = AutoModelForCausalLM.from_pretrained(
            self.folder, torch_dtype=dtype, local_files_only=True).to(device).eval()
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
                logits = self.net(**inputs).logits[:, -1, :]
            pair = torch.stack([logits[:, self.no_id], logits[:, self.yes_id]], dim=1)
            out += torch.nn.functional.log_softmax(pair.float(), dim=1)[:, 1].exp().tolist()
        return out

    def close(self) -> None:
        self.net = None


class KevServer(DecideBackend):
    """Kev through its own server, started once on a private port with the verified local copy
    and downloads turned off, and asked in System One's format. Not run where Kev cannot."""

    def load(self) -> None:
        import importlib.util
        if importlib.util.find_spec("kev") is None:
            raise RuntimeError("the kev package is not installed (pip install kev[serve])")
        self.port = free_port()
        env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   HF_HUB_CACHE=os.path.dirname(os.path.dirname(os.path.dirname(self.folder))))
        temperature = self.pin.extra.get("temperature")
        if temperature:
            env["KEV_TEMPERATURE"] = str(temperature)
        target = f"{self.pin.repository}@{self.pin.revision}"
        self.process = subprocess.Popen(
            [sys.executable, "-m", "kev.serve", "--run", target, "--port", str(self.port),
             "--host", "127.0.0.1"], env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
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


BACKENDS = {"qwen3-reranker-0.6b": QwenReranker, "kev-4b": KevServer, "kev-9b": KevServer}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def snapshot(models_dir: str, pin: modellock.Pin) -> str:
    """The folder of a model's pinned revision in a Hugging Face style cache, or ""."""
    if not pin.revision or not pin.repository:
        return ""
    base = os.path.join(models_dir, "models--" + pin.repository.replace("/", "--"), "snapshots")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return ""
    found = [n for n in names if n.startswith(pin.revision) or pin.revision.startswith(n)]
    return os.path.join(base, found[0]) if found else ""


class ModelService:
    """The models this machine may run, verified against the lock and loaded once each.

    `factories` maps a model name to what builds its backend (tests pass stand-ins); the lock
    still decides: a model it does not list, or whose files do not match, never loads."""

    def __init__(self, lock: modellock.Lock | None = None, models_dir: str | None = None,
                 factories: dict | None = None, choose: dict | None = None):
        self.lock = lock or modellock.Lock.load()
        self.models_dir = models_dir or os.path.join(models_client.model_home(), "models")
        self.factories = dict(BACKENDS if factories is None else factories)
        self.choose = dict(choose or {})  # role: model name, else the lock's default
        self.backends: dict[str, Backend] = {}
        self.roles: dict[str, dict] = {}
        self.started = time.time()

    def prepare(self) -> dict:
        """Verify and load one model per role. Returns {role: health row}."""
        for role in ROLES:
            self.roles[role] = self._prepare(role)
        return self.roles

    def _prepare(self, role: str) -> dict:
        wanted = self.choose.get(role)
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
        return {"lock": self.lock.fingerprint, "roles": self.roles,
                "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started))}

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
