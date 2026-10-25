"""The Test Bench's view of a packet (Release 1 plan, 15.2 and 15.3).

`trim` takes parts out of a route after the router has chosen and before the packet is
built, so nothing fills the gap: "custom" is exactly what was checked. `include` names the
sections (and, within them, the items) to keep; `exclude` names sections and items to drop.

`view` lists the packet's own sections in the order they go out, each item with why it was
chosen and its tokens, from what the packet builder recorded (so the names match whatever a
Brain holds).

(`bench.py` is the older behaviour checks of packet kinds; this is the owner's Test Bench.)
"""
from __future__ import annotations

import os
import re

from . import gitops, util

# (name, label), in the order a packet sends them.
SECTIONS = (("must_holds", "Must-holds"), ("project", "Project"), ("sheets", "Live sheets"),
            ("notes", "Notes"), ("files", "Files"), ("pointers", "Also relevant"),
            ("map", "Brain map"))
LATE = ("sheets", "map")  # added by the Brain after the packet builder


def _ids(value) -> set[str]:
    return {str(i) for i in (value or []) if str(i).strip()}


def dropped(include=None, exclude=None) -> set[str]:
    """The sections `include` and `exclude` leave out."""
    include, exclude = dict(include or {}), dict(exclude or {})
    names = {name for name, _label in SECTIONS}
    drop = _ids(exclude.get("sections")) & names
    if include:
        drop |= names - _ids(include.get("sections"))
    return drop


def trim(route, include=None, exclude=None) -> set[str]:
    """Drop the excluded sections and items from `route` in place, and return the sections
    the Brain adds later (sheets, the map) that must be left out too."""
    include, exclude = dict(include or {}), dict(exclude or {})
    names = {name for name, _label in SECTIONS}
    drop = _ids(exclude.get("sections")) & names
    drop_ids = _ids(exclude.get("ids"))
    keep_ids: set[str] | None = None
    if include:
        drop |= names - _ids(include.get("sections"))
        keep_ids = _ids(include.get("ids")) or None
    if not drop and not drop_ids and keep_ids is None:
        return set()

    def kept(item_id: str) -> bool:
        return item_id not in drop_ids and (keep_ids is None or item_id in keep_ids)

    def scored(name: str, attr: str) -> None:
        rows = getattr(route, attr)
        setattr(route, attr, [] if name in drop else [s for s in rows if kept(s.item.id)])

    for attr in ("notes", "style_notes", "standing_answer"):
        scored("notes", attr)
    for attr in ("related", "related_pool"):
        scored("pointers", attr)
    scored("files", "sections")
    for attr in ("must_holds", "must_overflow"):
        rows = getattr(route, attr)
        setattr(route, attr, [] if "must_holds" in drop
                else [m for m in rows if kept(m.note.id)])
    if "files" in drop:
        route.pointed_files = []
    if "project" in drop and route.mode not in ("focus-only", "focus-update"):
        route.focus = None
    gone = {s.item.id for s in route.notes}
    route.older = [(old, new) for old, new in route.older if new.id in gone]
    return drop & set(LATE)


