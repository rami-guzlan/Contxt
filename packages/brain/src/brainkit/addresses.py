"""Section addresses: one part of a note, a lesson or a file, by name (v4 spec, section 6).

    note-id#heading     a note's part under that heading
    file#section        a filed document's part (the file by its path, its name or its title)
    lore_id#story       a lesson's story, #pattern or #words

An address names a part by the slug of its heading. Text before a document's first heading
is `#opening`; a note with no headings has one part, `#body`. An address without `#` names the
whole item. `gnomon_open` opens one address within the pull budget (api.py); the app shows each
address beside its part so the owner can copy it.

Nothing here is stored. Parts are read from the text each time, so an address always names
what the Brain holds now, and one that names something gone says so (`not_found`), with when
it went when the Brain knows.
"""
from __future__ import annotations

import re

from . import util
from .scopes import Scopes

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def split(body: str) -> list[dict]:
    """The parts of a text, in order: [{slug, heading, text}]."""
    parts: list[dict] = []
    heading, lines, fenced, seen = "", [], False, False

    def flush():
        text = "\n".join(lines).strip()
        if text or heading:
            parts.append({"heading": heading, "text": text})

    for line in str(body or "").splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        found = None if fenced else HEADING.match(line)
        if found:
            if seen or "\n".join(lines).strip():
                flush()
            heading, lines, seen = " ".join(found.group(2).split()), [], True
            continue
        lines.append(line)
    flush()
    if not seen:
        text = str(body or "").strip()
        return [{"slug": "body", "heading": "", "text": text}] if text else []
    out, used = [], set()
    for part in parts:
        slug = util.slugify(part["heading"]) if part["heading"] else "opening"
        base, n = slug, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        out.append({"slug": slug, **part})
    return out


def of(item_id: str, body: str) -> list[str]:
    """Every address in one item, in order."""
    return [f"{item_id}#{p['slug']}" for p in split(body)]


def _file(index, wanted: str):
    """The filed document an address names: by path, by its name, or by its title."""
    text = wanted.strip().replace("\\", "/")
    for path in (text, "references/" + text):
        if path in index.references:
            return index.references[path]
    low = text.lower()
    for path, ref in sorted(index.references.items()):
        if path.rsplit("/", 1)[-1].lower() == low or index.file_title(path).lower() == low:
            return ref
    return None


def resolve(st, address: str, chain, partitions) -> dict:
    """What an address names, for the caller: status `ok` with its text, or `not_found`."""
    address = " ".join(str(address or "").split())
    item, _, part = address.partition("#")
    item, part = item.strip(), part.strip()
    index = st.index
    found = {"address": address, "item": item, "section": part}
    note = index.note(item) if item else None
    if note is not None and not Scopes.admits(note.scope, note.partition, chain, partitions):
        note = None
    kind, name, body, ident = "", "", "", ""
    if note is not None:
        kind = "lesson" if note.kind == "lesson" else "note"
        name, body, ident, digest = (note.title or note.id), note.body, note.id, note.body_hash
    else:
        ref = _file(index, item) if item else None
        owner = index.file_project(ref.path) if ref is not None else None
        if owner is not None and not Scopes.admits(owner.note.scope, owner.note.partition,
                                                    chain, partitions):
            ref = None
        if ref is None:
            gone = index.note(item, include_archived=True) if item else None
            when = ""
            if gone is not None and Scopes.admits(gone.scope, gone.partition, chain,
                                                  partitions):
                when = str(gone.meta.get("updated") or gone.meta.get("archived") or "")
                found["name"] = gone.title or gone.id
            return {**found, "status": "not_found", "gone_at": when or None,
                    "why": "not in the Brain now"}
        kind, name, body, ident = "file", index.file_title(ref.path), ref.body, ref.path
        digest = ref.body_hash
    parts = split(body)
    found.update(kind=kind, id=ident, name=name,
                 sections=[f"{ident}#{p['slug']}" for p in parts])
    if not part:
        text = body.strip()
    else:
        wanted = util.slugify(part)
        hit = next((p for p in parts if p["slug"] in (part.lower(), wanted)), None)
        if hit is None and part.isdigit() and 0 < int(part) <= len(parts):
            hit = parts[int(part) - 1]
        if hit is None:
            return {**found, "status": "not_found", "gone_at": None,
                    "why": f"{name} has no part #{part} now"}
        text = ((f"## {hit['heading']}\n\n" if hit["heading"] else "") + hit["text"]).strip()
        name = f"{name}, {hit['heading'] or hit['slug']}"
        found["section"] = hit["slug"]
        found["address"] = f"{ident}#{hit['slug']}"
    return {**found, "status": "ok", "name": name, "text": text,
            "tokens": util.tokens(text), "hash": util.sha256(digest + "#" + found["section"])}
