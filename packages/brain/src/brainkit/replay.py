"""Replay: rebuild the brief a logged request got, against the brain as it is now, as it was
at a git commit, or with a waiting proposal applied, and say what changed (brain-logic plan
10.3). The evaluations, the blast radius of a change and the paper's results all use it.

Nothing is recorded: a replay routes on a throwaway ledger. A past or proposed brain is a
scratch copy of the vault (from git, or with the proposal applied in the copy) that borrows the
live brain's local models and embedding cache, so it matches by meaning exactly as the live one
does. The live vault is never written.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile

from . import util
from .sessions import Ledger


def logged(brain, packet_id: str) -> dict | None:
    """What a logged request was and what it got: its request, who asked, the partition, and
    the packet's data."""
    found = brain.ledger.packet(str(packet_id or ""))
    if found is None:
        return None
    data = found.get("data") or {}
    chain = data.get("scope_chain") or []
    principal = brain.ledger.session_principal(found.get("session_id") or "") or (
        chain[-1] if chain else None)
    return {"packet_id": found["id"], "request": found.get("request") or "",
            "principal": principal, "partition": data.get("partition"), "data": data,
            "tokens": found.get("tokens"), "at": found.get("at")}


def _summary(data: dict) -> dict:
    return {"mode": data.get("mode"), "request_type": data.get("request_type"),
            "notes": list(data.get("note_ids") or []),
            "must_holds": list(data.get("must_hold_ids") or []),
            "sections": list(data.get("section_ids") or []),
            "skill": data.get("skill_included") or data.get("skill_id"),
            "related": list(data.get("related_ids") or []),
            "tokens": int(data.get("token_count") or 0)}


def diff(before: dict, after: dict) -> dict:
    """What entered, left and moved between two brief summaries, and the token difference."""
    def changes(key):
        old, new = list(before.get(key) or []), list(after.get(key) or [])
        return {"entered": [i for i in new if i not in old],
                "left": [i for i in old if i not in new]}
    old_notes, new_notes = list(before.get("notes") or []), list(after.get("notes") or [])
    kept = [n for n in new_notes if n in old_notes]
    moved = [n for n in kept if old_notes.index(n) != new_notes.index(n)
             and [m for m in old_notes if m in kept].index(n) != kept.index(n)]
    out = {"notes": dict(changes("notes"), moved=moved), "must_holds": changes("must_holds"),
           "sections": changes("sections"),
           "tokens": {"before": int(before.get("tokens") or 0),
                      "after": int(after.get("tokens") or 0)},
           "mode": None if before.get("mode") == after.get("mode") else
           {"before": before.get("mode"), "after": after.get("mode")},
           "skill": None if before.get("skill") == after.get("skill") else
           {"before": before.get("skill"), "after": after.get("skill")}}
    out["tokens"]["change"] = out["tokens"]["after"] - out["tokens"]["before"]
    out["same"] = not any(out[k]["entered"] or out[k]["left"]
                          for k in ("notes", "must_holds", "sections")) and not moved and \
        not out["mode"] and not out["skill"]
    return out


def _rebuild(target, case: dict) -> dict:
    result = target.context(case["request"], principal=case.get("principal"),
                            partition=case.get("partition"), record=False,
                            include_kernel=False)
    if result.is_error:
        return {"error": result.text}
    return result.data


def _scratch_brain(brain, vault_dir: str):
    """A brain over a scratch vault that shares the live brain's models and vector cache."""
    from .api import Brain
    other = Brain(vault_dir, principal=brain.default_principal,
                  embeddings=brain.embedder is not None,
                  rerank=brain.reranker is not None, repo_root=os.path.dirname(vault_dir))
    if brain.embedder is not None and other.embedder is not None:
        other.embedder.model_dir = brain.embedder.model_dir
        other.embedder.cache_path = brain.embedder.cache_path
    if brain.reranker is not None and other.reranker is not None:
        other.reranker.model_dir = brain.reranker.model_dir
    other._ledger = Ledger(os.path.join(tempfile.mkdtemp(prefix="brain-replay-ledger-"),
                                        "sessions.sqlite"), 30)
    return other


def _git(repo: str, *args: str, binary: bool = False):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=False,
                          timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        raise ValueError(f"git {' '.join(args[:2])} failed: {detail[0][:200]}")
    return done.stdout if binary else done.stdout.decode("utf-8", "replace").strip()


