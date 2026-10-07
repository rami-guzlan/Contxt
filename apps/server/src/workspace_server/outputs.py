"""The outputs folder: what the person's AI made, organized, downloadable, and each file with
the context it was made from.

The folder is the home's `outputs/` (the CONTXT_EXPORTS_DIR setting). The app lists it, serves
a file for download, makes folders and moves or renames a file inside it; it never deletes
one and never reaches outside the folder.

WHAT A FILE WAS MADE FROM, when the app can know:

- a skill run that makes files worked in `skill-runs/<date>-<skill>/`: the run's task says what
  was asked of which skill, and the Brain's record says what each run was handed;
- an export from the app wrote it: its artifact, and the work that made that;
- an AI in a conversation saved it and said so (the Brain's `record_output`): what that
  conversation asked and got.

Anything else was made outside the app, and the page says so.
"""

from __future__ import annotations

import mimetypes
import os
import shutil
from datetime import UTC, datetime
from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, ValidationFailed
from workspace_core.workspace import Workspace

MARKER = ".run.json"  # a skill run still working in its folder (runners.py)
HIDDEN = (".", "~$")
KINDS = {
    ".md": "document",
    ".txt": "document",
    ".docx": "document",
    ".doc": "document",
    ".pdf": "pdf",
    ".pptx": "slides",
    ".ppt": "slides",
    ".xlsx": "spreadsheet",
    ".csv": "spreadsheet",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".svg": "image",
    ".webp": "image",
    ".html": "page",
    ".json": "data",
    ".mp3": "audio",
    ".m4a": "audio",
    ".wav": "audio",
    ".mp4": "video",
}
MAX_FILES = 2000
NAME_CHARS = set('\\/:*?"<>|')


def kind_of(name: str) -> str:
    return KINDS.get(os.path.splitext(name)[1].lower(), "file")


def _hidden(name: str) -> bool:
    return name.startswith(HIDDEN) or name.endswith((".contxt-new", ".tmp"))


