"""Bring outside documents into the brain without bypassing governance.

SCOUT (`brain scout <folder>`) reads an explicitly chosen folder, extracts text with its
location (file, page, paragraph), drops what the brain already knows, and files each new
candidate as a PENDING proposal with that location as evidence. Scout findings never apply
on their own, even in the caller's own scope: a document is not an owner.

INTAKE (`brain intake <file>`) files one source document as a reference with a pointer note
(see uploads.add_file), under `references/` as Markdown with the original bytes kept in the
runtime library. The capture policy treats it as a file from a chat: filed at once as an undo
point, except under the regulated preset, where it is staged outside the vault until the
owner approves.

Gates run before anything is read: an explicit folder that is not a drive root, excluded
names (keys, credentials, .env, private folders), a size ceiling, supported formats only,
and a sensitivity label check ("confidential", "do not ingest") on the extracted text.
"""
from __future__ import annotations

import fnmatch
import hashlib
import html.parser
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from . import util

SUPPORTED = (".md", ".txt", ".html", ".htm", ".docx", ".pptx", ".pdf", ".vtt", ".srt")
EXCLUDE = (".git", "__pycache__", ".venv", "venv", "node_modules", "private", ".env*", "*.env",
           "*.key", "*.pem", "*.pfx", "*.p12", "*.crt", "*.cer", "$RECYCLE.BIN",
           "System Volume Information", ".brain")
SENSITIVE = ("do not ingest", "highly confidential", "strictly confidential", "restricted")
MAX_BYTES = 25 * 1024 * 1024
MIN_CLAIM, MAX_CLAIM = 60, 1200
KNOWN_THRESHOLD = 0.72


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


# ------------------------------------------------------------------ extraction

class _HTMLText(html.parser.HTMLParser):
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "section",
             "article"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _docx_paragraphs(path):
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_BYTES:
            raise ValueError("document.xml is too large")
        root = ElementTree.fromstring(archive.read(info))
    for paragraph in root.iter(ns + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(ns + "t")).strip()
        if text:
            yield text


