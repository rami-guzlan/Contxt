"""The model lock: every local model the retrieval engine may run, pinned.

`models.lock.json` (beside this module) lists each model by name: its role (rerank, decide,
embed), the repository and revision it comes from, the checksum of every file, its dtype and
the runtime it was checked with. The same pins run everywhere, so two machines give the same
answers and an audit can name the exact model behind any decision (brain-logic plan 5.11.8).

- A model the lock does not list is refused.
- A listed model loads only when its files match the lock's checksums; a model not pinned yet
  (no revision or no checksums) is refused until someone pins it on a machine that runs it:
  `brain models pin <name> <folder>` records the checksums of a downloaded copy.
- An adapter (Kev is a LoRA adapter and a head) is only as pinned as the base model it runs on,
  so its entry pins that base too (`base`: repository, revision, checksums), kept in the same
  model cache and verified with it.
- The lock's fingerprint (a hash of its pins) travels with every brief the engine builds, and
  a client refuses a model service whose lock differs.

Changing a pin is a code change, reviewed like one, with the replay harness showing how the
eval's briefs move before it lands.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

from . import util

LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.lock.json")
ROLES = ("rerank", "decide", "embed", "agent")
CHUNK = 1 << 20


@dataclass(frozen=True)
class Pin:
    """One model the lock lists."""
    name: str
    role: str
    repository: str
    revision: str
    files: dict = field(default_factory=dict)  # relative path: sha256
    dtype: str = ""
    runtime: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)  # what a backend needs (a temperature, a template)
    default: bool = False  # the model its role runs unless the service is told otherwise
    base: dict = field(default_factory=dict)  # an adapter's base model: repository, revision, files

    @property
    def pinned(self) -> bool:
        if self.base and not (self.base.get("revision") and self.base.get("files")):
            return False
        return bool(self.revision) and bool(self.files)


@dataclass(frozen=True)
class Verdict:
    """Whether a model folder may load, and why not."""
    name: str
    ok: bool
    reason: str = ""


class Refused(Exception):
    """A model the lock does not allow."""


class Lock:
    def __init__(self, pins: dict[str, Pin], path: str = ""):
        self.pins = pins
        self.path = path

    @classmethod
    def load(cls, path: str | None = None) -> Lock:
        path = path or os.environ.get("BRAIN_MODELS_LOCK") or LOCK_PATH
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        pins = {}
        for row in data.get("models") or []:
            name = str(row.get("name") or "").strip()
            role = str(row.get("role") or "").strip()
            if not name or role not in ROLES:
                continue
            base = row.get("base") or {}
            pins[name] = Pin(
                name=name, role=role, repository=str(row.get("repository") or ""),
                revision=str(row.get("revision") or ""),
                files={str(k): str(v).lower() for k, v in (row.get("files") or {}).items()},
                dtype=str(row.get("dtype") or ""), runtime=dict(row.get("runtime") or {}),
                extra=dict(row.get("extra") or {}), default=bool(row.get("default")),
                base={"repository": str(base.get("repository") or ""),
                      "revision": str(base.get("revision") or ""),
                      "files": {str(k): str(v).lower()
                                for k, v in (base.get("files") or {}).items()}}
                if base else {})
        return cls(pins, path)

    @property
    def fingerprint(self) -> str:
        """A hash of every pin (and every base it runs on): what a client and the service
        compare."""
        rows = []
        for p in sorted(self.pins.values(), key=lambda p: p.name):
            row = [p.name, p.role, p.repository, p.revision, sorted(p.files.items()), p.dtype]
            if p.base:
                row.append([p.base["repository"], p.base["revision"],
                            sorted(p.base["files"].items())])
            rows.append(row)
        return util.short_hash(json.dumps(rows, sort_keys=True), 12)

    def pin(self, name: str) -> Pin:
        """The pin for a model, or Refused when the lock does not list it."""
        found = self.pins.get(str(name or "").strip())
        if found is None:
            raise Refused(f"{name!r} is not in the model lock; only pinned models run "
                          f"({', '.join(sorted(self.pins)) or 'none listed'})")
        return found

    def for_role(self, role: str) -> list[Pin]:
        return [p for p in self.pins.values() if p.role == role]

    def verify(self, name: str, folder: str) -> Verdict:
        """Does the model in `folder` match its pin, file for file?"""
        try:
            pin = self.pin(name)
        except Refused as exc:
            return Verdict(name, False, str(exc))
        if not pin.pinned:
            return Verdict(name, False, f"{name} is not pinned yet: run `brain models pin "
                                        f"{name} <folder>` on a machine that runs it")
        if not folder or not os.path.isdir(folder):
            return Verdict(name, False, f"{name} is not downloaded ({folder or 'no folder'})")
        problem = _mismatch(pin.files, folder)
        if problem:
            return Verdict(name, False, f"{name}: {problem}")
        if pin.base:
            where = base_folder(pin, folder)
            label = f"{name}: its base model {pin.base['repository']}"
            if not where:
                return Verdict(name, False, f"{label} is not downloaded")
            problem = _mismatch(pin.base["files"], where)
            if problem:
                return Verdict(name, False, f"{label}: {problem}")
        return Verdict(name, True)


def _mismatch(files: dict, folder: str) -> str:
    """The first file of `files` missing from `folder` or differing from its checksum, or ""."""
    for rel, expected in sorted(files.items()):
        path = os.path.join(folder, *rel.split("/"))
        if not os.path.isfile(path):
            return f"{rel} is missing"
        if file_sha256(path) != expected:
            return f"{rel} does not match the lock"
    return ""


def snapshot(models_dir: str, repository: str, revision: str) -> str:
    """The folder of a repository's revision in a Hugging Face style cache, or ""."""
    if not repository or not revision:
        return ""
    found = os.path.join(models_dir, "models--" + repository.replace("/", "--"), "snapshots")
    try:
        names = sorted(os.listdir(found))
    except OSError:
        return ""
    names = [n for n in names if n.startswith(revision) or revision.startswith(n)]
    return os.path.join(found, names[0]) if names else ""


