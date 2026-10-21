"""A skill as files: brought in from a zip, a folder or a GitHub repository; taken away as a zip;
and copied into Claude Code, with a stamp saying which version went.

A skill is a folder with a SKILL.md: front matter (Contxt's fields, or the Agent Skills format's
`name` and `description`) and the steps, beside its own files (scripts/, assets/, references/).
Bringing one in reads that folder and hands it to the Brain with every file it accepts; the
files it does not (a secret, a type it does not keep, one too large) are listed as skipped.

The copy in Claude Code (`~/.claude/skills/<name>/`, or a project's `.claude/skills/<name>/`)
carries `.contxt-skill.json`: the skill, the hash of the SKILL.md that went and when. The skill's
page then says how many versions behind that copy is. Any connected AI can always read the
current version with skills_get; the copy is for tools that need the files on disk.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import Any

from brainkit import frontmatter, uploads
from workspace_core.clock import iso
from workspace_core.errors import Conflict, NotFound, ValidationFailed
from workspace_core.workspace import Workspace

from .library import REPO, FetchError, _git

MAX_ZIP = 30 * 1024 * 1024  # bytes a skill's files may add up to, unpacked
MAX_MEMBERS = 400
STAMP = ".contxt-skill.json"
# https://github.com/owner/name/tree/main/skills/brand-sheet: a skill inside a repository
TREE = re.compile(
    r"^https://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?"
    r"(?:/tree/[^/]+/(.+?))?/?$"
)
NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")


@dataclass
class Bundle:
    """One skill read from its files, ready for the Brain."""

    name: str
    category: str
    description: str
    body: str
    when_to_use: str = ""
    triggers: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    loads: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def fields(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "body": self.body,
            "when_to_use": self.when_to_use,
            "triggers": self.triggers,
            "artifacts": self.artifacts,
            "loads": self.loads,
            "depends_on": self.depends_on,
            "files": self.files,
        }


def _slug(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", str(text or "").lower()).strip("-")[:40]
    return slug or fallback


def read_bundle(files: dict[str, bytes], *, hint: str = "") -> Bundle:
    """The skill in a set of files (paths relative to what was brought in): its SKILL.md, its
    front matter and steps, and the files beside it the Brain keeps."""
    paths = {p.replace("\\", "/").strip("/"): data for p, data in files.items() if p.strip("/")}
    found = sorted(
        (p for p in paths if p.rsplit("/", 1)[-1].lower() == "skill.md"),
        key=lambda p: (p.count("/"), p),
    )
    if not found:
        raise ValidationFailed("There is no SKILL.md in it: a skill is a folder with a SKILL.md.")
    top = found[0].count("/")
    level = [p for p in found if p.count("/") == top]
    if len(level) > 1:
        names = ", ".join(p.rsplit("/", 2)[-2] if "/" in p else p for p in level[:5])
        raise ValidationFailed(
            f"It holds {len(level)} skills ({names}): bring them in one at a time."
        )
    chosen = found[0]
    root = chosen.rsplit("/", 1)[0] if "/" in chosen else ""
    meta, body, _errors = frontmatter.parse(paths[chosen].decode("utf-8", errors="replace"))
    folder = root.rsplit("/", 1)[-1] if root else ""
    name = str(meta.get("name") or folder or hint).strip()
    if not NAME_OK.match(name):
        name = _slug(name, "imported-skill")
    parent = root.rsplit("/", 2)[-2] if root.count("/") >= 1 else ""
    category = _slug(str(meta.get("category") or parent or "imported"), "imported")
    text = str(body or "").strip()
    description = " ".join(str(meta.get("description") or "").split())
    if not description:
        first = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "")
        description = first[:300]
    bundle = Bundle(
        name=name,
        category=category,
        description=description,
        body=text,
        when_to_use=" ".join(str(meta.get("when_to_use") or meta.get("when-to-use") or "").split()),
        triggers=frontmatter.as_list(meta.get("triggers")),
        artifacts=frontmatter.as_list(meta.get("artifacts")),
        loads=frontmatter.as_list(meta.get("loads")),
        depends_on=frontmatter.as_list(meta.get("depends_on")),
    )
    prefix = f"{root}/" if root else ""
    total = 0
    for path in sorted(paths):
        if path == chosen or not path.startswith(prefix):
            continue
        rel = path[len(prefix) :]
        data = paths[path]
        try:
            clean = uploads.clean_relpath(rel)
            if not clean.lower().endswith(uploads.SKILL_FILE_EXT):
                raise uploads.Refused("the Brain does not keep this type of file in a skill")
            if len(data) > uploads.MAX_FILE:
                raise uploads.Refused("larger than 10 MB")
        except uploads.Refused as exc:
            bundle.skipped.append(f"{rel}: {exc}")
            continue
        total += len(data)
        if total > uploads.MAX_PROPOSAL or len(bundle.files) >= uploads.MAX_FILES:
            bundle.skipped.append(f"{rel}: past what one skill may carry")
            continue
        bundle.files.append(
            {"path": clean, "content_base64": base64.b64encode(data).decode("ascii")}
        )
    return bundle


def read_zip(data: bytes) -> dict[str, bytes]:
    """The files in a zip, refused when it is too large to unpack or reaches outside itself."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValidationFailed("That is not a zip file.") from exc
    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) > MAX_MEMBERS:
        raise ValidationFailed(f"The zip holds more than {MAX_MEMBERS} files.")
    if sum(m.file_size for m in members) > MAX_ZIP:
        raise ValidationFailed("The zip unpacks to more than 30 MB.")
    out: dict[str, bytes] = {}
    for member in members:
        name = member.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/") or name.startswith("__MACOSX/"):
            continue
        out[name] = archive.read(member)
    return out