def _pptx_slides(path):
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        names = sorted((n for n in archive.namelist()
                        if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                       key=lambda n: int(re.findall(r"\d+", n)[-1]))
        for number, name in enumerate(names, 1):
            root = ElementTree.fromstring(archive.read(name))
            text = " ".join((node.text or "").strip() for node in root.iter(ns + "t")
                            if (node.text or "").strip())
            if text:
                yield number, text


def extract(path) -> list[tuple[str, str]]:
    """[(location, text)] segments for one file."""
    ext = os.path.splitext(path)[1].lower()
    out = []
    if ext in (".md", ".txt"):
        text = util.read_text(path)
        _meta_lines = 0
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end > 0:
                text = text[end + 4:]
        for number, block in enumerate(re.split(r"\n\s*\n", text), 1):
            block = block.strip()
            if block:
                out.append((f"block {number}", block))
    elif ext in (".html", ".htm"):
        parser = _HTMLText()
        parser.feed(util.read_text(path))
        for number, block in enumerate(re.split(r"\n\s*\n", "".join(parser.parts)), 1):
            block = " ".join(block.split())
            if block:
                out.append((f"block {number}", block))
    elif ext == ".docx":
        out = [(f"paragraph {i}", t) for i, t in enumerate(_docx_paragraphs(path), 1)]
    elif ext == ".pptx":
        out = [(f"slide {n}", t) for n, t in _pptx_slides(path)]
    elif ext in (".vtt", ".srt"):
        turns = transcript_turns(util.read_text(path))
        out = [(f"at {_clock(t.start)}", f"{t.speaker}: {t.text}" if t.speaker else t.text)
               for t in turns]
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise ValueError("PDF needs `pip install pypdf`") from exc
        reader = PdfReader(path)
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            for number, block in enumerate(re.split(r"\n\s*\n", text), 1):
                block = " ".join(block.split())
                if block:
                    out.append((f"page {page_number} block {number}", block))
    return out


# ------------------------------------------------------------------ documents as Markdown
#
# A document filed in the brain keeps its shape, so the brain can find and quote the part a
# request is about (sections.py): Word headings stay headings, every slide and every PDF page
# becomes one, lists and tables stay lists and tables, and a slide's speaker notes travel
# with it. `extract` above stays as it is: scout reads claims, not documents.

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
HEADING_STYLE = re.compile(r"^(?:heading|titre|[uü]berschrift|kop|encabezado|t[ií]tulo|titolo|"
                           r"rubrik)\s*([1-6])$")
SKIP_PLACEHOLDERS = {"sldNum", "ftr", "dt", "hdr", "sldImg"}


def to_markdown(path) -> str:
    """One document as Markdown that keeps its shape. Raises ValueError when it cannot be
    read (an unsupported type, a PDF without pypdf installed)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".md", ".txt"):
        text = util.read_text(path)
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end > 0:
                text = text[end + 4:]
        return text.strip()
    if ext in (".html", ".htm"):
        parser = _HTMLMarkdown()
        parser.feed(util.read_text(path))
        blocks = [" ".join(b.split()) for b in re.split(r"\n\s*\n", "".join(parser.parts))]
        return "\n\n".join(b for b in blocks if b and b not in ("-", "#"))
    if ext == ".docx":
        return _docx_markdown(path)
    if ext == ".pptx":
        return _pptx_markdown(path)
    if ext == ".pdf":
        return _pdf_markdown(path)
    if ext in (".vtt", ".srt"):
        return transcript_markdown(transcript_turns(util.read_text(path)))
    raise ValueError(f"cannot read {ext or 'files without an extension'}")


# ------------------------------------------------------------------ transcripts
#
# A meeting's transcript as Teams or Zoom export it (WebVTT, SubRip): timed cues, often a
# speaker per cue. Read as turns, one paragraph each with who spoke and when ("**Dana** [04:12]
# ..."), so the brain quotes a turn whole and a reader sees the conversation, not the cues.

CUE_TIME = re.compile(r"^\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})")
VOICE = re.compile(r"<v(?:\.[^\s>]+)*\s+([^>]+)>", re.IGNORECASE)
TAG = re.compile(r"</?[a-zA-Z][^>]*>")
# "Dana Ruiz: we keep the video" (Zoom, SubRip): a name of up to four words before a colon.
NAMED = re.compile(r"^([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3}):\s+(.+)$", re.DOTALL)
TURN_WORDS = 160          # a long turn is cut here into paragraphs that keep their time
QUIET_TURN_SECONDS = 60   # without speakers, a new paragraph after this long


@dataclass
class Turn:
    start: float
    speaker: str
    text: str


def _seconds(stamp: str) -> float:
    parts = stamp.replace(",", ".").split(":")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def _clock(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def transcript_turns(text: str) -> list:
    """The cues of a WebVTT or SubRip transcript as turns: consecutive cues by one speaker run
    together, up to TURN_WORDS words a paragraph."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\ufeff", "")):
        lines = [line for line in block.split("\n") if line.strip()]
        timing = next((i for i, line in enumerate(lines) if CUE_TIME.match(line)), None)
        if timing is None:
            continue
        start = _seconds(CUE_TIME.match(lines[timing]).group(1))
        raw = " ".join(lines[timing + 1:])
        voice = VOICE.search(raw)
        speaker = " ".join(voice.group(1).split()) if voice else ""
        words = " ".join(TAG.sub("", raw).split())
        if not speaker:
            named = NAMED.match(words)
            if named:
                speaker, words = named.group(1), named.group(2)
        if words:
            cues.append(Turn(start, speaker, words))
    turns: list[Turn] = []
    for cue in cues:
        last = turns[-1] if turns else None
        same = last is not None and last.speaker == cue.speaker and len(
            last.text.split()) + len(cue.text.split()) <= TURN_WORDS and (
            cue.speaker or cue.start - last.start < QUIET_TURN_SECONDS)
        if same:
            last.text = f"{last.text} {cue.text}"
        else:
            turns.append(Turn(cue.start, cue.speaker, cue.text))
    return turns