def view(data: dict, st) -> list[dict]:
    """The packet's sections, in order, each with its items: id, title, why, score, tokens."""
    index = st.index
    note_tokens = data.get("note_tokens") or {}
    trace = data.get("trace") or {}
    scores = {r.get("id"): r for r in trace.get("note_scores") or []}
    musts = {r.get("id"): r for r in trace.get("must_holds") or []}
    pointers = set(data.get("pointer_ids") or [])

    def title(note_id):
        note = index.note(note_id, include_archived=True)
        return note.title if note is not None else note_id

    out: list[dict] = []

    def add(name, label, items):
        if items:
            out.append({"name": name, "label": label, "items": items,
                        "tokens": sum(i["tokens"] for i in items)})

    for name, label in SECTIONS:
        if name == "must_holds":
            items = []
            for i in data.get("must_hold_ids") or []:
                note = index.note(i)
                items.append({"id": i, "title": title(i), "tokens": util.tokens(
                    (note.must_text or note.body) if note is not None else ""),
                    "why": (musts.get(i) or {}).get("why") or "a must-hold in play",
                    "score": None})
            add(name, label, items)
        elif name == "project" and data.get("focus_id"):
            focus = index.focuses.get(data["focus_id"])
            add(name, label, [{"id": data["focus_id"],
                               "title": focus.title if focus else data["focus_id"],
                               "tokens": util.tokens(focus.note.body) if focus else 0,
                               "why": "the project this request names", "score": None}])
        elif name == "sheets":
            add(name, label, [{"id": str(r.get("id") or r.get("row") if isinstance(r, dict)
                                         else r),
                               "title": str(r.get("key") or r.get("row") or ""
                                            if isinstance(r, dict) else r),
                               "tokens": 0, "why": "a current value the request names",
                               "score": None} for r in data.get("state_rows") or []])
        elif name == "notes":
            add(name, label, [{
                "id": i, "title": title(i), "tokens": int(note_tokens.get(i) or 0),
                "why": ("sent in short: " if i in pointers else "")
                + ("house style for writing" if (scores.get(i) or {}).get("core") is not None
                   else "relevant to the request"),
                "score": (scores.get(i) or {}).get("adj", (scores.get(i) or {}).get("score"))}
                for i in data.get("note_ids") or [] if i != data.get("focus_id")])
        elif name == "files":
            add(name, label, [{"id": i, "title": i, "tokens": 0,
                               "why": "a section of a filed document", "score": None}
                              for i in data.get("section_ids") or []])
        elif name == "pointers":
            add(name, label, [{"id": i, "title": title(i), "tokens": util.tokens(title(i)),
                               "why": "named, not sent: one call away", "score": None}
                              for i in data.get("related_ids") or []])
        elif name == "map" and data.get("map_included") in ("full", "changes"):
            add(name, label, [{"id": f"map:{data.get('map_fingerprint')}", "title": label,
                               "tokens": int(data.get("map_tokens") or 0),
                               "why": "what the Brain holds, once a conversation",
                               "score": None}])
    return out


# Tests and suites (15.4): `bench/<suite>/<test>.yaml` and `bench/<suite>/suite.yaml` in the
# Brain's own folder, committed, so the owner's quality bar travels with the Brain. The Brain
# keeps them as text; the app reads and writes the YAML.
FOLDER = "bench"
_PART = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def bench_path(root, rel: str) -> str:
    """The file `rel` names, refused unless it is `bench/<suite>/<name>.yaml`."""
    parts = str(rel or "").replace("\\", "/").split("/")
    if (len(parts) != 3 or parts[0] != FOLDER or not _PART.match(parts[1])
            or not parts[2].endswith(".yaml") or not _PART.match(parts[2][:-5])):
        raise ValueError(f"A bench file is {FOLDER}/<suite>/<name>.yaml, not {rel!r}.")
    return os.path.join(root, *parts)


def bench_files(root) -> dict[str, str]:
    """Every bench file, by its path from the Brain's folder."""
    out: dict[str, str] = {}
    top = os.path.join(root, FOLDER)
    if not os.path.isdir(top):
        return out
    for suite in sorted(os.listdir(top)):
        folder = os.path.join(top, suite)
        if not (_PART.match(suite) and os.path.isdir(folder)):
            continue
        for name in sorted(os.listdir(folder)):
            rel = f"{FOLDER}/{suite}/{name}"
            try:
                path = bench_path(root, rel)
                with open(path, encoding="utf-8") as handle:
                    out[rel] = handle.read()
            except (ValueError, OSError):
                continue
    return out


def bench_write(root, rel: str, text: str | None, *, message: str) -> dict:
    """Write a bench file (or remove it, with `text` None) and commit it."""
    path = bench_path(root, rel)
    if text is None:
        if os.path.exists(path):
            os.remove(path)
        folder = os.path.dirname(path)
        if os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return gitops.commit(root, [path], message)