def read_folder(folder: str) -> dict[str, bytes]:
    """The files under a folder on this computer (a repository's skill folder)."""
    out: dict[str, bytes] = {}
    total = 0
    for here, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            full = os.path.join(here, name)
            rel = os.path.relpath(full, folder).replace("\\", "/")
            size = os.path.getsize(full)
            total += size
            if total > MAX_ZIP or len(out) >= MAX_MEMBERS:
                raise ValidationFailed("That skill's folder is larger than 30 MB.")
            with open(full, "rb") as handle:
                out[rel] = handle.read()
    return out


def fetch_repo_skill(
    url: str, cache: str, *, path: str = "", git: Any = None
) -> tuple[dict[str, bytes], str]:
    """A skill's files from a GitHub repository (the repository, or a folder in it named in the
    address or by `path`), with a shallow clone into the app's cache; and where it came from."""
    found = TREE.match(str(url or "").strip())
    if not found or not REPO.match(f"https://github.com/{found.group(1)}/{found.group(2)}"):
        raise FetchError(
            "Give a GitHub address, such as https://github.com/owner/name/tree/main/skills/x."
        )
    git = git or _git
    owner, name, inside = found.group(1), found.group(2), found.group(3) or ""
    folder = os.path.join(cache, f"{owner}__{name}")
    if os.path.isdir(os.path.join(folder, ".git")):
        git(["git", "-C", folder, "fetch", "--depth", "1", "--quiet", "origin", "HEAD"])
        git(["git", "-C", folder, "reset", "--hard", "--quiet", "FETCH_HEAD"])
    else:
        os.makedirs(cache, exist_ok=True)
        git(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--quiet",
                f"https://github.com/{owner}/{name}.git",
                folder,
            ]
        )
    rel = (path or inside).strip().strip("/")
    target = (
        os.path.realpath(os.path.join(folder, *rel.split("/"))) if rel else os.path.realpath(folder)
    )
    if not (
        target == os.path.realpath(folder) or target.startswith(os.path.realpath(folder) + os.sep)
    ):
        raise FetchError(f"{rel} is not a folder in the repository.")
    if not os.path.isdir(target):
        raise FetchError(f"{rel} is not a folder in the repository.")
    where = f"https://github.com/{owner}/{name}" + (f"/tree/HEAD/{rel}" if rel else "")
    return read_folder(target), where


