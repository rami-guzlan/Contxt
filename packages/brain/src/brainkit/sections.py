"""Sections: the parts of a filed document the brain can find and quote on their own.

A reference (a document filed under references/) is split at its headings into sections of
a readable size. A request about one part of a long proposal ("tighten the LinkedIn
section") then reaches that part, quoted with the file's version and date, instead of a
pointer to the whole file. Converted documents keep their shape for this
(importers.to_markdown): Word headings, slides and PDF pages become headings. Text with no
headings is cut into runs of whole paragraphs.

Nothing here is stored. Sections are derived from the reference text whenever the index is
built, so a new version of a file is split anew and nothing can fall behind it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import util

TARGET_WORDS = 320      # a long section is cut into parts of about this many words
MAX_WORDS = 520         # ...when it runs past this
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
SOURCE_LINE = re.compile(r"^>\s*Source:", re.IGNORECASE)
SLIDE_OR_PAGE = re.compile(r"^(?:slide|page)\s+\d+\s*(?::\s*)?", re.IGNORECASE)


@dataclass(frozen=True)
class Section:
    id: str            # "<reference path>#<n>"
    path: str          # the reference it belongs to
    n: int             # its place in the document, from 1
    heading: str       # the headings above it, "Budget > LinkedIn video"; "" for none
    text: str
    part: int = 0      # part k of a long section cut in pieces (0: not cut)
    parts: int = 0

    @property
    def body_hash(self) -> str:
        return util.sha256(self.text)

    @property
    def tokens(self) -> int:
        return util.tokens(self.text)

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def label(self) -> str:
        """How a packet names it: its headings, and which part of a long section it is."""
        base = self.heading or ("Opening" if self.n == 1 and not self.parts else "")
        if self.parts:
            piece = f"part {self.part} of {self.parts}"
            return f"{base} ({piece})" if base else piece[:1].upper() + piece[1:]
        return base or f"Section {self.n}"


def body_lines(body: str) -> list[str]:
    """A reference's text without what is not its content: front matter, the document's own
    title line and the source stamp the brain writes under it."""
    text = str(body or "")
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end > 0:
            text = text[end + 4:]
    lines = text.splitlines()
    out, opening = [], True
    for line in lines:
        stripped = line.strip()
        if opening:
            if not stripped:
                continue
            if stripped.startswith("# ") and not out:
                continue
            if SOURCE_LINE.match(stripped):
                continue
            opening = False
        out.append(line.rstrip())
    return out


def split(path: str, body: str) -> list[Section]:
    """The sections of one reference, in document order."""
    stack: list[tuple[int, str]] = []
    blocks: list[tuple[str, str]] = []
    current: list[str] = []
    fenced = False

    def flush():
        text = "\n".join(current).strip()
        if text:
            blocks.append((" > ".join(title for _level, title in stack), text))
        current.clear()

    for line in body_lines(body):
        if line.strip().startswith("```"):
            fenced = not fenced
        found = None if fenced else HEADING.match(line)
        if found:
            flush()
            level, title = len(found.group(1)), " ".join(found.group(2).split())
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            continue
        current.append(line)
    flush()
    out: list[Section] = []
    for heading, text in blocks:
        pieces = _cut(text) if len(text.split()) > MAX_WORDS else [text]
        for number, piece in enumerate(pieces, 1):
            many = len(pieces) > 1
            out.append(Section(id=f"{path}#{len(out) + 1}", path=path, n=len(out) + 1,
                               heading=heading, text=piece, part=number if many else 0,
                               parts=len(pieces) if many else 0))
    return out


def _cut(text: str) -> list[str]:
    """Whole paragraphs in runs of about TARGET_WORDS words. A paragraph too long for one part
    (a pasted transcript, say) is cut at its sentences, and a run-on with no sentence ends at
    its words; the paragraph breaks that were there stay."""
    units: list[tuple[str, bool]] = []  # (text, starts a paragraph)
    for paragraph in (p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()):
        if len(paragraph.split()) <= MAX_WORDS:
            units.append((paragraph, True))
            continue
        first = True
        for sentence in (s for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()):
            words = sentence.split()
            chunks = ([sentence] if len(words) <= MAX_WORDS else
                      [" ".join(words[i:i + TARGET_WORDS])
                       for i in range(0, len(words), TARGET_WORDS)])
            for chunk in chunks:
                units.append((chunk, first))
                first = False
    pieces: list[list[tuple[str, bool]]] = []
    run: list[tuple[str, bool]] = []
    count = 0
    for unit in units:
        words = len(unit[0].split())
        if run and count + words > TARGET_WORDS:
            pieces.append(run)
            run, count = [], 0
        run.append(unit)
        count += words
    if run:
        pieces.append(run)
    return ["".join((("\n\n" if new else " ") if i else "") + part
                    for i, (part, new) in enumerate(piece)) for piece in pieces]


def outline(body: str, limit: int = 8) -> list[str]:
    """The headings a document is organized by, for its card: the deepest level that has
    more than one heading among its first few levels, so a deck lists its slide titles and a
    report its chapters."""
    seen: list[tuple[int, str]] = []
    fenced = False
    for line in body_lines(body):
        if line.strip().startswith("```"):
            fenced = not fenced
        found = None if fenced else HEADING.match(line)
        if found:
            title = SLIDE_OR_PAGE.sub("", " ".join(found.group(2).split())).strip()
            if title:
                seen.append((len(found.group(1)), title))
    if not seen:
        return []
    levels = sorted({level for level, _t in seen})
    chosen = next((level for level in levels
                   if sum(1 for lv, _t in seen if lv == level) > 1), levels[0])
    titles = list(dict.fromkeys(title for level, title in seen if level == chosen))
    return titles[:limit] + (["..."] if len(titles) > limit else [])


def opening(body: str, limit: int = 180) -> str:
    """The first words of a document's own text, for a card when nothing better says what
    it covers."""
    text = " ".join(line for line in body_lines(body) if not HEADING.match(line))
    return util.excerpt(text, limit)