class Outputs:
    def __init__(self, ws: Workspace, root: str) -> None:
        self.ws = ws
        self.root = os.path.abspath(root)

    # ---------------------------------------------------------------- reading

    def listing(self, who: Principal) -> dict[str, Any]:
        """Every file in the outputs folder, newest first, with its folder, size, kind and
        where it came from in one word; and every folder, for organizing."""
        who.require("artifacts.read")
        files: list[dict[str, Any]] = []
        folders: list[str] = []
        if os.path.isdir(self.root):
            for folder, dirs, names in os.walk(self.root):
                dirs[:] = sorted(d for d in dirs if not _hidden(d))
                rel_folder = self._rel(folder)
                if rel_folder:
                    folders.append(rel_folder)
                working = os.path.exists(os.path.join(folder, MARKER))
                for name in names:
                    if _hidden(name):
                        continue
                    path = os.path.join(folder, name)
                    try:
                        info = os.stat(path)
                    except OSError:
                        continue
                    rel = self._rel(path)
                    files.append(
                        {
                            "path": rel,
                            "name": name,
                            "folder": rel_folder,
                            "size": info.st_size,
                            "modified": datetime.fromtimestamp(info.st_mtime, UTC)
                            .isoformat()
                            .replace("+00:00", "Z"),
                            "kind": kind_of(name),
                            "from": "skill" if rel.startswith("skill-runs/") else None,
                            "working": working,
                        }
                    )
                    if len(files) >= MAX_FILES:
                        break
        files.sort(key=lambda f: f["modified"], reverse=True)
        return {"root": self.root, "folders": folders, "files": files}

    def file(self, who: Principal, rel: str) -> tuple[str, str, str]:
        """(absolute path, file name, media type) of one file, for download."""
        who.require("artifacts.read")
        path = self._inside(rel)
        if not os.path.isfile(path):
            raise NotFound(f"No file {rel} in the outputs folder.")
        name = os.path.basename(path)
        return path, name, mimetypes.guess_type(name)[0] or "application/octet-stream"

    def made_from(self, who: Principal, rel: str) -> dict[str, Any]:
        """What one file was made from, as far as the app can know (see the module)."""
        who.require("artifacts.read")
        path = self._inside(rel)
        if not os.path.isfile(path):
            raise NotFound(f"No file {rel} in the outputs folder.")
        out: dict[str, Any] = {"path": self._rel(path), "how": "unknown"}
        parts = self._rel(path).split("/")
        if len(parts) >= 3 and parts[0] == "skill-runs":
            folder = os.path.join(self.root, parts[0], parts[1])
            run = self.ws.skills.made_in(who, folder)
            if run is not None:
                out.update(how="skill", skill_run=run)
                out["given"] = [
                    dict(r, pieces=self.ws.rt.brain.work_given(r["id"])) for r in run["runs"]
                ]
                return out
        exported = self.ws.artifacts.exported_to(who, path)
        if exported is not None:
            out.update(how="export", export=exported)
            if exported.get("run_id"):
                out["given"] = [
                    {
                        "id": exported["run_id"],
                        "pieces": self.ws.rt.brain.work_given(str(exported["run_id"])),
                    }
                ]
            return out
        said = self.ws.rt.brain.made_from(path)
        if said is not None:
            out.update(how="chat", chat=said)
        return out

    # ---------------------------------------------------------------- organizing

    def make_folder(self, who: Principal, rel: str) -> dict[str, Any]:
        """A new folder inside the outputs folder (the owner's files: the owner organizes)."""
        who.require("workspace.admin")
        path = self._inside(rel, new=True)
        if os.path.exists(path):
            raise Conflict(f"{self._rel(path)} is already there.")
        os.makedirs(path)
        return {"path": self._rel(path)}

    def move(self, who: Principal, source: str, target: str) -> dict[str, Any]:
        """Move or rename one file inside the outputs folder. Never over another file."""
        who.require("workspace.admin")
        start = self._inside(source)
        if not os.path.isfile(start):
            raise NotFound(f"No file {source} in the outputs folder.")
        end = self._inside(target, new=True)
        if os.path.isdir(end):
            end = os.path.join(end, os.path.basename(start))
        if os.path.exists(end):
            raise Conflict(f"{self._rel(end)} is already there: choose another name.")
        if os.path.exists(os.path.join(os.path.dirname(start), MARKER)):
            raise Conflict("A skill run is still working in that folder: move it once it ends.")
        os.makedirs(os.path.dirname(end), exist_ok=True)
        shutil.move(start, end)
        return {"path": self._rel(end)}

    # ---------------------------------------------------------------- paths

    def _rel(self, path: str) -> str:
        rel = os.path.relpath(path, self.root)
        return "" if rel == "." else rel.replace(os.sep, "/")

    def _inside(self, rel: str, *, new: bool = False) -> str:
        """A path inside the outputs folder, or a refusal: no climbing out, no odd names."""
        text = str(rel or "").strip().replace("\\", "/").strip("/")
        if not text:
            raise ValidationFailed("Name a file or folder in the outputs folder.", field="path")
        parts = text.split("/")
        if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
            raise ValidationFailed("That is not a path inside the outputs folder.", field="path")
        if new and any(set(p) & NAME_CHARS or len(p) > 120 for p in parts):
            raise ValidationFailed(
                'A name may not hold \\ / : * ? " < > | and stays under 120 characters.',
                field="path",
            )
        path = os.path.abspath(os.path.join(self.root, *parts))
        real_root = os.path.realpath(self.root)
        real = os.path.realpath(path if os.path.exists(path) else os.path.dirname(path))
        if os.path.commonpath([real_root, real]) != real_root:
            raise ValidationFailed("That is not a path inside the outputs folder.", field="path")
        return path
