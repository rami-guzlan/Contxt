"""This computer: what it can run, the setup it gets, and the person's model choices
(brain-logic plan 5.11.15 and 5.11.16).

At first run, and whenever the person asks, the app reads the machine (RAM, an NVIDIA GPU and
its memory, Apple Silicon or not) and picks the setup that fits:

    laptop        16 GB of RAM, no GPU with 12 GB or more: the solo default
    workstation   an NVIDIA GPU with 12 GB or more, or a Mac with 32 GB or more
    large         a GPU with 24 GB or more, or a Mac with 64 GB or more
    small         under 16 GB: code alone, bge-small and MiniLM; no local decision model or agent

Each setup names a default model per role (meaning, reranker, decisions, knowledge agent), all
pinned in the lock. The person can make any pinned option the default for its role, unless the
RAM check says it will not fit (refused, with the reason); one slower than the speed budget gets
a warning and is allowed. The choices, the speed and quality measured here, and which Kev steps
qualified live in this machine's settings (`<model home>/settings.json`), never in a Brain.

Kev-0.8B, the laptop's decision model, is the weakest: each of its steps (the gate, the second
pass) runs only once it passed that step's bars in the comparison. Until then the gate falls
back to the reranker's best score against the cut, and the second pass is skipped. The lock
names the steps a model must qualify for (`extra.qualify`); a model it names none for runs them
all.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass

from . import modellock, models_client, util

ROLES = ("embed", "rerank", "decide", "agent")
ROLE_WORDS = {"embed": "meaning", "rerank": "reranker", "decide": "decisions",
              "agent": "knowledge agent"}
SETUPS = {
    "small": {"label": "Under 16 GB", "ceiling": 100,
              "models": {"embed": "bge-small-en-v1.5", "rerank": "ms-marco-minilm-l-6-v2",
                         "decide": None, "agent": None}},
    "laptop": {"label": "Laptop", "ceiling": 100,
               "models": {"embed": "bge-small-en-v1.5", "rerank": "qwen3-reranker-0.6b",
                          "decide": "kev-0.8b", "agent": "qwen3.5-4b"}},
    "workstation": {"label": "Workstation", "ceiling": 300,
                    "models": {"embed": "bge-small-en-v1.5", "rerank": "qwen3-reranker-0.6b",
                               "decide": "kev-4b", "agent": "qwen3.5-9b"}},
    "large": {"label": "Large workstation", "ceiling": 300,
              "models": {"embed": "bge-small-en-v1.5", "rerank": "qwen3-reranker-0.6b",
                         "decide": "kev-9b", "agent": "qwen3.6-35b-a3b"}},
}
# What the operating system, a browser and the app hold, plus room to spare, on a machine whose
# models share its RAM: on 16 GB that leaves about 6 GB for models (5.11.7, 5.11.13).
RESERVE_GB = 9.5
GPU_HEADROOM_GB = 1.0
STEPS = ("gate", "second_pass")  # the Kev steps a weak decision model must qualify for
SETTINGS = "settings.json"
# The speed budget per step (5.11.7, p50 in milliseconds): starting targets that the first
# measurements on the reference machines set for real. A role is held to its step's budget.
BUDGETS_MS = {
    "gpu": {"gate": 60, "cut": 300, "second_pass": 150, "brief_p95": 1000},
    "mac": {"gate": 150, "cut": 800, "second_pass": 400, "brief_p95": 2000},
    "laptop_mac": {"gate": 200, "cut": 1200, "second_pass": 500, "brief_p95": 3000},
    "laptop_windows": {"gate": 600, "cut": 2000, "second_pass": 1500, "brief_p95": 5000},
}
ROLE_STEP = {"rerank": "cut", "decide": "gate"}
SPEED_PASSAGES = 50  # what the reranker scores in the speed check: a typical candidate set
# No default is offered that the RAM check says will not fit (5.11.13). When a setup's defaults
# do not fit, these give way in order: the small reranker, then the local agent (Claude Code
# can stand in), then the local decision model.
GIVE_WAY = (("rerank", "ms-marco-minilm-l-6-v2"), ("agent", None), ("decide", None))
SMALL_RERANKER = "ms-marco-minilm-l-6-v2"
MEANING_INDEX = "bge-small-en-v1.5"  # kept with the Brain (vault/.brain/models), not here
_detected: list = []  # this process's reading of the machine; `check` reads it again


@dataclass
class Machine:
    ram_gb: float
    gpu: str = ""
    gpu_gb: float = 0.0
    apple_silicon: bool = False
    system: str = ""

    @property
    def setup(self) -> str:
        if self.gpu_gb >= 24 or (self.apple_silicon and self.ram_gb >= 63):
            return "large"
        if self.gpu_gb >= 12 or (self.apple_silicon and self.ram_gb >= 31):
            return "workstation"
        if self.ram_gb >= 15:  # a 16 GB machine reports a little less
            return "laptop"
        return "small"

    @property
    def gpu_runs_models(self) -> bool:
        """Do the models load into a GPU's own memory (an NVIDIA GPU with room), rather than
        the RAM the system shares (Apple Silicon, or no GPU)?"""
        return self.gpu_gb >= 12


def budget(machine: Machine) -> dict:
    """This machine's speed budget per step (5.11.7)."""
    if machine.gpu_runs_models:
        return BUDGETS_MS["gpu"]
    if machine.apple_silicon:
        return BUDGETS_MS["mac"] if machine.ram_gb >= 31 else BUDGETS_MS["laptop_mac"]
    return BUDGETS_MS["laptop_windows"]