def transcript_markdown(turns) -> str:
    """Turns as Markdown paragraphs: "**Speaker** [mm:ss] text", or "[mm:ss] text"."""
    out = []
    for turn in turns:
        who = f"**{turn.speaker}** " if turn.speaker else ""
        out.append(f"{who}[{_clock(turn.start)}] {turn.text}")
    return "\n\n".join(out)


class _HTMLMarkdown(_HTMLText):
    """HTML text with its headings and list items marked the Markdown way."""

    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r"h[1-6]", tag) and not self.skip:
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li" and not self.skip:
            self.parts.append("\n\n- ")
        else:
            super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n")
        super().handle_endtag(tag)


def _docx_markdown(path) -> str:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_BYTES:
            raise ValueError("document.xml is too large")
        root = ElementTree.fromstring(archive.read(info))
        names = _docx_style_names(archive)
    body = root.find(W + "body")
    out: list[str] = []
    if body is not None:
        _docx_blocks(body, names, out)
    return "\n\n".join(out)


def _docx_style_names(archive) -> dict:
    """{style id: style name}, lowercased: a heading's id differs by language and template
    ("Heading1", "berschrift1", "1"), its name less so ("heading 1")."""
    try:
        root = ElementTree.fromstring(archive.read("word/styles.xml"))
    except (KeyError, ElementTree.ParseError):
        return {}
    out = {}
    for style in root.iter(W + "style"):
        style_id = style.get(W + "styleId")
        name = style.find(W + "name")
        if style_id and name is not None:
            out[style_id] = " ".join(str(name.get(W + "val") or "").lower().split())
    return out


def _docx_level(paragraph, names) -> int:
    """The heading level of a Word paragraph (1 to 6), or 0 for body text."""
    props = paragraph.find(W + "pPr")
    if props is None:
        return 0
    style = props.find(W + "pStyle")
    if style is not None:
        style_id = str(style.get(W + "val") or "")
        for name in (names.get(style_id, ""), style_id.lower()):
            if name == "title":
                return 1
            if name == "subtitle":
                return 2
            found = HEADING_STYLE.match(name)
            if found:
                return int(found.group(1))
    outline = props.find(W + "outlineLvl")
    if outline is not None:
        try:
            level = int(outline.get(W + "val") or "9") + 1
        except ValueError:
            level = 0
        if 1 <= level <= 6:
            return level
    return 0


def _docx_text(element) -> str:
    parts = []
    for node in element.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append(" ")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts).strip()


def _docx_blocks(container, names, out) -> None:
    for child in container:
        if child.tag == W + "p":
            text = _docx_text(child)
            if not text:
                continue
            level = _docx_level(child, names)
            props = child.find(W + "pPr")
            if level:
                out.append("#" * level + " " + " ".join(text.split()))
            elif props is not None and props.find(W + "numPr") is not None:
                out.append("- " + " ".join(text.split()))
            else:
                out.append(text)
        elif child.tag == W + "tbl":
            rows = []
            for row in child.iter(W + "tr"):
                cells = [" ".join(_docx_text(cell).split()) for cell in row.findall(W + "tc")]
                if any(cells):
                    rows.append(cells)
            if rows:
                out.append(_table(rows))
        elif child.tag == W + "sdt":
            content = child.find(W + "sdtContent")
            if content is not None:
                _docx_blocks(content, names, out)


def _table(rows) -> str:
    width = max(len(r) for r in rows)
    lines = []
    for number, row in enumerate(rows):
        cells = [c.replace("|", "\\|") for c in row] + [""] * (width - len(row))
        lines.append("| " + " | ".join(cells) + " |")
        if number == 0:
            lines.append("|" + " --- |" * width)
    return "\n".join(lines)


def _rels(archive, part) -> dict:
    """{relationship id: (type, target part)} for one part of an Office package."""
    import posixpath
    folder, _, name = part.rpartition("/")
    try:
        root = ElementTree.fromstring(archive.read(f"{folder}/_rels/{name}.rels"))
    except (KeyError, ElementTree.ParseError):
        return {}
    out = {}
    for rel in root.iter(PKG + "Relationship"):
        target = str(rel.get("Target") or "")
        resolved = posixpath.normpath(posixpath.join(folder, target)) if target else ""
        out[rel.get("Id")] = (str(rel.get("Type") or ""), resolved)
    return out


