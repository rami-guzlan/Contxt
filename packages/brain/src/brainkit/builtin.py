"""Built-in skills: the procedures every brain comes with (brainkit/builtin/skills).

They keep the brain itself: a knowledge check of anything new against what the brain holds
and what it is for, a wrap-up that files what a conversation decided, teaching the brain one
thing on purpose, and an interview about the brain's goals. A new brain gets them when it is
made (`copy_into`); an older one gets the ones it is missing when its owner adds them
(`install`), as one undo point. Once in a brain they are its own skills: the owner can change
them like any other, and a skill of the same name is never overwritten.
"""
from __future__ import annotations

import os
import shutil

from . import frontmatter as fm
from . import util

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "builtin", "skills")


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def available() -> list[dict]:
    """[{"name", "category", "description", "folder"}]: every built-in skill, by name."""
    out = []
    if not os.path.isdir(FOLDER):
        return out
    for category in sorted(os.listdir(FOLDER)):
        base = os.path.join(FOLDER, category)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name, "SKILL.md")
            if not os.path.isfile(path):
                continue
            meta, _body, _errors = fm.parse(util.read_text(path))
            out.append({"name": str(meta.get("name") or name), "category": category,
                        "description": str(meta.get("description") or ""),
                        "folder": os.path.join(base, name)})
    return out


def missing(brain) -> list[dict]:
    """The built-in skills this brain does not have (by name)."""
    have = set(brain.state().index.skills)
    return [s for s in available() if s["name"] not in have]


def copy_into(vault: str) -> list[str]:
    """Copy every built-in skill into a vault that is being made (no history yet). Skips a
    skill of the same name already there. Returns the names copied."""
    copied = []
    for skill in available():
        target = os.path.join(vault, "skills", skill["category"], skill["name"])
        if os.path.exists(target):
            continue
        shutil.copytree(skill["folder"], target, ignore=shutil.ignore_patterns("__pycache__"))
        copied.append(skill["name"])
    return copied


def install(brain, *, actor=None, names=None):
    """Add the built-in skills a brain is missing (or the ones `names` lists), as one undo
    point the owner can take back."""
    from . import checkpoints, governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    wanted = [s for s in missing(brain) if names is None or s["name"] in set(names)]
    if not wanted:
        return _result("The brain has every built-in skill already.", {"added": []})
    label = "Built-in skills: " + ", ".join(s["name"] for s in wanted)
    touched = []
    with checkpoints.batch(brain, actor=who, label=label) as batch:
        for skill in wanted:
            rel = f"skills/{skill['category']}/{skill['name']}"
            for folder, _dirs, files in os.walk(skill["folder"]):
                if "__pycache__" in folder:
                    continue
                inner = os.path.relpath(folder, skill["folder"])
                for name in files:
                    relpath = "/".join(p for p in (rel, "" if inner == "." else
                                                   inner.replace(os.sep, "/"), name) if p)
                    target = brain.vault.path(*relpath.split("/"))
                    brain.vault.touch(target)
                    with open(os.path.join(folder, name), "rb") as handle:
                        util.atomic_write_bytes(target, handle.read())
                    touched.append(target)
            batch.decisions.append({"action": "approved", "kind": "skill.create",
                                    "title": skill["name"]})
        record = {"at": util.now_iso(), "action": "added", "by": who, "kind": "skill.builtin",
                  "skills": [s["name"] for s in wanted]}
        touched.append(brain.vault.path(brain.vault.append_decision(record)))
        outcome = brain.after_write(touched, label)
    return _result(f"Added {len(wanted)} built-in skill(s): "
                   + ", ".join(s["name"] for s in wanted) + ".",
                   {"added": [s["name"] for s in wanted], "checkpoint": batch.checkpoint,
                    "commit": outcome.get("commit")})
