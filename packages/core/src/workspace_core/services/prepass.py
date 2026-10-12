"""The pre-pass (brain-logic plan 7.2, step 1): what code finds in something brought in before
any model reads it, for free.

- Split by structure: speaker turns in a transcript, headings in a document, slides in a deck,
  else paragraphs.
- Drop boilerplate: recording notices, sign-offs, unsubscribe and confidentiality footers.
- Find dates, figures and the names of people and organizations, so a model is pointed at them.
- Find sensitive spans with deterministic recognizers (emails, phone numbers, card and account
  numbers, ID numbers), for redaction in what goes to a cloud model (decision 13).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Each recognizer, with what replaces what it finds in redacted text.
SENSITIVE: dict[str, tuple[re.Pattern[str], str]] = {
    "email": (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[email]"),
    "id": (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[ID number]"),
    "iban": (re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}\b"), "[account number]"),
    "account": (re.compile(r"(?<![\w.])(?:\d[ -]?){12,19}(?![\w.])"), "[account number]"),
    "phone": (
        re.compile(
            r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}"
            r"(?!\w)"
        ),
        "[phone]",
    ),
}
BOILERPLATE = re.compile(
    r"^\s*(this (meeting|call) is being recorded.*|recording (started|stopped).*|"
    r"sent from my (iphone|android|phone).*|unsubscribe.*|to stop receiving these.*|"
    r"this (e-?mail|message) (and any attachments )?(is|are) confidential.*|"
    r"confidential(ity)? notice.*|transcribed by .*|\[?(music|silence|crosstalk)\]?)\s*$",
    re.IGNORECASE,
)
SPEAKER = re.compile(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?([A-Z][\w.' -]{1,40}):\s+\S")
HEADING = re.compile(r"^\s*#{1,6}\s+\S|^\s*(slide|page)\s+\d+\b", re.IGNORECASE)
MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|"
    "july|august|september|october|november|december"
)
DATE = re.compile(
    rf"\b(\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}|"
    rf"(?:{MONTHS})\.? \d{{1,2}}(?:, \d{{4}})?|\d{{1,2}} (?:{MONTHS})(?: \d{{4}})?)\b",
    re.IGNORECASE,
)
FIGURE = re.compile(
    r"(?<![\w.])(?:[$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?[kmb]n?)?|\d[\d,]*(?:\.\d+)?\s?(?:%|percent|"
    r"k\b|m\b|bn\b|million|billion|thousand|hours?|days?|weeks?|people|users|attendees)|"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?)",
    re.IGNORECASE,
)
NAME = re.compile(r"\b([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[A-Z]\.|of|and|&)){1,3})\b")
NOT_NAMES = {"The", "This", "That", "When", "What", "We", "It", "In", "On", "And", "But"}
CHUNK_CHARS = 1500


@dataclass
class Chunk:
    """A piece of the text, cut where its structure turns."""

    text: str
    kind: str  # turn | section | paragraph
    speaker: str = ""


@dataclass
class Found:
    """What the pre-pass found in one text."""

    chunks: list[Chunk] = field(default_factory=list)
    dropped: int = 0  # boilerplate lines left out
    dates: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    sensitive: dict[str, int] = field(default_factory=dict)  # recognizer: count

    def summary(self) -> str:
        """One line a model reads before the text."""
        parts = []
        speakers = sorted({c.speaker for c in self.chunks if c.speaker})
        if speakers:
            parts.append("speakers: " + ", ".join(speakers[:12]))
        if self.dates:
            parts.append("dates: " + ", ".join(self.dates[:10]))
        if self.figures:
            parts.append("figures: " + ", ".join(self.figures[:10]))
        if self.names:
            parts.append("names: " + ", ".join(self.names[:12]))
        return "; ".join(parts)


def sensitive_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, recognizer) for each sensitive span, earliest first, none overlapping."""
    spans: list[tuple[int, int, str]] = []
    for name, (pattern, _label) in SENSITIVE.items():
        for found in pattern.finditer(text):
            if not any(found.start() < end and start < found.end() for start, end, _n in spans):
                spans.append((found.start(), found.end(), name))
    return sorted(spans)


def redact(text: str) -> str:
    """The text with each sensitive span replaced by what it is: [email], [phone], ..."""
    out, last = [], 0
    for start, end, name in sensitive_spans(text):
        out += [text[last:start], SENSITIVE[name][1]]
        last = end
    out.append(text[last:])
    return "".join(out)


def clean(text: str) -> tuple[str, int]:
    """The text without its boilerplate lines, and how many were dropped."""
    kept, dropped = [], 0
    for line in str(text or "").splitlines():
        if BOILERPLATE.match(line):
            dropped += 1
            continue
        kept.append(line)
    return "\n".join(kept), dropped


def split(text: str) -> list[Chunk]:
    """Speaker turns, else sections under headings or slides, else paragraphs (each held to
    about CHUNK_CHARS)."""
    lines = str(text or "").splitlines()
    if sum(1 for line in lines if SPEAKER.match(line)) >= 2:
        chunks: list[Chunk] = []
        for line in lines:
            found = SPEAKER.match(line)
            if found:
                chunks.append(Chunk(line.strip(), "turn", found.group(1).strip()))
            elif line.strip() and chunks:
                chunks[-1].text += "\n" + line.strip()
        return chunks
    if any(HEADING.match(line) for line in lines):
        sections: list[Chunk] = []
        for line in lines:
            if HEADING.match(line) or not sections:
                sections.append(Chunk(line.strip(), "section"))
            elif line.strip():
                sections[-1].text += "\n" + line.strip()
        return [c for c in sections if c.text.strip()]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]
    out: list[Chunk] = []
    for paragraph in paragraphs:
        if out and len(out[-1].text) + len(paragraph) < CHUNK_CHARS:
            out[-1].text += "\n\n" + paragraph
        else:
            out.append(Chunk(paragraph, "paragraph"))
    return out


def for_model(text: str, *, redacting: bool) -> str:
    """What a model reads of something brought in: without its boilerplate, and with its
    sensitive spans redacted when the preset says so (decision 13)."""
    kept, _dropped = clean(text)
    return redact(kept) if redacting else kept


def run(text: str) -> Found:
    """The whole pre-pass over one text."""
    kept, dropped = clean(text)
    found = Found(chunks=split(kept), dropped=dropped)
    found.dates = list(dict.fromkeys(m.group(0) for m in DATE.finditer(kept)))
    found.figures = list(dict.fromkeys(m.group(0).strip() for m in FIGURE.finditer(kept)))
    found.names = list(
        dict.fromkeys(
            m.group(1)
            for m in NAME.finditer(kept)
            if m.group(1).split()[0] not in NOT_NAMES and not DATE.fullmatch(m.group(1))
        )
    )
    for _start, _end, name in sensitive_spans(kept):
        found.sensitive[name] = found.sensitive.get(name, 0) + 1
    return found
