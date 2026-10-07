"""Files people and models made, served so they never run in the app's origin.

What is shown in place is what cannot run: pictures (not SVG, which can carry scripts), audio
and video. Everything else (a PDF, a deck, HTML a model wrote) downloads. Every response is
sandboxed and its type is never guessed by the browser, as the Brain's own files are.
"""

from __future__ import annotations

from fastapi.responses import FileResponse

SHOWN_IN_PLACE = ("image/png", "image/jpeg", "image/gif", "image/webp")
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-cache",
}


def shown_in_place(media: str | None) -> bool:
    kind = str(media or "").split(";")[0].strip().lower()
    return kind in SHOWN_IN_PLACE or kind.startswith(("audio/", "video/"))


def served(path: str, *, media: str | None, filename: str, download: bool) -> FileResponse:
    """A file to show in place when that is safe and asked for, else to download."""
    kind = str(media or "").split(";")[0].strip().lower() or "application/octet-stream"
    inline = not download and shown_in_place(kind)
    return FileResponse(
        path,
        media_type=kind,
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
        headers=HEADERS,
    )