def _vault_at(brain, ref: str, root: str) -> str:
    """A scratch copy (under `root`) of the vault as it was at a git commit or any ref."""
    top = _git(brain.vault.root, "rev-parse", "--show-toplevel")
    rel = os.path.relpath(brain.vault.root, top).replace("\\", "/")
    rel = "" if rel in (".", "") else rel
    blob = _git(top, "archive", "--format=tar", str(ref), *([rel] if rel else []), binary=True)
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        archive.extractall(root, filter="data")
    return os.path.join(root, *rel.split("/")) if rel else root


def _vault_with(brain, proposal_id: str, root: str) -> str:
    """A scratch copy (under `root`) of the vault, its waiting proposal's staged files
    included, that commits nothing to git."""
    import json
    dest = os.path.join(root, "vault")
    shutil.copytree(brain.vault.root, dest, ignore=shutil.ignore_patterns(".brain", ".git"))
    staging = os.path.join(brain.vault.runtime_dir, "staging", proposal_id)
    if os.path.isdir(staging):
        shutil.copytree(staging, os.path.join(dest, ".brain", "staging", proposal_id))
    settings = os.path.join(dest, "brain.json")
    try:
        with open(settings, encoding="utf-8") as handle:
            data = json.load(handle)
        data.setdefault("git", {})["auto_commit"] = False
        util.atomic_write(settings, json.dumps(data, indent=2) + "\n")
    except (OSError, ValueError):
        pass
    return dest


class Target:
    """The brain a replay routes against, and the scratch folder to clean up after."""

    def __init__(self, brain, *, at: str | None = None, proposal: str | None = None):
        self.brain = brain
        self.root = None
        self.label = "now"
        self.target = brain
        if not (at or proposal):
            return
        self.root = tempfile.mkdtemp(prefix="brain-replay-")
        try:
            if at:
                self.target = _scratch_brain(brain, _vault_at(brain, at, self.root))
                self.label = f"at {at}"
                return
            self.target = _scratch_brain(brain, _vault_with(brain, proposal, self.root))
            outcome = self.target.approve(proposal, actor=self.target.state().config.owner)
            if outcome.is_error:
                raise ValueError(f"The proposal could not be applied in a copy: {outcome.text}")
            self.label = f"with {proposal}"
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.target is not self.brain:
            self.target.close()
        if self.root:
            shutil.rmtree(self.root, ignore_errors=True)


def replay(brain, packet_ids, *, at: str | None = None, proposal: str | None = None) -> dict:
    """Rebuild each logged request against the target brain and compare with what it got."""
    if isinstance(packet_ids, str):
        packet_ids = [packet_ids]
    started = util.now()
    target = Target(brain, at=at, proposal=proposal)
    rows = []
    # A scratch brain is private to this replay and nothing writes it while the briefs are
    # rebuilt, so its index is built once instead of re-reading the vault for every brief.
    # The live brain is never held this way: its writers must not wait on a replay.
    steady = (target.target.deferring() if target.target is not brain
              else contextlib.nullcontext())
    try:
        with steady:
            for packet_id in packet_ids:
                case = logged(brain, packet_id)
                if case is None:
                    rows.append({"packet_id": packet_id, "error": "not in the ledger"})
                    continue
                rebuilt = _rebuild(target.target, case)
                if "error" in rebuilt:
                    rows.append({"packet_id": packet_id, "request": case["request"],
                                 "error": rebuilt["error"]})
                    continue
                before, after = _summary(case["data"]), _summary(rebuilt)
                rows.append({"packet_id": packet_id, "request": case["request"],
                             "at": case["at"], "before": before, "after": after,
                             "diff": diff(before, after)})
    finally:
        target.close()
    changed = [r for r in rows if r.get("diff") and not r["diff"]["same"]]
    return {"against": target.label, "replayed": len(rows), "changed": len(changed),
            "seconds": round((util.now() - started).total_seconds(), 2), "rows": rows}


def recent_packets(brain, *, item: str | None = None, limit: int = 20) -> list[str]:
    """The newest logged packets, or the newest that carried one note (for a blast radius)."""
    with brain.ledger._connect() as conn:
        if item:
            rows = conn.execute(
                "SELECT DISTINCT packet_id FROM deliveries WHERE item = ? AND packet_id NOT IN "
                "('followup', 'work') ORDER BY at DESC LIMIT ?", (item, int(limit)))
        else:
            rows = conn.execute("SELECT id AS packet_id FROM packets ORDER BY at DESC LIMIT ?",
                                (int(limit),))
        return [r["packet_id"] for r in rows]