def _slide_order(archive) -> list[str]:
    """Slide parts in the order the deck shows them (not the order they were made)."""
    names = set(archive.namelist())
    try:
        root = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
        rels = _rels(archive, "ppt/presentation.xml")
        order = [rels[s.get(R + "id")][1] for s in root.iter(P + "sldId")
                 if s.get(R + "id") in rels]
        order = [name for name in order if name in names]
        if order:
            return order
    except (KeyError, ElementTree.ParseError):
        pass
    return sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                  key=lambda n: int(re.findall(r"\d+", n)[-1]))


def _placeholder(shape):
    found = shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
    return (found.get("type") or "body") if found is not None else None


def _lines(shape) -> list[str]:
    out = []
    for paragraph in shape.iter(A + "p"):
        text = " ".join("".join(node.text or "" for node in paragraph.iter(A + "t")).split())
        if text:
            out.append(text)
    return out


def _pptx_notes(archive, slide) -> str:
    for kind, target in _rels(archive, slide).values():
        if not kind.endswith("/notesSlide"):
            continue
        try:
            root = ElementTree.fromstring(archive.read(target))
        except (KeyError, ElementTree.ParseError):
            return ""
        return " ".join(line for shape in root.iter(P + "sp")
                        if _placeholder(shape) == "body" for line in _lines(shape))
    return ""


def _pptx_markdown(path) -> str:
    out = []
    with zipfile.ZipFile(path) as archive:
        for number, name in enumerate(_slide_order(archive), 1):
            info = archive.getinfo(name)
            if info.file_size > MAX_BYTES:
                raise ValueError(f"{name} is too large")
            tree = ElementTree.fromstring(archive.read(info)).find(f"{P}cSld/{P}spTree")
            title, body = "", []
            if tree is not None:
                for shape in tree.iter(P + "sp"):
                    kind = _placeholder(shape)
                    if kind in SKIP_PLACEHOLDERS:
                        continue
                    lines = _lines(shape)
                    if lines and not title and kind in ("title", "ctrTitle"):
                        title = " ".join(lines)
                    else:
                        body += lines
                for frame in tree.iter(P + "graphicFrame"):
                    for row in frame.iter(A + "tr"):
                        cells = [" ".join("".join(t.text or "" for t in cell.iter(A + "t")).split())
                                 for cell in row.findall(A + "tc")]
                        if any(cells):
                            body.append(" | ".join(cells))
            notes = _pptx_notes(archive, name)
            if not (title or body or notes):
                continue
            block = [f"## Slide {number}" + (f": {title}" if title else "")]
            if body:
                block.append("\n".join(body))
            if notes:
                block.append("Speaker notes: " + notes)
            out.append("\n\n".join(block))
    return "\n\n".join(out)


def _pdf_markdown(path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise ValueError("PDF needs `pip install pypdf`") from exc
    out = []
    for number, page in enumerate(PdfReader(path).pages, 1):
        blocks = [" ".join(b.split()) for b in re.split(r"\n\s*\n", page.extract_text() or "")]
        blocks = [b for b in blocks if b]
        if blocks:
            out.append(f"## Page {number}\n\n" + "\n\n".join(blocks))
    return "\n\n".join(out)


def _sha(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(name) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE)


def gate_folder(folder) -> str | None:
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        return f"{folder} is not a folder"
    anchor = Path(folder).anchor
    if os.path.normcase(os.path.normpath(folder)) == os.path.normcase(os.path.normpath(anchor)):
        return "Scout refuses a drive or filesystem root; choose a specific folder"
    return None


def candidate_files(folder):
    for current, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not _excluded(d) and not d.startswith("."))
        for name in sorted(files):
            if _excluded(name) or not name.lower().endswith(SUPPORTED):
                continue
            path = os.path.join(current, name)
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield path


def _claims(segments):
    for location, text in segments:
        flat = " ".join(text.split())
        if not (MIN_CLAIM <= len(flat) <= MAX_CLAIM):
            continue
        if flat.startswith(("#", "|", "```")) or flat.count("|") > 3:
            continue
        if not re.search(r"[a-z]{3,}.*[.!?:]", flat, re.I):
            continue
        yield location, flat


