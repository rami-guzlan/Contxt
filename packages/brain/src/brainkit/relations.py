"""Relationships between entries (v4 backend plan, 13.2): typed, few, derived.

Edges come from fields the Brain already stores, rebuilt with its index. Nothing here is a
new store or a general graph:

    supersedes   an entry's `supersedes` (its version chain)
    belongs to   an entry's `project`
    pinned in    a project's pinned notes
    cites        the `references/...` files an entry points at, and its `source_id`
    mentions     a project named (by its title or an alias) in an entry's text
    explains, depends on, example of, instead of
                 an entry's own `relates` list, added only through proposals:
                 `relates: ["explains: msg#slack"]` (or `{type, to}` items)

The edges live in a `relations` table in the Brain's SQLite file (sheetstore.py), rebuilt
when the vault's fingerprint changes; git stays the source of truth. Reads are scope-filtered:
an edge is shown only when both its entries are visible to the caller, and a sealed entry is
left out with no count.
"""
from __future__ import annotations

import re

from . import sheetstore
from .scopes import Scopes

EXPLICIT = ("explains", "depends on", "example of", "instead of")
DERIVED = ("supersedes", "belongs to", "pinned in", "cites", "mentions")
TYPES = DERIVED + EXPLICIT
MAX_DEPTH = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS relations (
    src TEXT NOT NULL,
    type TEXT NOT NULL,
    dst TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_relations_src ON relations (src);
CREATE INDEX IF NOT EXISTS ix_relations_dst ON relations (dst);
"""


def _explicit(value) -> list[tuple[str, str]]:
    """An entry's own `relates` list as (type, target) pairs, unknown types left out."""
    items = value if isinstance(value, list) else ([value] if value else [])
    out = []
    for item in items:
        if isinstance(item, dict):
            kind, to = str(item.get("type") or ""), str(item.get("to") or "")
        else:
            kind, _, to = str(item).partition(":")
        kind, to = " ".join(kind.lower().split()), to.strip()
        if kind in EXPLICIT and to:
            out.append((kind, to))
    return out


def _project(index, name: str):
    """A project by its id, title, slug or an alias."""
    if name in index.focuses:
        return index.focuses[name]
    wanted = name.lower()
    return next((f for f in index.focuses.values()
                 if wanted in {str(x).lower() for x in [f.title, f.slug, *f.aliases]}), None)


def derive(index) -> list[tuple[str, str, str, str]]:
    """Every edge the index implies: (from, type, to, what it came from)."""
    edges: list[tuple[str, str, str, str]] = []
    notes = dict(index.notes)
    known = set(notes) | set(index.archived)
    projects = list(index.focuses.values())
    names = []
    for focus in projects:
        for name in [focus.title, *focus.aliases]:
            name = str(name or "").strip()
            if len(name) >= 4:
                names.append((re.compile(r"\b" + re.escape(name) + r"\b", re.I), focus.id))
        for pinned in focus.pinned_notes:
            if pinned in known:
                edges.append((pinned, "pinned in", focus.id, "project pins"))
    for note in notes.values():
        for old in str(note.meta.get("supersedes") or "").split(","):
            old = old.strip()
            if old and old != "none" and old in known:
                edges.append((note.id, "supersedes", old, "version chain"))
        project = str(note.meta.get("project") or "").strip()
        target = _project(index, project) if project else None
        if target is not None and target.id != note.id:
            edges.append((note.id, "belongs to", target.id, "project"))
        for path in note.references:
            edges.append((note.id, "cites", path, "references"))
        source = str(note.meta.get("source_id") or "").strip()
        if source:
            edges.append((note.id, "cites", source, "source"))
        for pattern, focus_id in names:
            if focus_id != note.id and pattern.search(note.body):
                edges.append((note.id, "mentions", focus_id, "text"))
        for kind, to in _explicit(note.meta.get("relates")):
            edges.append((note.id, kind, to, "relates"))
    return sorted(set(edges))


def ensure(brain, st) -> None:
    """The relations table, rebuilt when the vault changed since it was built."""
    if sheetstore.meta(brain, "relations_fingerprint") == st.fingerprint:
        return
    edges = derive(st.index)
    with sheetstore._db(brain) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM relations")
        conn.executemany("INSERT INTO relations (src, type, dst, source) VALUES (?, ?, ?, ?)",
                         edges)
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('relations_fingerprint', ?)",
                     (st.fingerprint,))


def _base(target: str) -> str:
    return target.split("#", 1)[0]


def neighbours(brain, st, note_id: str, chain, partitions, *, types=None,
               depth: int = 1) -> list[dict]:
    """The edges around an entry, out to `depth` (at most 2), both directions, each with its
    type, the entry at the other end, which way it points, and where it came from. Only
    entries the caller may see; a sealed one is left out entirely."""
    ensure(brain, st)
    wanted = {t for t in (types or []) if t in TYPES} or set(TYPES)
    depth = max(1, min(int(depth or 1), MAX_DEPTH))
    index = st.index

    def visible(item: str) -> bool:
        found = index.notes.get(_base(item)) or index.archived.get(_base(item))
        if found is None:
            return True  # a file or a source, not an entry
        return Scopes.admits(found.scope, found.partition, chain, partitions)

    if not visible(note_id):
        return []
    seen, frontier, out = {note_id}, [note_id], []
    with sheetstore._db(brain) as conn:
        conn.executescript(SCHEMA)
        for level in range(1, depth + 1):
            following = []
            for item in frontier:
                rows = conn.execute(
                    "SELECT src, type, dst, source FROM relations WHERE src = ? OR dst = ?"
                    " OR dst LIKE ? ORDER BY type, src, dst", (item, item, item + "#%"))
                for src, kind, dst, source in rows:
                    if kind not in wanted:
                        continue
                    outward = _base(src) == item
                    other = dst if outward else src
                    if not visible(other) or not visible(src):
                        continue
                    found = index.notes.get(_base(other)) or index.archived.get(_base(other))
                    out.append({"type": kind, "id": other, "direction":
                                "out" if outward else "in", "depth": level, "source": source,
                                "title": found.title if found is not None else other,
                                "from": src if not outward else item})
                    if found is not None and _base(other) not in seen:
                        seen.add(_base(other))
                        following.append(_base(other))
            frontier = following
    return out


PACKET_EDGES = 2  # edges shown under an entry in a packet, at most


def _cached(index) -> dict:
    found = getattr(index, "_relations_cache", None)
    if found is None:
        found = {"out": {}, "in": {}}
        for src, kind, dst, _source in derive(index):
            found["out"].setdefault(src, []).append((kind, dst))
            found["in"].setdefault(_base(dst), []).append((kind, src))
        index._relations_cache = found
    return found


def for_packet(index, note_id: str, shown: set[str]) -> list[str]:
    """Up to two edges for an entry in a packet, each to something the packet itself holds
    (another entry sent with it, or the request's project): never a pointer to what the
    caller was not given."""
    edges = _cached(index)
    out = [f"{kind} `{dst}`" for kind, dst in edges["out"].get(note_id, [])
           if _base(dst) in shown and _base(dst) != note_id]
    out += [f"{kind} (from) `{src}`" for kind, src in edges["in"].get(note_id, [])
            if src in shown and src != note_id]
    return out[:PACKET_EDGES]


def counts(index, visible) -> dict[str, int]:
    """How many edges of each type join entries the caller may see."""
    tally: dict[str, int] = {}
    for src, kind, dst, _source in derive(index):
        if visible(src) and visible(dst):
            tally[kind] = tally.get(kind, 0) + 1
    return tally