def cache_of(folder: str) -> str:
    """The model cache a model's folder sits in: `<cache>/models--org--name/snapshots/<rev>`
    in a Hugging Face style cache, else the folder's parent (`<cache>/<name>`)."""
    parts = os.path.normpath(folder).split(os.sep)
    if len(parts) >= 4 and parts[-2] == "snapshots" and parts[-3].startswith("models--"):
        return os.sep.join(parts[:-3])
    return os.path.dirname(os.path.normpath(folder))


def base_folder(pin: Pin, folder: str) -> str:
    """Where an adapter's base model is: its pinned revision in the adapter's own cache."""
    if not pin.base:
        return ""
    return snapshot(cache_of(folder), pin.base["repository"], pin.base["revision"])


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def checksums(folder: str) -> dict[str, str]:
    """{relative path: sha256} for every file of a downloaded model (what `pin` records)."""
    out = {}
    for root, _dirs, names in os.walk(folder):
        for name in sorted(names):
            if name.startswith("."):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder).replace("\\", "/")
            out[rel] = file_sha256(path)
    return dict(sorted(out.items()))


def record_pin(name: str, folder: str, *, revision: str = "", base: str = "",
               path: str | None = None) -> dict:
    """Write the checksums of a downloaded copy into the lock (a code change to review).
    `base` ("<repository>@<revision>") pins the base model an adapter runs on, from the same
    model cache."""
    path = path or LOCK_PATH
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    rows = data.get("models") or []
    row = next((r for r in rows if r.get("name") == name), None)
    if row is None:
        raise Refused(f"{name!r} is not in the model lock; add its entry first")
    found_base = None
    if base:
        repository, _sep, base_revision = base.partition("@")
        where = snapshot(cache_of(folder), repository, base_revision)
        if not repository or not base_revision or not where:
            raise Refused(f"the base model {base} is not in the model cache beside {folder}")
        found_base = {"repository": repository, "revision": os.path.basename(where),
                      "files": checksums(where)}
    row["files"] = checksums(folder)
    if revision:
        row["revision"] = revision
    if found_base:
        row["base"] = found_base
    util.atomic_write(path, json.dumps(data, indent=2) + "\n")
    out = {"name": name, "files": len(row["files"]), "revision": row.get("revision")}
    if found_base:
        out["base"] = {"repository": found_base["repository"],
                       "revision": found_base["revision"], "files": len(found_base["files"])}
    return out
