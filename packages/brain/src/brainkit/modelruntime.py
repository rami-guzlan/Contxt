"""The model runtime: the separate environment the local model service runs in (build step 9).

The app's own environment stays small. The local models need torch, transformers, Kev and
llama.cpp, so one command makes an environment for them in the model home, pinned the way the
models are:

    brain models runtime [--cpu]   install it, in the build this machine needs
    brain models setup [--cpu]     the runtime and this machine's setup models, in one go

What it installs: `models-runtime.txt` beside this module (Kev's own tested set), and then

- torch 2.8.0 in the build this machine needs: CUDA 12.6 on an NVIDIA GPU (it still runs older
  GPUs such as Pascal; CUDA 13 builds do not), CUDA 12.8 on a GPU of compute capability 10 or
  more, the CPU build otherwise, PyPI's own on a Mac;
- llama-cpp-python 0.3.36 for the knowledge agent: its CUDA 12.5 build on an NVIDIA GPU (on
  Windows it finds the CUDA runtime in torch's folder, so no CUDA toolkit is needed), its CPU
  build otherwise, none on a Mac (MLX runs the agent there);
- Kev from github.com/jaredpalmer/kev at a pinned commit, never PyPI's unrelated `kev`.

No 12 GB GPU is needed: on a small GPU or none, the service puts each model where it fits
(modelservice.place). The service runs in this environment with brainkit on its path, since
brainkit needs nothing beyond the standard library. Without the runtime the service still
starts, says why each model cannot load, and retrieval falls back.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

from . import models_client, util

KEV = "kev @ git+https://github.com/jaredpalmer/kev@fc4a17e194bca35a48c57211392ec49ea54a94ac"
LLAMA = "llama-cpp-python==0.3.36"
LLAMA_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/{}"
PYTHON = "3.13"  # Kev runs on 3.12 and 3.13
REQUIREMENTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models-runtime.txt")
STAMP = "contxt-runtime.json"
BRAINKIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the folder holding it


@dataclass(frozen=True)
class Build:
    """Which builds of torch and llama.cpp this machine gets."""
    variant: str  # cuda, cpu or mac
    torch: str    # uv's torch backend (cu126, cu128, cpu), "" for PyPI's own
    llama: str    # the llama.cpp wheel index (cu125, cpu), "" for none
    why: str


def folder() -> str:
    return os.path.join(models_client.model_home(), "runtime")


def python(base: str | None = None) -> str:
    base = base or folder()
    if os.name == "nt":
        return os.path.join(base, "Scripts", "python.exe")
    return os.path.join(base, "bin", "python")


def pinned() -> str:
    """A hash of what the runtime pins: a changed file means the runtime is out of date."""
    with open(REQUIREMENTS, "rb") as handle:
        body = handle.read()
    return hashlib.sha256(body + KEV.encode() + LLAMA.encode()).hexdigest()[:12]


def build_for(found, compute: float = 0.0, *, cpu: bool = False) -> Build:
    """The builds for a machine (machine.Machine) whose GPU has this compute capability."""
    if found.apple_silicon:
        return Build("mac", "", "", "Apple Silicon: PyPI's torch (with MPS) and MLX")
    if cpu or not found.gpu:
        return Build("cpu", "cpu", "cpu", "the CPU builds: " + (
            "asked for" if cpu else "no NVIDIA GPU here"))
    if compute >= 10:
        return Build("cuda", "cu128", "cu125", f"{found.gpu} (compute {compute:g}): CUDA 12.8")
    return Build("cuda", "cu126", "cu125",
                 f"{found.gpu}" + (f" (compute {compute:g})" if compute else "")
                 + ": CUDA 12.6, which still runs older GPUs")


def steps(build: Build, uv: str, target: str) -> list[list[str]]:
    """The commands that make the runtime, in order."""
    py = python(target)
    out = [[uv, "venv", target, "--python", PYTHON, "--allow-existing"]]
    packages = [uv, "pip", "install", "--python", py, "-r", REQUIREMENTS]
    if build.torch:
        packages += ["--torch-backend", build.torch]
    out.append(packages)
    if build.llama:
        out.append([uv, "pip", "install", "--python", py, LLAMA, "--extra-index-url",
                    LLAMA_INDEX.format(build.llama)])
    out.append([uv, "pip", "install", "--python", py, "--no-deps", KEV])
    return out


def install(*, cpu: bool = False, found=None, compute: float | None = None, run=None,
            say=print) -> dict:
    """Make or update the runtime for this machine. Returns what it records."""
    from . import machine
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("the model runtime is installed with uv (https://docs.astral.sh/uv/): "
                           "install uv, then run this again")
    found = found or machine.detect()
    if compute is None:
        compute = compute_capability() if found.gpu else 0.0
    build = build_for(found, compute, cpu=cpu)
    target = folder()
    say(f"The model runtime in {target}: {build.why}.")
    for argv in steps(build, uv, target):
        say("  " + " ".join(a for a in argv[1:] if a != uv))
        (run or _run)(argv)
    record = {"build": asdict(build), "pinned": pinned(), "python": python(target),
              "at": util.now_iso()}
    util.atomic_write(os.path.join(target, STAMP), json.dumps(record, indent=1) + "\n")
    return record


def _run(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


def status() -> dict:
    """Whether the runtime is here, which build, and whether it matches what is pinned now."""
    try:
        with open(os.path.join(folder(), STAMP), encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError):
        record = {}
    here = bool(record) and os.path.isfile(python())
    return {"installed": here, "current": here and record.get("pinned") == pinned(),
            "build": record.get("build"), "python": python() if here else "",
            "at": record.get("at")}


def compute_capability() -> float:
    """The largest NVIDIA GPU's compute capability (6.1 for a GTX 1060), 0 when unknown."""
    tool = shutil.which("nvidia-smi")
    if not tool:
        return 0.0
    try:
        out = subprocess.run([tool, "--query-gpu=compute_cap", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return 0.0
    found = []
    for line in out.splitlines():
        try:
            found.append(float(line.strip()))
        except ValueError:
            continue
    return max(found, default=0.0)


def service_command(fallback: str | None = None) -> tuple[list[str], dict]:
    """How to start the model service: in the runtime when it is installed (brainkit on its
    path), else in this environment. Returns (argv, environment)."""
    env = dict(os.environ)
    found = status()
    if found["installed"]:
        env["PYTHONPATH"] = os.pathsep.join(p for p in (BRAINKIT, env.get("PYTHONPATH")) if p)
        return [found["python"], "-m", "brainkit.modelservice"], env
    return [fallback or sys.executable, "-m", "brainkit.modelservice"], env