# ---------------------------------------------------------------- out


def zip_skill(folder: str, name: str) -> bytes:
    """The skill's folder as a zip, under a folder named after it."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for here, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for file in sorted(names):
                if file.startswith("."):
                    continue
                full = os.path.join(here, file)
                rel = os.path.relpath(full, folder).replace("\\", "/")
                archive.write(full, f"{name}/{rel}")
    return out.getvalue()


def claude_code_place(name: str, project_dir: str | None = None) -> str:
    """Where Claude Code keeps the skill: the person's own skills, or a project's."""
    if project_dir:
        base = os.path.abspath(project_dir)
        if not os.path.isdir(base):
            raise ValidationFailed(
                f"There is no folder {base} on this computer.", field="project_dir"
            )
        return os.path.join(base, ".claude", "skills", name)
    return os.path.join(os.path.expanduser("~"), ".claude", "skills", name)


def push(ws: Workspace, who: Any, name: str, *, project_dir: str | None = None) -> dict[str, Any]:
    """Copy the skill into Claude Code with a stamp of the version that went. A folder there
    that Contxt did not put there is left alone."""
    who.require("workspace.admin")
    skill = ws.skills.find(who, name)
    folder = ws.rt.brain.skill_folder(skill.name)
    if not folder:
        raise NotFound(f"The files of /{skill.name} are not on this computer.")
    versions = ws.rt.brain.skill_versions(skill.name) or []
    place = claude_code_place(skill.name, project_dir)
    if os.path.isdir(place):
        if not os.path.isfile(os.path.join(place, STAMP)):
            raise Conflict(
                f"Claude Code has a skill {skill.name} that did not come from Contxt ({place}): "
                "rename or remove it first."
            )
        shutil.rmtree(place)
    shutil.copytree(folder, place, ignore=shutil.ignore_patterns(".*"))
    stamp = {
        "skill": skill.name,
        "hash": versions[0].get("hash") if versions else None,
        "ref": versions[0].get("ref") if versions else None,
        "pushed_at": iso(ws.rt.clock.now()),
    }
    with open(os.path.join(place, STAMP), "w", encoding="utf-8") as handle:
        json.dump(stamp, handle, indent=1)
    pushes = dict(ws.info().settings.get("skill_pushes") or {})
    places = [p for p in pushes.get(skill.name) or [] if p != place]
    pushes[skill.name] = [place, *places][:10]
    ws.update_settings(who, settings={"skill_pushes": pushes})
    return {"place": place, **stamp, "behind": 0}


def user_copy(name: str, hashes: list[Any]) -> dict[str, Any] | None:
    """The person's own Claude Code copy of a skill, and how many versions behind the Brain's
    it is (`hashes` newest first); None when there is no copy."""
    try:
        with open(os.path.join(claude_code_place(name), STAMP), encoding="utf-8") as handle:
            stamp = json.load(handle)
    except (OSError, ValueError):
        return None
    behind = hashes.index(stamp.get("hash")) if stamp.get("hash") in hashes else None
    return {"behind": behind, "pushed_at": stamp.get("pushed_at")}


def pushed(ws: Workspace, who: Any, name: str) -> list[dict[str, Any]]:
    """Each copy in Claude Code, and how many versions behind the Brain's it is."""
    skill = ws.skills.find(who, name)
    versions = ws.rt.brain.skill_versions(skill.name) or []
    hashes = [v.get("hash") for v in versions]
    places = list((ws.info().settings.get("skill_pushes") or {}).get(skill.name) or [])
    user = claude_code_place(skill.name)
    if user not in places:
        places.append(user)
    out = []
    for place in places:
        try:
            with open(os.path.join(place, STAMP), encoding="utf-8") as handle:
                stamp = json.load(handle)
        except (OSError, ValueError):
            continue
        behind = hashes.index(stamp.get("hash")) if stamp.get("hash") in hashes else None
        out.append(
            {
                "place": place,
                "user": place == user,
                "pushed_at": stamp.get("pushed_at"),
                "behind": behind,
            }
        )
    return out
