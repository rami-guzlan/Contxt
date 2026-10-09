"""The Library's sources: a web page or a GitHub repository, fetched and kept as Markdown.

A page is fetched over HTTPS and turned into Markdown with the Brain's own reader. A repository
is cloned shallow into the app's cache (outside the Brain) with the person's own git sign-in,
and kept as a snapshot: its README, its folder tree and the files they pick. Contxt never
stores a token, and git is told never to ask for one on screen.

Both go through the same gates as anything filed in the Brain: sizes are capped, files that
look like secrets are never read, and the Brain refuses text carrying a sensitivity label.
Fetching uses the system's certificate store (truststore), so a network that inspects TLS
works without turning checks off.

What the Brain files is only the text: when it was fetched lives on the document's card
(`fetched_at`), and when it was last checked lives here, in the app's data folder, so a check
that found nothing new changes nothing in the Brain's history.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import ssl
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from brainkit import importers, uploads
from workspace_core.errors import ValidationFailed, WorkspaceError
from workspace_core.services.brain import Brain as BrainService
from workspace_core.workspace import Workspace

log = logging.getLogger("workspace.library")

MAX_PAGE = 3 * 1024 * 1024  # bytes read from one page
MAX_REPO_FILE = 200 * 1024  # bytes of one file picked from a repository
MAX_SNAPSHOT = 1024 * 1024  # characters in one repository snapshot
MAX_PICKED = 20  # files picked from one repository
TREE_LINES = 200
TREE_DEPTH = 3
TIMEOUT = 20  # seconds to fetch a page
GIT_TIMEOUT = 180  # seconds for a clone or a fetch
TEXT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
)
REPO = re.compile(
    r"^https://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
README = re.compile(r"^readme(\.(md|markdown|rst|txt))?$", re.IGNORECASE)
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
}
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
CADENCE = {"weekly": dt.timedelta(days=7), "monthly": dt.timedelta(days=30)}


class FetchError(ValidationFailed):
    """A source that could not be fetched, said in words the person can act on."""

    code = "fetch_failed"


def ssl_context() -> ssl.SSLContext:
    """The system's certificate store when truststore is there, else Python's defaults."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:  # pragma: no cover - truststore ships with the app
        return ssl.create_default_context()


@dataclass(frozen=True)
class Source:
    """What was fetched: where from, a title, and the Markdown the Brain keeps."""

    url: str
    title: str
    markdown: str
    paths: tuple[str, ...] = ()
    commit: str | None = None


Opener = Callable[[urllib.request.Request], Any]


def _open(request: urllib.request.Request) -> Any:
    return urllib.request.urlopen(request, timeout=TIMEOUT, context=ssl_context())


def fetch_page(url: str, *, opener: Opener | None = None) -> Source:
    """One web page as Markdown, with its title."""
    url = str(url or "").strip()
    if not url.lower().startswith("https://"):
        raise FetchError("Only https:// addresses can be fetched.")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Contxt Library",
            "Accept": "text/html,text/markdown,text/plain;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with (opener or _open)(request) as response:
            final = str(response.geturl() or url)
            kind = (response.headers.get_content_type() or "").lower()
            charset = response.headers.get_content_charset() or "utf-8"
            data = response.read(MAX_PAGE + 1)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"The page answered {exc.code}: it may be private or gone.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise FetchError(f"Could not reach the page: {reason}.") from exc
    if not final.lower().startswith("https://"):
        raise FetchError("The page sent the request on to an address that is not https://.")
    if len(data) > MAX_PAGE:
        raise FetchError("The page is larger than 3 MB.")
    if kind not in TEXT_TYPES:
        raise FetchError(f"The address gives {kind or 'something unknown'}, not a page of text.")
    text = data.decode(charset, errors="replace")
    if kind in ("text/html", "application/xhtml+xml"):
        found = TITLE.search(text)
        title = " ".join(found.group(1).split()) if found else ""
        markdown = _html_markdown(text)
    else:
        markdown = text.strip()
        heading = next((ln[2:].strip() for ln in markdown.splitlines() if ln.startswith("# ")), "")
        title = heading
    if not markdown:
        raise FetchError("The page has no readable text.")
    title = title or final.split("://", 1)[-1].rstrip("/")
    body = f"# {title}\n\nSource: {final}\n\n{markdown}\n"
    return Source(url=final, title=title[:200], markdown=body)


