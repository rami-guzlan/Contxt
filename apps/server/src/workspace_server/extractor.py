"""Text from uploaded documents, using the Brain's importers (docx, pptx, html, pdf, and the
WebVTT and SubRip transcripts Teams and Zoom export): a plain text shadow for search, or Markdown
that keeps the document's shape (headings, slides, pages, a transcript's turns)."""

from __future__ import annotations

import os
import tempfile

from brainkit import importers

SUPPORTED = (".md", ".txt", ".html", ".htm", ".docx", ".pptx", ".pdf", ".vtt", ".srt")


class DocumentExtractor:
    def extract(self, data: bytes, filename: str, mime: str | None) -> str | None:
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in SUPPORTED:
            return None
        handle, path = tempfile.mkstemp(suffix=ext)
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            try:
                segments = importers.extract(path)
            except ValueError:
                return None  # e.g. a PDF without the optional pypdf installed
        finally:
            os.remove(path)
        text = "\n\n".join(text for _where, text in segments).strip()
        return text or None

    def markdown(self, data: bytes, filename: str) -> str | None:
        """The document as Markdown with its shape kept, or None when it cannot be read."""
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in SUPPORTED:
            return None
        handle, path = tempfile.mkstemp(suffix=ext)
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            try:
                text = importers.to_markdown(path)
            except ValueError:
                return None
        finally:
            os.remove(path)
        return text.strip() or None