# ------------------------------------------------------------------ scout

def scout(brain, folder, *, dry_run=False, scope=None, limit=25, principal=None):
    refusal = gate_folder(folder)
    if refusal:
        return _result(f"Scout refused: {refusal}.", {"status": "refused"}, True)
    from . import governance
    folder = os.path.abspath(folder)
    who = brain.principal(principal)
    caller = brain.caller(who)
    if not isinstance(caller, tuple):
        return caller
    chain, partitions = caller
    st = brain.state()
    notes = st.router.admitted_notes(chain, partitions)
    seen: set[str] = set()
    findings, skipped = [], {"known": 0, "sensitive": 0, "unreadable": 0, "duplicate": 0}
    for path in candidate_files(folder):
        try:
            segments = extract(path)
        except Exception:
            skipped["unreadable"] += 1
            continue
        joined = " ".join(t for _l, t in segments[:200]).lower()
        if any(label in joined for label in SENSITIVE):
            skipped["sensitive"] += 1
            continue
        digest = None
        for location, claim in _claims(segments):
            key = util.normalize(claim)
            if key in seen:
                skipped["duplicate"] += 1
                continue
            seen.add(key)
            ranked = st.router.score_notes(claim, notes)
            if ranked and ranked[0].score >= KNOWN_THRESHOLD:
                skipped["known"] += 1
                continue
            digest = digest or _sha(path)
            layer, topic = governance.guess_placement(brain, claim, chain, partitions)
            findings.append({"path": path, "location": location, "text": claim,
                             "sha256": digest, "layer": layer, "topic": topic,
                             "closest": ranked[0].item.id if ranked else None,
                             "closest_score": ranked[0].score if ranked else 0.0})
            if len(findings) >= int(limit or 25):
                break
        if len(findings) >= int(limit or 25):
            break
    if dry_run:
        lines = [f"- [{f['layer']}/{f['topic']}] {util.excerpt(f['text'], 140)} "
                 f"({os.path.relpath(f['path'], folder)}, {f['location']})" for f in findings]
        return _result(f"Scout found {len(findings)} new candidate(s) (dry run, nothing "
                       f"written). Skipped: {skipped}.\n" + "\n".join(lines),
                       {"findings": findings, "skipped": skipped})
    proposed = []
    target_scope = scope or (chain[-2] if len(chain) > 1 else chain[0])
    for finding in findings:
        res = governance.propose_note(
            brain, area=finding["layer"], topic=finding["topic"], text=finding["text"],
            scope=target_scope, principal=who,
            source=f"scout: {finding['path']} ({finding['location']})",
            evidence=f"sha256 {finding['sha256']}; closest existing note "
                     f"{finding['closest']} ({finding['closest_score']:.2f})",
            reason="found by scout; placement guessed", force_pending=True,
            extra={"placement": "guessed"})
        proposed.append({"ok": not res.is_error, "message": res.text.splitlines()[0]})
    ok = sum(1 for p in proposed if p["ok"])
    return _result(f"Scout proposed {ok} note(s) for review from {folder}. Skipped: {skipped}.",
                   {"proposed": proposed, "skipped": skipped, "findings": len(findings)})


# ------------------------------------------------------------------ intake

def intake(brain, file_path, *, title=None, topic=None, principal=None):
    """File one document as a reference with a pointer note, by the capture policy for a file
    from a chat: at once as an undo point, or waiting for review under regulated."""
    from . import uploads
    path = os.path.abspath(file_path)
    if os.path.isfile(path) and not path.lower().endswith(SUPPORTED):
        return _result("Intake supports .md .txt .html .docx .pptx .pdf .vtt .srt only.",
                       {"status": "unsupported"}, True)
    res = uploads.add_file(brain, source_path=path, title=title, topic=topic,
                           principal=principal, purpose="reference",
                           source=f"intake: {os.path.basename(path)}",
                           reason="filed by intake")
    if not res.is_error:
        res.data["reference"] = res.data.get("target")
    return res
