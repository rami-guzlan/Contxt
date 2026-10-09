"""Files brought to Moving in, read into the text it sifts: any type, zips included.

Each uploaded file becomes one source (a zip, one source holding what its files say, each under
its own name), so the Brain splits, checks and sifts it like a paste:

- documents (Word, PowerPoint, PDF, HTML, Markdown, text, Teams and Zoom transcripts) through
  the Brain's importers, their shape kept;
- an AI app's data export: ChatGPT's and Claude's `conversations.json` give the person's own
  messages, newest conversations first (what they told the AI); any other JSON gives its
  sentences;
- anything else that reads as text (CSV, YAML, XML, Cursor rules, files with no extension);
- a zip: every file inside, one level of zips within it too, within limits on how many files
  and how much text, so a zip bomb is refused rather than read.

What cannot be read is named with why (a picture, a recording, a spreadsheet, a locked file),
never guessed at. Nothing is written anywhere: a document is read through a temporary file
removed at once, and a name inside a zip is only ever a label.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any

from .extractor import DocumentExtractor

MAX_CHARS = 200_000  # one source, as Moving in takes it
MAX_FILE = 25 * 1024 * 1024  # one file inside a zip, read
MAX_TOTAL = 60 * 1024 * 1024  # everything read from one zip
MAX_MEMBERS = 300
DOCUMENTS = (".md", ".txt", ".html", ".htm", ".docx", ".pptx", ".pdf", ".vtt", ".srt")
TEXTS = (
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".xml",
    ".log",
    ".ini",
    ".toml",
    ".mdc",
    ".rst",
    ".org",
    ".tex",
    ".rtf",
    ".cursorrules",
    ".text",
    ".markdown",
)
PICTURES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic", ".tif", ".tiff")
RECORDINGS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".webm", ".mkv", ".avi")
SHEETS = (".xlsx", ".xls", ".ods", ".numbers")
SKIP_PARTS = ("__MACOSX", ".DS_Store", "Thumbs.db")
# Keys whose values say nothing a person would want kept (ids, times, links).
NOISE_KEYS = ("id", "uuid", "url", "href", "src", "model", "type", "status", "hash", "file")


def _why_not(name: str) -> str | None:
    ext = os.path.splitext(name)[1].lower()
    if ext in PICTURES:
        return "a picture: Moving in reads words, not images"
    if ext in RECORDINGS:
        return "a recording: bring it in through Capture, which transcribes it"
    if ext in SHEETS:
        return "a spreadsheet: save it as CSV to bring it in"
    return None


def _decoded(data: bytes) -> str | None:
    """The bytes as text, when they are text: UTF-8 (or UTF-16 with its mark), mostly
    printable."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None
    sample = text[:4000]
    if not sample.strip():
        return None
    printable = sum(1 for c in sample if c.isprintable() or c in "\n\r\t")
    return text if printable / max(1, len(sample)) > 0.95 else None


def _conversations(found: Any) -> tuple[str, str] | None:
    """A ChatGPT or Claude export's conversations: the person's own messages, newest first."""
    if not isinstance(found, list) or not found or not isinstance(found[0], dict):
        return None
    first = found[0]
    chats: list[tuple[str, str, list[str]]] = []
    if "mapping" in first:  # ChatGPT
        for chat in found:
            said = []
            nodes = (chat.get("mapping") or {}).values() if isinstance(chat, dict) else []
            ordered = sorted(
                (n.get("message") or {} for n in nodes if isinstance(n, dict)),
                key=lambda m: float(m.get("create_time") or 0),
            )
            for message in ordered:
                if (message.get("author") or {}).get("role") != "user":
                    continue
                parts = (message.get("content") or {}).get("parts") or []
                text = "\n".join(p for p in parts if isinstance(p, str)).strip()
                if text:
                    said.append(text)
            if said:
                chats.append(
                    (str(chat.get("update_time") or ""), str(chat.get("title") or ""), said)
                )
        app = "ChatGPT"
    elif "chat_messages" in first:  # Claude
        for chat in found:
            said = [
                str(m.get("text") or "").strip()
                for m in chat.get("chat_messages") or []
                if isinstance(m, dict)
                and m.get("sender") == "human"
                and str(m.get("text") or "").strip()
            ]
            if said:
                chats.append((str(chat.get("updated_at") or ""), str(chat.get("name") or ""), said))
        app = "Claude"
    else:
        return None
    chats.sort(key=lambda c: c[0], reverse=True)
    lines = []
    for _when, title, said in chats:
        lines.append(f"## {title or 'A conversation'}")
        lines.extend(said)
        lines.append("")
    return app, "\n".join(lines).strip()


def _sentences(found: Any) -> str:
    """Any other JSON: its sentences, once each, without ids, times and links."""
    out: list[str] = []
    seen: set[str] = set()

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, str(k))
        elif isinstance(value, list):
            for v in value:
                walk(v, key)
        elif isinstance(value, str):
            low = key.lower()
            text = value.strip()
            if (
                len(text) >= 12
                and " " in text
                and not any(low == n or low.endswith(("_" + n, n + "s")) for n in NOISE_KEYS)
                and not low.endswith(("_at", "_time", "time", "date"))
                and text not in seen
            ):
                seen.add(text)
                out.append(text)

    walk(found)
    return "\n".join(out)