def _html_markdown(html: str) -> str:
    """The Brain's own reader turns the page into Markdown, the same way it reads a filed
    .html document."""
    handle, path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(html)
        return importers.to_markdown(path)
    finally:
        os.remove(path)


Git = Callable[[list[str]], str]


def _git(argv: list[str]) -> str:
    """Run git without a window and without asking for a sign-in on screen."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env=env,
            check=False,
            creationflags=flags,
        )
    except FileNotFoundError as exc:
        raise FetchError(
            "Git is not installed on this computer, so a repository can't be linked."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FetchError("The repository took too long to fetch.") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip().splitlines()[-1:] or [""]
        raise FetchError(
            "Git could not fetch the repository. If it is private, sign in to GitHub with git on "
            f"this computer first. ({detail[0][:160]})"
        )
    return done.stdout


def snapshot_repo(url: str, paths: list[str], cache: str, *, git: Git = _git) -> Source:
    """A GitHub repository as one Markdown snapshot: its README, its folder tree, and the
    files picked from it, at the commit fetched."""
    found = REPO.match(str(url or "").strip())
    if not found:
        raise FetchError(
            "Give a GitHub repository's address, such as https://github.com/owner/name."
        )
    owner, name = found.group(1), found.group(2)
    if len(paths) > MAX_PICKED:
        raise FetchError(f"Pick at most {MAX_PICKED} files from a repository.")
    folder = os.path.join(cache, f"{owner}__{name}")
    address = f"https://github.com/{owner}/{name}.git"
    if os.path.isdir(os.path.join(folder, ".git")):
        git(["git", "-C", folder, "fetch", "--depth", "1", "--quiet", "origin", "HEAD"])
        git(["git", "-C", folder, "reset", "--hard", "--quiet", "FETCH_HEAD"])
    else:
        os.makedirs(cache, exist_ok=True)
        git(["git", "clone", "--depth", "1", "--quiet", address, folder])
    commit = git(["git", "-C", folder, "rev-parse", "HEAD"]).strip()[:40]
    parts = [
        f"# {owner}/{name}",
        "",
        f"Repository: https://github.com/{owner}/{name} at commit {commit[:12]}.",
    ]
    readme = next((f for f in sorted(os.listdir(folder)) if README.match(f)), None)
    if readme:
        parts += ["", "## README", "", _read_text(os.path.join(folder, readme), MAX_REPO_FILE * 2)]
    parts += ["", "## Folder tree", "", "```text", *_tree(folder), "```"]
    picked: list[str] = []
    size = sum(len(p) for p in parts)
    for raw in paths:
        try:
            rel = uploads.clean_relpath(str(raw).replace("\\", "/").strip().strip("/"))
        except uploads.Refused as exc:
            raise FetchError(f"{raw} can't be read from the repository: {exc}.") from exc
        full = os.path.realpath(os.path.join(folder, *rel.split("/")))
        if not full.startswith(os.path.realpath(folder) + os.sep) or not os.path.isfile(full):
            raise FetchError(f"{rel} is not a file in the repository.")
        if os.path.getsize(full) > MAX_REPO_FILE:
            raise FetchError(f"{rel} is larger than 200 KB.")
        text = _read_text(full, MAX_REPO_FILE)
        if "\x00" in text:
            raise FetchError(f"{rel} is not a text file.")
        language = os.path.splitext(rel)[1].lstrip(".").lower()
        block = ["", f"## {rel}", "", f"```{language}", text.rstrip(), "```"]
        size += sum(len(line) for line in block)
        if size > MAX_SNAPSHOT:
            raise FetchError("The files picked add up to more than 1 MB; pick fewer.")
        parts += block
        picked.append(rel)
    return Source(
        url=f"https://github.com/{owner}/{name}",
        title=f"{owner}/{name}",
        markdown="\n".join(parts).strip() + "\n",
        paths=tuple(picked),
        commit=commit,
    )


def _read_text(path: str, limit: int) -> str:
    with open(path, "rb") as handle:
        data = handle.read(limit)
    return data.decode("utf-8", errors="replace").strip()


def _tree(root: str) -> list[str]:
    """The repository's folders and files a few levels down, folders first."""
    lines: list[str] = []

    def walk(folder: str, depth: int) -> None:
        if depth > TREE_DEPTH or len(lines) >= TREE_LINES:
            return
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return
        dirs = [
            n
            for n in names
            if os.path.isdir(os.path.join(folder, n))
            and n not in SKIP_DIRS
            and not n.startswith(".")
        ]
        files = [
            n for n in names if os.path.isfile(os.path.join(folder, n)) and not n.startswith(".")
        ]
        for name in dirs:
            if len(lines) >= TREE_LINES:
                return
            lines.append(f"{'  ' * (depth - 1)}{name}/")
            walk(os.path.join(folder, name), depth + 1)
        for name in files:
            if len(lines) >= TREE_LINES:
                return
            lines.append(f"{'  ' * (depth - 1)}{name}")

    walk(root, 1)
    if len(lines) >= TREE_LINES:
        lines.append("…")
    return lines


