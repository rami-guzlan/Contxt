"""Homes: the folder that holds one Brain with its app data and outputs, made from a starter.

    <home>/
      brain/      the Brain: Markdown files, its own git repository
      data/       the app's database, uploaded files, sign-in key and backups
      outputs/    what your AI makes
      .env        this home's settings, with paths relative to the home

A starter is a Brain to begin from: `empty`, or one of the demo Brains, each a folder of
the repository's `brains/`. Making a home copies the starter into `brain/`, makes that a git
repository of its own (so every change to the Brain has a history and an undo), and writes
the settings. A home that already holds a Brain is never overwritten.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .settings import setting

MARK = os.path.join("vault", "brain.json")  # what makes a folder a starter Brain
FALLBACK_IDENTITY = ("Contxt", "contxt@localhost")  # when git has no user configured


class HomeError(Exception):
    """A home cannot be made as asked; the message says what to do instead."""


@dataclass(frozen=True)
class Starter:
    id: str
    name: str
    description: str
    path: str


def starters_root() -> str | None:
    """The folder of starter Brains: $CONTXT_STARTERS, else the nearest `brains/` with an
    `empty` starter above this package (the repository's own)."""
    explicit = setting("STARTERS")
    if explicit:
        return os.path.abspath(explicit) if os.path.isdir(explicit) else None
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        here = os.path.dirname(here)
        candidate = os.path.join(here, "brains")
        if os.path.isfile(os.path.join(candidate, "empty", MARK)):
            return candidate
    return None


def repository_root() -> str | None:
    """The folder that holds `brains/`: where `demos/` go."""
    root = starters_root()
    return os.path.dirname(root) if root else None


def starters(root: str | None = None) -> list[Starter]:
    """Every starter, the empty one first, then the demos by name."""
    root = root or starters_root()
    if not root:
        return []
    found = []
    for entry in sorted(os.listdir(root)):
        folder = os.path.join(root, entry)
        config = os.path.join(folder, MARK)
        if not os.path.isfile(config):
            continue
        with open(config, encoding="utf-8") as handle:
            data = json.load(handle)
        found.append(
            Starter(
                id=entry,
                name=str(data.get("name") or entry),
                description=str(data.get("description") or ""),
                path=folder,
            )
        )
    return sorted(found, key=lambda s: (s.id != "empty", s.id))


def find_starter(starter_id: str, root: str | None = None) -> Starter:
    known = starters(root)
    for starter in known:
        if starter.id == starter_id:
            return starter
    if not known:
        raise HomeError(
            "No starter Brains found. Run Contxt from its repository folder, or set "
            "CONTXT_STARTERS to its brains/ folder."
        )
    names = ", ".join(s.id for s in known)
    raise HomeError(f"There is no starter called {starter_id!r}. The starters: {names}.")


def free_port(start: int = 8790, tries: int = 100) -> int:
    """The first port from `start` that nothing listens on (for a demo's own server)."""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise HomeError(f"No free port between {start} and {start + tries - 1}.")


# Windows names its timezones its own way; the common ones, as the IANA zone that CLDR's
# windowsZones lists for each (the app asks for anything else during first-time setup).
WINDOWS_ZONES = {
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles",
    "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Atlantic Standard Time": "America/Halifax",
    "Canada Central Standard Time": "America/Regina",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "SA Pacific Standard Time": "America/Bogota",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "GTB Standard Time": "Europe/Bucharest",
    "FLE Standard Time": "Europe/Kyiv",
    "Russian Standard Time": "Europe/Moscow",
    "Turkey Standard Time": "Europe/Istanbul",
    "Israel Standard Time": "Asia/Jerusalem",
    "Egypt Standard Time": "Africa/Cairo",
    "South Africa Standard Time": "Africa/Johannesburg",
    "Arabian Standard Time": "Asia/Dubai",
    "India Standard Time": "Asia/Kolkata",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Singapore Standard Time": "Asia/Singapore",
    "China Standard Time": "Asia/Shanghai",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "E. Australia Standard Time": "Australia/Brisbane",
    "W. Australia Standard Time": "Australia/Perth",
    "New Zealand Standard Time": "Pacific/Auckland",
    "UTC": "UTC",
}


def iana_from_windows(name: str) -> str | None:
    return WINDOWS_ZONES.get(name.strip("\x00 ").strip())


def _windows_timezone() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        path = r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            name, _kind = winreg.QueryValueEx(key, "TimeZoneKeyName")
    except OSError:
        return None
    return iana_from_windows(str(name))


def _known(zone: str | None) -> str | None:
    if not zone:
        return None
    try:
        ZoneInfo(zone)
    except (ValueError, OSError, LookupError):
        return None
    return zone


def local_timezone() -> str | None:
    """This computer's IANA timezone: TZ, /etc/localtime, or Windows' own zone name; None when
    none says it plainly, and the app asks during first-time setup."""
    zone = os.environ.get("TZ", "")
    if "/" in zone and not zone.startswith(("/", ":")):
        return _known(zone)
    found = _windows_timezone()
    if found:
        return _known(found)
    try:
        target = os.path.realpath("/etc/localtime")
    except OSError:
        return None
    if "zoneinfo" + os.sep in target:
        return _known(target.split("zoneinfo" + os.sep, 1)[1].replace(os.sep, "/"))
    return None


def _git(folder: str, *args: str) -> subprocess.CompletedProcess[str]:
    flags = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
    try:
        return subprocess.run(
            ["git", *args],
            cwd=folder,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
            check=False,
            **flags,  # type: ignore[arg-type]
        )
    except OSError as error:
        raise HomeError(
            "Contxt needs git to keep your Brain's history: install it, then try again."
        ) from error


def _identity(folder: str) -> list[str]:
    known = _git(folder, "var", "GIT_AUTHOR_IDENT").returncode == 0
    name, email = FALLBACK_IDENTITY
    return [] if known else ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def start_history(brain: str, message: str) -> None:
    """Make `brain` a git repository of its own, with everything in it as the first commit.
    On Windows it allows long paths, so a Brain in a deep folder still commits."""
    steps = [["init", "-q", "-b", "main"]]
    if os.name == "nt":
        steps.append(["config", "core.longpaths", "true"])
    for args in [*steps, ["add", "-A"]]:
        done = _git(brain, *args)
        if done.returncode != 0:
            raise HomeError(f"git {args[0]} failed in {brain}: {done.stderr.strip()}")
    done = _git(brain, *_identity(brain), "commit", "-q", "--no-verify", "-m", message)
    if done.returncode != 0:
        raise HomeError(f"git commit failed in {brain}: {done.stderr.strip()}")


def write_startup_files(brain: str) -> None:
    """The Brain's own CLAUDE.md and AGENTS.md (what an agent working in its folder reads
    first), so a new Brain starts with none missing."""
    from brainkit.api import Brain

    engine = Brain(os.path.join(brain, "vault"), embeddings=False, repo_root=brain)
    try:
        engine.write_kernel()
    finally:
        engine.close()


def env_text(*, name: str, port: int, timezone: str | None) -> str:
    lines = [
        "# Contxt settings for this folder. Paths are relative to this file's folder.",
        "# Every setting is described in .env.example in the Contxt repository.",
        f"CONTXT_NAME={name}",
        f"CONTXT_PORT={port}",
        "CONTXT_BRAIN_VAULT=brain/vault",
        "CONTXT_DATA_DIR=data",
        "CONTXT_EXPORTS_DIR=outputs",
    ]
    if timezone:
        lines.append(f"CONTXT_TIMEZONE={timezone}")
    return "\n".join(lines) + "\n"


def has_brain(home: str) -> bool:
    return os.path.isfile(os.path.join(home, "brain", MARK))


def create_home(
    home: str, starter: Starter, *, port: int = 8787, name: str | None = None
) -> dict[str, str]:
    """Make `home` from `starter`: brain/ (with its own history), data/, outputs/ and .env.
    Refuses when home/brain already holds anything; keeps a .env that is already there."""
    home = os.path.abspath(home)
    brain = os.path.join(home, "brain")
    if os.path.exists(brain) and (not os.path.isdir(brain) or os.listdir(brain)):
        raise HomeError(
            f"{brain} already exists and is not empty, so nothing was changed. To start "
            "another Brain, choose another folder with --home, or move that one away first."
        )
    os.makedirs(home, exist_ok=True)
    shutil.copytree(
        starter.path,
        brain,
        ignore=shutil.ignore_patterns(".gitkeep", ".brain", "__pycache__"),
        dirs_exist_ok=True,
    )
    from brainkit import builtin

    builtin.copy_into(os.path.join(brain, "vault"))  # the skills every Brain comes with
    for folder in ("data", "outputs"):
        os.makedirs(os.path.join(home, folder), exist_ok=True)
    write_startup_files(brain)
    start_history(brain, f"A new Brain from the {starter.id} starter")
    env = os.path.join(home, ".env")
    if not os.path.isfile(env):
        with open(env, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(env_text(name=name or starter.name, port=port, timezone=local_timezone()))
    return {
        "home": home,
        "brain": brain,
        "vault": os.path.join(brain, "vault"),
        "data": os.path.join(home, "data"),
        "outputs": os.path.join(home, "outputs"),
        "env": env,
        "starter": starter.id,
    }