class UploadReader:
    def __init__(self, extractor: DocumentExtractor | None = None) -> None:
        self.extractor = extractor or DocumentExtractor()

    def read(self, files: list[tuple[str, bytes]]) -> dict[str, Any]:
        """{"sources": [{"kind", "label", "text", "note"}], "skipped": [{"name", "why"}]}:
        one source per file that reads."""
        sources: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for name, data in files:
            label = os.path.basename(name or "") or "A file"
            if _is_zip(name, data):
                joined, inner_skipped = self._zip(data, depth=0)
                skipped += [
                    {"name": f"{label}: {s['name']}", "why": s["why"]} for s in inner_skipped
                ]
                if joined:
                    sources.append(self._source(label, joined, kind="paste"))
                elif not inner_skipped:
                    skipped.append({"name": label, "why": "an empty zip"})
                continue
            kind, text, why = self._one(name, data)
            if text:
                sources.append(self._source(label, text, kind=kind))
            else:
                skipped.append({"name": label, "why": why or "nothing in it reads as text"})
        return {"sources": sources, "skipped": skipped}

    @staticmethod
    def _source(label: str, text: str, *, kind: str) -> dict[str, Any]:
        note = ""
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
            note = f"Read up to its first {MAX_CHARS:,} characters."
        return {"kind": kind, "label": label[:80], "text": text, "note": note}

    def _one(self, name: str, data: bytes) -> tuple[str, str | None, str | None]:
        """(kind, text, why not) for one file that is not a zip."""
        why = _why_not(name)
        if why:
            return "paste", None, why
        ext = os.path.splitext(name or "")[1].lower()
        base = os.path.basename(name or "").lower()
        if base in ("claude.md", "agents.md", ".cursorrules") or ext == ".mdc":
            text = _decoded(data)
            return "instructions", text, None if text else "it is not text"
        if ext == ".json":
            text = _decoded(data)
            if text is None:
                return "paste", None, "it is not text"
            try:
                found = json.loads(text)
            except ValueError:
                return "paste", text, None
            chats = _conversations(found)
            if chats is not None:
                app, said = chats
                return ("chatgpt" if app == "ChatGPT" else "claude"), said, None
            return "paste", _sentences(found) or None, "it holds no sentences"
        if ext in DOCUMENTS:
            markdown = self.extractor.markdown(data, name)
            if markdown:
                return "paste", markdown, None
            if ext == ".pdf":
                return "paste", None, "a PDF with no text in it (a scan?), or one that is locked"
            return "paste", None, "it could not be read"
        text = _decoded(data)
        if text is not None:
            return "paste", text, None
        return "paste", None, "not a kind of file Moving in can read"

    def _zip(self, data: bytes, *, depth: int) -> tuple[str, list[dict[str, str]]]:
        """What a zip's files say, each under its name, and what was left out."""
        skipped: list[dict[str, str]] = []
        parts: list[str] = []
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            return "", [{"name": "the zip", "why": "it is damaged"}]
        with archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if len(members) > MAX_MEMBERS:
                skipped.append(
                    {"name": "the zip", "why": f"only its first {MAX_MEMBERS} files were read"}
                )
                members = members[:MAX_MEMBERS]
            total = 0
            for member in members:
                name = member.filename
                base = os.path.basename(name)
                if any(part in name for part in SKIP_PARTS) or (
                    base.startswith(".") and base != ".cursorrules"
                ):
                    continue
                if member.flag_bits & 0x1:
                    skipped.append({"name": name, "why": "it is locked with a password"})
                    continue
                if member.file_size > MAX_FILE:
                    skipped.append({"name": name, "why": "it is too large to read here"})
                    continue
                if total + member.file_size > MAX_TOTAL:
                    skipped.append({"name": name, "why": "the zip holds too much to read at once"})
                    break
                total += member.file_size
                inner = archive.read(member)
                if _is_zip(name, inner):
                    if depth >= 1:
                        skipped.append({"name": name, "why": "a zip inside a zip inside a zip"})
                        continue
                    nested, more = self._zip(inner, depth=depth + 1)
                    skipped += [{"name": f"{name}: {s['name']}", "why": s["why"]} for s in more]
                    if nested:
                        parts.append(f"# {name}\n\n{nested}")
                    continue
                _kind, text, why = self._one(name, inner)
                if text:
                    parts.append(f"# {name}\n\n{text.strip()}")
                else:
                    skipped.append({"name": name, "why": why or "nothing in it reads as text"})
        return "\n\n".join(parts), skipped


def _is_zip(name: str, data: bytes) -> bool:
    """A zip archive, not a document that is one inside (Word, PowerPoint, Excel)."""
    ext = os.path.splitext(name or "")[1].lower()
    if ext in (".docx", ".pptx", ".xlsx", ".odt", ".ods", ".odp", ".epub", ".jar"):
        return False
    return ext == ".zip" or data[:4] == b"PK\x03\x04"
