"""Project-scoped requests and current values (Release 1 plan, M00 baseline).

The spec (tests/evals/scope.json) holds invented projects, each a Focus with an objective,
two pinned notes and five notes filed with it, beside Brain-wide notes. Requests name a
project, or for `implicit` ones only its subject. Measured on a scratch copy of the empty
starter:

    reached     the needed note was delivered, whole or as a pointer
    whole       the needed note was delivered whole
    pins        a status request delivered every pinned note
    recognized  the router found the project the request names
    leaks       requests that delivered any note filed with another project, apart for the
                requests whose project was recognized
    updates     the newest dated value delivered with every older one marked
    conflicts   two live values for one fact on the same date: both delivered, neither
                marked older (no newest-wins)
"""
from __future__ import annotations

import json
import os
import shutil

from . import safeguards_eval as se

EMPTY = ("brains", "empty", "vault")


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _notes(specs, area, topic, **extra) -> list[dict]:
    out = []
    for spec in specs:
        meta = {"area": area, "topic": topic, "summary": spec["body"], **extra, **spec}
        out.append(meta)
    return out


def _sent(data) -> tuple[set, set]:
    whole = set(data.get("note_ids") or [])
    pointed = (set(data.get("pointer_ids") or []) | set(data.get("related_ids") or [])
               | set(data.get("unfit_ids") or []))
    return whole, whole | pointed


def build(root: str, spec: dict, models_dir: str | None = None) -> tuple[str, dict]:
    """A scratch Brain holding the spec's projects. Returns (vault, owner of each note id)."""
    from . import focus
    vault = se.copy_vault(os.path.join(root, *EMPTY), models_dir)
    owner = {}
    se.add_notes(vault, _notes(spec["brain_wide"], "work", "general"))
    brain = se.open_brain(vault)
    try:
        for project in spec["projects"]:
            made = focus.create_focus(brain, project["name"], project["objective"],
                                      objective=project["objective"],
                                      aliases=project.get("aliases"),
                                      pinned_notes=project.get("pins"))
            if made.is_error:
                raise RuntimeError(made.text)
            owner[made.data.get("id") or project["key"]] = project["key"]
    finally:
        brain.close()
    brain = se.open_brain(vault)
    try:
        focuses = {f.title: f for f in brain.state().index.focuses.values()}
    finally:
        brain.close()
    for project in spec["projects"]:
        f = focuses[project["name"]]
        se.add_notes(vault, _notes(project["notes"], f.note.area, f.note.topic,
                                   project_id=f.id))
        for note in project["notes"]:
            owner[note["id"]] = project["key"]
        owner[f.id] = project["key"]
    return vault, owner


def run(root: str, spec: dict, *, models_dir: str | None = None) -> dict:
    vault, owner = build(root, spec, models_dir)
    rows = []
    try:
        brain = se.open_brain(vault, semantic=bool(models_dir))
        try:
            for project in spec["projects"]:
                for case in project["requests"]:
                    data = brain.context(case["q"], record=False, include_kernel=False).data
                    whole, sent = _sent(data)
                    leaked = sorted(i for i in sent
                                    if owner.get(i) and owner[i] != project["key"])
                    row = {"project": project["key"], "q": case["q"],
                           "implicit": bool(case.get("implicit")), "leaked": leaked,
                           "recognized": str(data.get("focus_mode") or "no-focus")
                           not in ("no-focus", "portfolio")}
                    if case.get("status"):
                        row["pins"] = all(p in sent for p in project["pins"])
                    else:
                        row["reached"] = case["need"] in sent
                        row["whole"] = case["need"] in whole
                    rows.append(row)
        finally:
            brain.close()
    finally:
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
    return {"requests": rows, "updates": _dated(root, spec["updates"], models_dir, True),
            "conflicts": _dated(root, spec["conflicts"], models_dir, False)}


def _dated(root, cases, models_dir, update: bool) -> list[dict]:
    rows = []
    for case in cases:
        vault = se.copy_vault(os.path.join(root, *EMPTY), models_dir)
        try:
            se.add_notes(vault, _notes(case["notes"], "work", "general"))
            brain = se.open_brain(vault, semantic=bool(models_dir))
            try:
                data = brain.context(case["request"], record=False,
                                     include_kernel=False).data
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)
        whole, sent = _sent(data)
        older = set(data.get("older_ids") or [])
        if update:
            ok = case["newest"] in whole and all(o not in sent or o in older
                                                 for o in case["older"])
        else:
            ids = [n["id"] for n in case["notes"]]
            ok = all(i in sent and i not in older for i in ids)
        rows.append({"id": case["id"], "ok": ok, "sent": sorted(sent), "older": sorted(older)})
    return rows


def rate(rows, key, where=lambda r: True) -> tuple[int, int]:
    chosen = [r for r in rows if key in r and where(r)]
    return sum(1 for r in chosen if r[key]), len(chosen)


def summary(result: dict) -> dict:
    reqs = result["requests"]
    named = lambda r: not r["implicit"]  # noqa: E731
    return {
        "reached_named": rate(reqs, "reached", named),
        "whole_named": rate(reqs, "whole", named),
        "reached_implicit": rate(reqs, "reached", lambda r: r["implicit"]),
        "pins": rate(reqs, "pins"),
        "recognized": rate(reqs, "recognized", named),
        "leak_free_recognized": (sum(1 for r in reqs if r["recognized"] and not r["leaked"]),
                                 sum(1 for r in reqs if r["recognized"])),
        "leak_free": (sum(1 for r in reqs if not r["leaked"]), len(reqs)),
        "updates": rate(result["updates"], "ok"),
        "conflicts_shown": rate(result["conflicts"], "ok"),
    }


def markdown(result: dict, title: str) -> str:
    s = summary(result)
    labels = {"reached_named": "Needed note reached (project named)",
              "whole_named": "Needed note whole (project named)",
              "reached_implicit": "Needed note reached (subject only)",
              "pins": "Status request delivers every pin",
              "recognized": "Named project recognized",
              "leak_free_recognized": "No other project's notes, project recognized",
              "leak_free": "No other project's notes, every request",
              "updates": "Newest value current, older marked",
              "conflicts_shown": "Same-date conflict shows both values"}
    lines = [f"## {title}", "", "| Measure | Result |", "| --- | --- |"]
    for key, label in labels.items():
        good, total = s[key]
        lines.append(f"| {label} | {good}/{total} ({100 * good / total:.0f}%) |"
                     if total else f"| {label} | none |")
    leaks = [r for r in result["requests"] if r["leaked"]]
    if leaks:
        lines += ["", "Leaks:", ""] + [f"- {r['q']} brought {', '.join(r['leaked'])}" for r in leaks]
    misses = [r for r in result["requests"] if r.get("reached") is False]
    if misses:
        lines += ["", "Missed:", ""] + [f"- {r['q']}" for r in misses]
    return "\n".join(lines) + "\n"
