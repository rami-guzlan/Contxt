"""Ask the Brain first (Release 1 plan, M08): the one instruction an AI app keeps in its own
standing-instructions file, so its model asks the Brain before answering.

Installing writes the instruction between two marker lines at the end of that file, and
removing takes out only what is between the markers; everything else in the file stays as
it was. The file is shared by every project the app works on, so it holds the instruction
alone, never the Brain's contents. It is not a lock: an app may still answer without asking,
and nothing here can stop it.
"""

from __future__ import annotations

import os

from .providers import BRAIN_INSTRUCTION

START = "<!-- contxt: ask the Brain first -->"
END = "<!-- /contxt -->"
# The standing-instructions file of each app that keeps one on this computer.
FILES: dict[str, tuple[str, ...]] = {
    "claude-code": (".claude", "CLAUDE.md"),
    "codex": (".codex", "AGENTS.md"),
    "gemini": (".gemini", "GEMINI.md"),
}


def path_for(app: str, home: str | None = None) -> str | None:
    parts = FILES.get(app)
    return os.path.join(home or os.path.expanduser("~"), *parts) if parts else None


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


def _without(text: str) -> str:
    start = text.find(START)
    if start < 0:
        return text
    end = text.find(END, start)
    end = len(text) if end < 0 else end + len(END)
    return (text[:start].rstrip("\n") + "\n" + text[end:].lstrip("\n")).strip("\n") + (
        "\n" if text[:start].strip() or text[end:].strip() else ""
    )


def status(app: str, home: str | None = None) -> dict[str, object]:
    """Whether the instruction is in the app's file, and where that file is."""
    path = path_for(app, home)
    if path is None:
        return {"app": app, "supported": False, "installed": False, "path": None}
    return {"app": app, "supported": True, "installed": START in _read(path), "path": path}


def install(app: str, home: str | None = None) -> dict[str, object]:
    """Add the instruction (or bring it up to date) at the end of the app's file."""
    path = path_for(app, home)
    if path is None:
        raise ValueError(f"{app} keeps no instructions file on this computer.")
    kept = _without(_read(path)).rstrip("\n")
    block = f"{START}\n{BRAIN_INSTRUCTION}\n{END}\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write((kept + "\n\n" if kept else "") + block)
    return status(app, home)


def remove(app: str, home: str | None = None) -> dict[str, object]:
    """Take the instruction out of the app's file, leaving the rest as it was."""
    path = path_for(app, home)
    if path is None:
        raise ValueError(f"{app} keeps no instructions file on this computer.")
    text = _read(path)
    if START in text:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_without(text))
    return status(app, home)