def today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


# ---------------------------------------------------------------- keeping items current


class Checks:
    """When each Library item was last checked against its source: the app's own record,
    kept beside its data, never in the Brain."""

    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "library-checks.json")
        self._lock = threading.Lock()

    def read(self) -> dict[str, str]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                found = json.load(handle)
            return {str(k): str(v) for k, v in found.items()} if isinstance(found, dict) else {}
        except (OSError, ValueError):
            return {}

    def mark(self, path: str, when: str | None = None) -> None:
        with self._lock:
            known = self.read()
            known[path] = when or dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(known, handle, indent=1, sort_keys=True)


class Library:
    """Fetching for the Library, and filing what was fetched through the Brain."""

    def __init__(
        self, ws: Workspace, data_dir: str, *, opener: Opener | None = None, git: Git = _git
    ) -> None:
        self.ws = ws
        self.cache = os.path.join(data_dir, "library-cache")
        self.checks = Checks(data_dir)
        self.opener = opener
        self.git = git

    @property
    def brain(self) -> BrainService:
        return self.ws.brain

    def fetch(
        self, *, url: str | None = None, repo: str | None = None, paths: list[str] | None = None
    ) -> Source:
        if repo:
            return snapshot_repo(repo, list(paths or []), self.cache, git=self.git)
        if url:
            return fetch_page(url, opener=self.opener)
        raise FetchError("Give a page's address or a repository's.")

    def refresh(self, who: Any, path: str, *, wait: bool = False) -> dict[str, Any]:
        """Fetch an item again. Changed text files a new version (at once when the person
        asked, waiting for review when it came due on its own); unchanged text changes nothing
        in the Brain, and only the check is recorded."""
        item = self.brain.library_item(who, path)
        if not (item["source_url"] or item["source_repo"]):
            raise FetchError(
                "It was not fetched from anywhere, so there is nothing to fetch again."
            )
        source = self.fetch(
            url=None if item["source_repo"] else item["source_url"],
            repo=item["source_repo"],
            paths=item["source_paths"],
        )
        result = self.brain.add_file(
            who,
            filename=os.path.basename(path),
            data=source.markdown.encode("utf-8"),
            title=item["title"],
            replaces=path,
            wait=wait,
            library={"fetched_at": today()},
        )
        self.checks.mark(path)
        status = "unchanged" if result.status == "duplicate" else result.status
        return {
            "status": status,
            "message": result.message,
            "path": path,
            "proposal_id": result.proposal_id,
        }

    def due(self, who: Any) -> list[dict[str, Any]]:
        """Items whose refresh came round: last checked (or fetched) longer ago than their
        cadence."""
        checked = self.checks.read()
        now = dt.datetime.now(dt.UTC)
        out = []
        for item in self.brain.library(who):
            cadence = CADENCE.get(str(item.get("refresh") or ""))
            if cadence is None or not (item.get("source_url") or item.get("source_repo")):
                continue
            last = _moment(checked.get(item["path"])) or _moment(item.get("fetched_at"))
            if last is None or now - last >= cadence:
                out.append(item)
        return out


def _moment(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)


class LibraryWorker:
    """Fetches Library items again when their refresh comes round, one at a time; what
    changed waits for the person's review."""

    def __init__(self, ws: Workspace, library: Library, interval: float = 900.0) -> None:
        self.ws = ws
        self.library = library
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> int:
        owner = self.ws.owner()
        done = 0
        for item in self.library.due(owner)[:5]:
            try:
                self.library.refresh(owner, item["path"], wait=True)
            except WorkspaceError as exc:
                log.info("could not refresh %s: %s", item["path"], exc)
                self.library.checks.mark(item["path"])  # try again at the next cadence
            done += 1
        return done

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="library", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.run_once()
            except Exception:
                log.exception("library refresh failed")