def detect(*, refresh: bool = False) -> Machine:
    """Read this computer: its RAM, an NVIDIA GPU and its memory, Apple Silicon or not (once a
    process, unless asked again)."""
    if _detected and not refresh:
        return _detected[0]
    system = platform.system()
    gpu, gpu_gb = _nvidia()
    found = Machine(ram_gb=round(_ram_gb(), 1), gpu=gpu, gpu_gb=gpu_gb,
                    apple_silicon=system == "Darwin" and platform.machine() == "arm64",
                    system=system)
    _detected[:] = [found]
    return found


def _ram_gb() -> float:
    system = platform.system()
    try:
        if system == "Windows":
            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            ("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                            ("page_total", ctypes.c_ulonglong),
                            ("page_free", ctypes.c_ulonglong),
                            ("virtual_total", ctypes.c_ulonglong),
                            ("virtual_free", ctypes.c_ulonglong),
                            ("extended", ctypes.c_ulonglong)]
            status = Status()
            status.length = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
            return status.total / 2 ** 30
        if system == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                 timeout=5)
            return int(out.stdout.strip()) / 2 ** 30
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 2 ** 20
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        pass
    return 0.0


def _nvidia() -> tuple[str, float]:
    """The largest NVIDIA GPU and its memory in GB, ("", 0) when there is none."""
    tool = shutil.which("nvidia-smi")
    if not tool:
        return "", 0.0
    try:
        out = subprocess.run([tool, "--query-gpu=name,memory.total",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "", 0.0
    best = ("", 0.0)
    for line in out.stdout.splitlines():
        name, _sep, memory = line.rpartition(",")
        try:
            gb = float(memory.strip()) / 1024
        except ValueError:
            continue
        if gb > best[1]:
            best = (name.strip(), round(gb, 1))
    return best


# ---------------------------------------------------------------------------- choices

def settings_path() -> str:
    return os.path.join(models_client.model_home(), SETTINGS)


def load() -> dict:
    """This machine's settings: the machine found, the setup, the person's choices, what was
    measured here and which Kev steps qualified."""
    try:
        with open(settings_path(), encoding="utf-8") as handle:
            found = json.load(handle)
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def save(settings: dict) -> None:
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    util.atomic_write(path, json.dumps(settings, indent=1) + "\n")


def check(machine: Machine | None = None) -> dict:
    """Read the machine again and keep what was found (the person's choices stay)."""
    machine = machine or detect(refresh=True)
    settings = load()
    settings["machine"] = asdict(machine)
    settings["setup"] = machine.setup
    settings["checked_at"] = util.now_iso()
    save(settings)
    return settings


def machine_of(settings: dict) -> Machine:
    found = settings.get("machine") or {}
    if not found:
        return detect()
    return Machine(**{k: found[k] for k in ("ram_gb", "gpu", "gpu_gb", "apple_silicon",
                                             "system") if k in found})


def setup_of(settings: dict) -> str:
    setup = str(settings.get("setup") or "")
    return setup if setup in SETUPS else machine_of(settings).setup


def chosen(role: str, settings: dict | None = None,
           lock: modellock.Lock | None = None) -> str | None:
    """The model a role runs here: the person's choice, else the setup's default (made to fit
    this machine's RAM)."""
    settings = load() if settings is None else settings
    picked = (settings.get("models") or {}).get(role)
    if picked:
        return str(picked)
    return setup_models(settings, lock)[0].get(role)


def setup_models(settings: dict, lock: modellock.Lock | None = None) -> tuple[dict, list[str]]:
    """The setup's default model per role, made to fit this machine's RAM, and what gave way,
    in words."""
    models = dict(SETUPS[setup_of(settings)]["models"])
    lock = lock or modellock.Lock.load()
    machine = machine_of(settings)
    gave = []
    for role, smaller in GIVE_WAY:
        if fits(models, machine, lock)[0]:
            break
        was = models.get(role)
        if was == smaller or was is None:
            continue
        models[role] = smaller
        gave.append(f"{was} does not fit beside the other defaults here: the "
                    f"{ROLE_WORDS[role]} model is {smaller}" if smaller else
                    f"{was} does not fit beside the other defaults here: no local "
                    f"{ROLE_WORDS[role]} model")
    return models, gave


def ceiling(settings: dict | None = None) -> int:
    """The candidate ceiling that only protects speed: lower on a laptop (5.11.7)."""
    settings = load() if settings is None else settings
    return int(SETUPS[setup_of(settings)]["ceiling"])


def ram_gb(name: str | None, lock: modellock.Lock) -> float:
    if not name:
        return 0.0
    try:
        return float(lock.pin(name).extra.get("ram_gb") or 0.0)
    except (modellock.Refused, TypeError, ValueError):
        return 0.0


def fits(models: dict, machine: Machine, lock: modellock.Lock) -> tuple[bool, str]:
    """Will these models fit this machine? (False, why) when the RAM check says no."""
    total = round(sum(ram_gb(name, lock) for name in models.values()), 1)
    if machine.gpu_runs_models:
        # The models load into the GPU first and spill into spare system RAM, slower.
        room = round(machine.gpu_gb - GPU_HEADROOM_GB + max(0.0, machine.ram_gb - RESERVE_GB),
                     1)
        where = (f"the GPU's {machine.gpu_gb:g} GB and spare RAM of {machine.ram_gb:g} GB, less "
                 f"about {RESERVE_GB:g} GB for the system")
    else:
        room = round(machine.ram_gb - RESERVE_GB, 1)
        where = f"{machine.ram_gb:g} GB of RAM, less about {RESERVE_GB:g} GB for the system"
    if total > room:
        return False, (f"these models need about {total:g} GB and this computer has room for "
                       f"about {room:g} GB ({where})")
    return True, ""


def choose(role: str, name: str, *, lock: modellock.Lock | None = None) -> dict:
    """Make a pinned model the default for its role here. Refused (ValueError) when the lock
    does not list it, it serves another role, or the RAM check says it will not fit; one that
    measured slower than this machine's budget is allowed, with a warning. Returns
    {"role", "model", "warning"}."""
    if role not in ROLES:
        raise ValueError(f"a role is one of {', '.join(ROLES)}")
    lock = lock or modellock.Lock.load()
    pin = lock.pin(name)  # Refused when unlisted
    if pin.role != role:
        raise ValueError(f"{name} is a {ROLE_WORDS.get(pin.role, pin.role)} model, not a "
                         f"{ROLE_WORDS[role]} model")
    settings = load()
    machine = machine_of(settings)
    models = {r: chosen(r, settings, lock) for r in ROLES}
    models[role] = name
    ok, why = fits(models, machine, lock)
    if not ok:
        raise ValueError(f"{name} will not fit: {why}")
    settings.setdefault("models", {})[role] = name
    save(settings)
    return {"role": role, "model": name, "warning": slow(name, role, settings, machine)}


def slow(name: str, role: str, settings: dict, machine: Machine) -> str:
    """A warning when a model measured slower here than its step's budget, else ""."""
    step = ROLE_STEP.get(role)
    speed = ((settings.get("measured") or {}).get(name) or {}).get("speed_ms")
    if not step or speed is None:
        return ""
    limit = budget(machine)[step]
    if float(speed) <= limit:
        return ""
    advice = (f"; {SMALL_RERANKER} is the faster reranker here"
              if role == "rerank" and name != SMALL_RERANKER and not machine.gpu_runs_models
              else "")
    return (f"{name} measured {float(speed):g} ms here, slower than this machine's budget of "
            f"{limit} ms for the {'relevance cut' if step == 'cut' else step}: allowed, and "
            f"briefs will be slower{advice}")


def must_qualify(decider: str | None, lock: modellock.Lock) -> list[str]:
    """The Kev steps this decision model runs only once it qualified for them here."""
    try:
        steps = lock.pin(str(decider or "")).extra.get("qualify") or []
    except modellock.Refused:
        return []
    return [step for step in steps if step in STEPS]


def qualified(decider: str | None, step: str, settings: dict | None = None,
              lock: modellock.Lock | None = None) -> bool:
    """Does the decision model run this Kev step here (5.11.15)?"""
    if not decider:
        return False
    if step not in must_qualify(decider, lock or modellock.Lock.load()):
        return True
    settings = load() if settings is None else settings
    return bool(((settings.get("qualified") or {}).get(decider) or {}).get(step))


def fallbacks(decider: str | None, settings: dict, lock: modellock.Lock) -> list[str]:
    """What runs instead of each Kev step the decision model has not qualified for, in words."""
    out = []
    if decider and not qualified(decider, "gate", settings, lock):
        out.append(f"{decider} has not qualified for the gate here: the reranker's best score "
                   "against the cut decides instead")
    if decider and not qualified(decider, "second_pass", settings, lock):
        out.append(f"{decider} has not qualified for the second pass here: it is skipped")
    return out


def record(name: str, *, speed_ms: float | None = None, quality: float | None = None,
           steps: dict | None = None) -> dict:
    """Keep what the speed and quality checks measured for a model here, and which Kev steps it
    qualified for."""
    settings = load()
    measured = settings.setdefault("measured", {}).setdefault(name, {})
    if speed_ms is not None:
        measured["speed_ms"] = round(float(speed_ms), 1)
    if quality is not None:
        measured["quality"] = round(float(quality), 3)
    measured["at"] = util.now_iso()
    if steps:
        settings.setdefault("qualified", {}).setdefault(name, {}).update(
            {k: bool(v) for k, v in steps.items() if k in STEPS})
    save(settings)
    return settings


def set_agent_claude_code(on: bool) -> dict:
    """The person's opt-in: the knowledge agent may run through Claude Code, on their own plan.
    Its work then leaves this machine."""
    settings = load()
    settings["agent_claude_code"] = bool(on)
    save(settings)
    return settings


# ---------------------------------------------------------------------------- the files

def models_dir() -> str:
    return os.path.join(models_client.model_home(), "models")


def folder_of(pin: modellock.Pin) -> str:
    """Where a pinned model's files live here (a Hugging Face style cache, or its own folder)."""
    from .modelservice import snapshot
    home = models_dir()
    return snapshot(home, pin) or os.path.join(home, pin.name)


def here(name: str | None, lock: modellock.Lock) -> bool:
    """Is this model downloaded here and verified against the lock?"""
    if not name:
        return False
    try:
        return lock.verify(name, folder_of(lock.pin(name))).ok
    except modellock.Refused:
        return False


def download(name: str, *, lock: modellock.Lock | None = None, fetch=None) -> modellock.Verdict:
    """Fetch a pinned model at its pinned revision into this machine's model home, then verify
    it file by file against the lock; from then on it runs offline. Refused for a model the
    lock lists but has not pinned yet: nothing unpinned is ever fetched."""
    lock = lock or modellock.Lock.load()
    pin = downloadable(name, lock)
    (fetch or _fetch)(pin, models_dir())
    return lock.verify(name, folder_of(pin))


def downloadable(name: str, lock: modellock.Lock) -> modellock.Pin:
    """The pin to download, or Refused: unlisted, or listed without a revision and checksums."""
    pin = lock.pin(name)
    if not pin.pinned:
        raise modellock.Refused(
            f"{name} is listed but not pinned yet: its revision and file checksums are recorded "
            "on a machine that runs it (brain models pin), and then it can be downloaded")
    return pin


def _fetch(pin: modellock.Pin, cache: str) -> None:
    """Fetch a model's pinned files at its revision, and the base model it runs on, if any."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("downloading a model needs huggingface_hub (it comes with the "
                           "embeddings extra)") from exc
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    snapshot_download(repo_id=pin.repository, revision=pin.revision, cache_dir=cache,
                      allow_patterns=sorted(pin.files))
    if pin.base:
        snapshot_download(repo_id=pin.base["repository"], revision=pin.base["revision"],
                          cache_dir=cache, allow_patterns=sorted(pin.base["files"]))


def remove(name: str, *, lock: modellock.Lock | None = None) -> None:
    """Remove a downloaded model from this machine; it can be downloaded again. Refused for a
    model a role runs here: another becomes the default first."""
    lock = lock or modellock.Lock.load()
    pin = lock.pin(name)
    settings = load()
    for role in ROLES:
        if chosen(role, settings, lock) == name:
            raise ValueError(f"{name} is the {ROLE_WORDS[role]} model in use here: make another "
                             "the default first")
    home = models_dir()
    targets = [os.path.join(home, pin.name)]
    if pin.repository:
        targets.append(os.path.join(home, "models--" + pin.repository.replace("/", "--")))
    for target in targets:
        if os.path.isdir(target):
            shutil.rmtree(target)


# ---------------------------------------------------------------------------- the checks

def check_speed(found: models_client.Status | None = None, *, runs: int = 3) -> dict:
    """Time each model the service runs here, the median of a few runs: the reranker over a
    typical candidate set, the decision model on one gate question, the agent on one short
    answer. Keeps what it measured; says which miss this machine's budget."""
    found = found or models_client.status(refresh=True)
    if not found.url:
        raise ValueError("no model service is running here: download this setup's models first")
    settings = load()
    machine = machine_of(settings)
    passages = [f"[note-{i}] A passage about house style, prices or projects, number {i}."
                for i in range(SPEED_PASSAGES)]
    calls = {}
    roles = found.roles
    if (roles.get("rerank") or {}).get("loaded"):
        calls["rerank"] = lambda: models_client.Reranker(found).scores(
            "How should headlines be written?", passages, "Judge whether this note helps")
    if (roles.get("decide") or {}).get("loaded"):
        calls["decide"] = lambda: models_client.Decider(found).ask(
            {"request": "How should headlines be written?"},
            {"gate": models_client.noul("Would anything kept in this Brain help?")})
    if found.agent:
        calls["agent"] = lambda: models_client.Agent(found).generate("Say ok.", max_tokens=8)
    measured, slow_ones = {}, []
    for role, call in calls.items():
        times = []
        for _ in range(max(1, runs)):
            started = time.perf_counter()
            call()
            times.append((time.perf_counter() - started) * 1000)
        name = str(roles[role].get("model"))
        speed = sorted(times)[len(times) // 2]
        record(name, speed_ms=speed)
        measured[name] = round(speed, 1)
        warning = slow(name, role, load(), machine)
        if warning:
            slow_ones.append(warning)
    return {"measured": measured, "slow": slow_ones, "budget": budget(machine)}


def overview(lock: modellock.Lock | None = None, settings: dict | None = None) -> dict:
    """What Settings > On this computer > Local models shows: the machine, its setup, and per
    role the model in use and every pinned option with its size, RAM, what was measured here,
    whether it is downloaded and verified, and whether it would fit."""
    lock = lock or modellock.Lock.load()
    settings = load() if settings is None else settings
    machine = machine_of(settings)
    setup = setup_of(settings)
    defaults, gave = setup_models(settings, lock)
    in_use = {role: chosen(role, settings, lock) for role in ROLES}
    roles = []
    for role in ROLES:
        options = []
        for pin in sorted(lock.for_role(role), key=lambda p: (float(p.extra.get("ram_gb") or 0),
                                                              p.name)):
            verdict = lock.verify(pin.name, folder_of(pin))
            trial = dict(in_use, **{role: pin.name})
            ok, why = fits(trial, machine, lock)
            options.append({
                "name": pin.name, "repository": pin.repository,
                "revision": pin.revision or None, "pinned": pin.pinned,
                "size_gb": pin.extra.get("size_gb"), "ram_gb": pin.extra.get("ram_gb"),
                "license": pin.extra.get("license"),
                "downloaded": verdict.ok, "why_not": "" if verdict.ok else verdict.reason,
                "fits": ok, "fit_reason": why,
                "measured": (settings.get("measured") or {}).get(pin.name),
                "slow": slow(pin.name, role, settings, machine),
                "in_use": in_use[role] == pin.name,
                "setup_default": defaults.get(role) == pin.name,
                # The meaning index's model lives with the Brain and downloads there.
                "with_brain": pin.name == MEANING_INDEX,
            })
        roles.append({"role": role, "label": ROLE_WORDS[role], "model": in_use[role],
                      "options": options})
    total = round(sum(ram_gb(n, lock) for n in in_use.values()), 1)
    engine = _engine_state()
    asked = settings.get("agent_claude_code")
    return {"machine": asdict(machine), "setup": setup, "setup_label": SETUPS[setup]["label"],
            "checked_at": settings.get("checked_at"), "roles": roles,
            "ram_in_use_gb": total, "budget_ms": budget(machine),
            "fallbacks": gave + fallbacks(in_use.get("decide"), settings, lock),
            "engine": engine,
            # Claude Code for the knowledge agent: the person's opt-in once a local agent model
            # is here; until then it stays on unless they turned it off (brain-logic plan 17).
            "agent_claude_code": asked is True or (asked is None and not engine["agent"]),
            "agent_claude_code_set": asked is not None,
            "lock": lock.fingerprint, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _engine_state() -> dict:
    found = models_client.status()
    return {"ready": found.ready, "reason": found.reason, "lock": found.lock,
            "roles": found.roles, "agent": found.agent}
