"""Talking to the local model service: finding it, trusting it, and the two adapters.

The retrieval engine (brain-logic plan 5.11) runs its models in one local service, shared by
the engine, the app and every MCP session (`brainkit/modelservice.py`). This module is the
engine's side of it:

- FINDING IT. `BRAIN_MODEL_SERVICE` names its address (or "off"); otherwise the discovery file
  the service writes when it starts (`<model home>/modelservice.json`).
- TRUSTING IT. The service is "ready" only when its lock fingerprint is this engine's and the
  roles the engine needs (rerank, decide) are each served by a model the lock verified. Anything
  else, and retrieval falls back to code and the meaning index, exactly as without the engine.
- THE ADAPTERS. Relevance scores go through a rerank interface (a query, an instruction and
  documents in; a score from 0 to 1 per document out), so the reranker can change without code
  changes. Decisions go through System One, the request format Jev defined and Kev and Laya
  speak: `{"model", "state", "questions"}` in, answers keyed by question out (a `noul` answer
  is the probability of yes; a `choice` answer carries every option's probability).

Nothing here downloads or loads a model, and every call has a short timeout: a slow or absent
service costs a request a fraction of a second, never its brief.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import modellock

HEALTH_TTL = 5.0       # seconds a health answer is trusted for
HEALTH_TIMEOUT = 0.5   # seconds to wait for the service's health
CALL_TIMEOUT = 20.0    # seconds to wait for scores or answers
NEEDED = ("rerank", "decide")
DISCOVERY = "modelservice.json"


def model_home() -> str:
    """Where this machine's local models and the service's discovery file live."""
    return os.path.abspath(os.environ.get("BRAIN_MODEL_HOME")
                           or os.path.join(os.path.expanduser("~"), ".brainkit"))


@dataclass
class Status:
    """What the engine knows about the model service right now."""
    url: str = ""
    ready: bool = False
    reason: str = ""
    lock: str = ""               # the service's lock fingerprint
    roles: dict = field(default_factory=dict)  # role: {"model", "verified", "loaded", "reason"}

    @property
    def models(self) -> dict:
        return {role: (info or {}).get("model") for role, info in self.roles.items()}


_cache: dict[str, tuple[float, Status]] = {}
_lock = threading.Lock()


def address() -> str:
    """The service's base URL, "" when none is named or found ("off" turns it off)."""
    named = str(os.environ.get("BRAIN_MODEL_SERVICE") or "").strip()
    if named.lower() in ("off", "0", "none", "false"):
        return ""
    if named:
        return named.rstrip("/")
    try:
        with open(os.path.join(model_home(), DISCOVERY), encoding="utf-8") as handle:
            found = json.load(handle)
    except (OSError, ValueError):
        return ""
    url = str(found.get("url") or "")
    return url.rstrip("/") if url.startswith("http://127.0.0.1:") else ""


def status(*, refresh: bool = False, lock: modellock.Lock | None = None) -> Status:
    """Is a verified model service ready for the engine? Cached for a few seconds."""
    url = address()
    if not url:
        return Status(reason="no model service is running")
    now = time.monotonic()
    with _lock:
        cached = _cache.get(url)
        if cached and not refresh and now - cached[0] < HEALTH_TTL:
            return cached[1]
    found = _check(url, lock or modellock.Lock.load())
    with _lock:
        _cache[url] = (now, found)
    return found


def forget() -> None:
    """Drop cached health answers (a test, or after the service restarts)."""
    with _lock:
        _cache.clear()


def _check(url: str, lock: modellock.Lock) -> Status:
    try:
        health = _get(f"{url}/v1/health", HEALTH_TIMEOUT)
    except (OSError, ValueError) as exc:
        return Status(url=url, reason=f"the model service at {url} did not answer ({exc})")
    roles = dict(health.get("roles") or {})
    theirs = str(health.get("lock") or "")
    if theirs != lock.fingerprint:
        return Status(url=url, lock=theirs, roles=roles,
                      reason=f"the model service runs lock {theirs or 'unknown'}, this engine "
                             f"{lock.fingerprint}: refused")
    missing = [role for role in NEEDED
               if not ((roles.get(role) or {}).get("verified")
                       and (roles.get(role) or {}).get("loaded"))]
    if missing:
        why = "; ".join(f"{role}: {(roles.get(role) or {}).get('reason') or 'no model'}"
                        for role in missing)
        return Status(url=url, lock=theirs, roles=roles,
                      reason=f"the model service has no verified model for {why}")
    for role in NEEDED:
        model = str((roles.get(role) or {}).get("model") or "")
        try:
            lock.pin(model)
        except modellock.Refused as exc:
            return Status(url=url, lock=theirs, roles=roles, reason=str(exc))
    return Status(url=url, ready=True, lock=theirs, roles=roles)


def _get(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def _post(url: str, body: dict, timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ServiceError(f"{url}: {exc.code} {detail}") from exc


class ServiceError(Exception):
    """The service could not answer a call; the engine falls back for that request."""


class Reranker:
    """Relevance scores through the rerank interface."""

    def __init__(self, service: Status):
        self.url = service.url
        self.model = str((service.roles.get("rerank") or {}).get("model") or "")

    def scores(self, query: str, documents: list[str], instruction: str) -> list[float]:
        if not documents:
            return []
        found = _post(f"{self.url}/v1/rerank", {"model": self.model, "query": query,
                                                "instruction": instruction,
                                                "documents": documents}, CALL_TIMEOUT)
        out = [0.0] * len(documents)
        for row in found.get("results") or []:
            index = int(row.get("index", -1))
            if 0 <= index < len(out):
                out[index] = float(row.get("relevance_score") or 0.0)
        return out


class Decider:
    """Decisions in System One's format (Kev, Laya and Jev all speak it)."""

    def __init__(self, service: Status):
        self.url = service.url
        self.model = str((service.roles.get("decide") or {}).get("model") or "")

    def ask(self, state, questions: dict) -> dict:
        """{question id: answer} for typed questions over one shared state."""
        if not questions:
            return {}
        found = _post(f"{self.url}/v1/systemone", {"model": self.model, "state": state,
                                                   "questions": questions}, CALL_TIMEOUT)
        return dict(found.get("answers") or {})


def noul(instructions: str, *, yes: str = "", no: str = "") -> dict:
    """A yes/no question; its answer is the probability of yes."""
    question: dict = {"type": "noul", "instructions": instructions}
    if yes or no:
        question["criteria"] = {"true": yes or None, "false": no or None}
    return question


def choice(instructions: str, options: dict) -> dict:
    """A question whose answer is one of `options` ({name: description}), in a fixed order:
    option order can change an answer, so callers always pass them the same way."""
    if not 1 <= len(options) <= 255:
        raise ValueError("a choice question takes 1 to 255 options")
    return {"type": "choice", "instructions": instructions, "criteria": dict(options)}


def yes(answer: dict | None) -> float:
    """The probability of yes in a `noul` answer (0 when there is none)."""
    try:
        return float((answer or {}).get("noul") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def probabilities(answer: dict | None) -> dict:
    """Every option's probability in a `choice` answer."""
    found = (answer or {}).get("probabilities") or {}
    return {str(k): float(v) for k, v in found.items()} if isinstance(found, dict) else {}
