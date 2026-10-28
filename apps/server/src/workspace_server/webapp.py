"""The web app: where the server finds it, and a built copy for this version from the project's
GitHub release, so running Contxt never needs Node.js.

    contxt web               where the web app is, and whether it is built
    contxt web --download    the built app for this version, from its GitHub release

A release carries `web-dist.zip` and `web-dist.zip.sha256` (the release workflow makes both).
The download is checked against that checksum before anything is unpacked, every path in the
archive must stay inside its folder, and the new copy replaces the old one only once it is
complete. A private repository needs GITHUB_TOKEN set to a token that can read it.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from typing import Any

from workspace_core import __version__

from .settings import setting

DEFAULT_REPOSITORY = "rami-guzlan/Gnomon-Brain"
ASSET = "web-dist.zip"
CHECKSUM = ASSET + ".sha256"
API = "https://api.github.com"


class WebAppError(Exception):
    """The web app could not be fetched or placed; the message says why and what to do."""


def found(start: str | None = None) -> str | None:
    """The nearest built-or-not `apps/web/dist` folder above this package (a checkout's own)."""
    here = start or os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        here = os.path.dirname(here)
        candidate = os.path.join(here, "apps", "web", "dist")
        if os.path.isdir(candidate):
            return candidate
    return None


def location(web_dist: str | None) -> str | None:
    """Where the web app is or belongs: the setting, else the checkout's own folder (which
    may not exist yet), else None when this is no checkout at all."""
    if web_dist:
        return os.path.abspath(web_dist)
    existing = found()
    if existing:
        return existing
    from .homes import repository_root

    root = repository_root()
    return os.path.join(root, "apps", "web", "dist") if root else None


def built(folder: str | None) -> bool:
    return bool(folder) and os.path.isfile(os.path.join(str(folder), "index.html"))


def _trust_system_certificates() -> None:
    """The certificates the operating system trusts, as a company network's TLS inspection
    needs; verification stays on."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass


def _get(url: str, *, token: str | None, accept: str, timeout: float = 60) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "contxt"})
    if token:
        # Not forwarded on redirect: GitHub sends assets on from a signed storage address that
        # refuses a second credential.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return bytes(response.read())


def release_assets(repository: str, tag: str, token: str | None) -> dict[str, str]:
    """{asset name: its API address} for one release."""
    url = f"{API}/repos/{repository}/releases/tags/{tag}"
    try:
        data = json.loads(_get(url, token=token, accept="application/vnd.github+json"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise WebAppError(
                f"There is no release {tag} at github.com/{repository} (or the repository is "
                "private: set GITHUB_TOKEN to a token that can read it). Or build the web app "
                "yourself: npm install, then npm run build."
            ) from error
        raise WebAppError(f"GitHub answered {error.code} for release {tag}.") from error
    except urllib.error.URLError as error:
        raise WebAppError(f"GitHub could not be reached: {error.reason}") from error
    return {str(a["name"]): str(a["url"]) for a in data.get("assets") or []}


def download(
    target: str,
    *,
    repository: str | None = None,
    version: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Fetch this version's built web app and put it at `target`."""
    repository = repository or setting("RELEASE_REPOSITORY") or DEFAULT_REPOSITORY
    tag = f"v{version or __version__}"
    token = token if token is not None else (os.environ.get("GITHUB_TOKEN") or None)
    _trust_system_certificates()
    assets = release_assets(repository, tag, token)
    if ASSET not in assets or CHECKSUM not in assets:
        raise WebAppError(f"Release {tag} has no {ASSET} with its checksum.")
    octets = "application/octet-stream"
    try:
        archive = _get(assets[ASSET], token=token, accept=octets, timeout=300)
        listed = _get(assets[CHECKSUM], token=token, accept=octets).decode("utf-8", "replace")
    except urllib.error.URLError as error:
        raise WebAppError(f"The download stopped: {getattr(error, 'reason', error)}") from error
    expected = (listed.split() or [""])[0].lower()
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected:
        raise WebAppError("The download does not match its checksum, so nothing was changed.")
    unpack(archive, target)
    return {"target": os.path.abspath(target), "tag": tag, "bytes": len(archive), "sha256": actual}


def _rename(source: str, destination: str, attempts: int = 20) -> None:
    """os.replace, retried briefly: on Windows a virus scanner holds new files for a moment,
    and renaming their folder fails until it lets go."""
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def _remove(folder: str, attempts: int = 20) -> None:
    for attempt in range(attempts):
        if not os.path.isdir(folder):
            return
        try:
            shutil.rmtree(folder)
            return
        except OSError:
            time.sleep(0.05 * (attempt + 1))
    shutil.rmtree(folder, ignore_errors=True)


def unpack(archive: bytes, target: str) -> None:
    """Unpack into a fresh folder beside `target`, then swap it in: the server never serves a
    half-written app, and a bad archive changes nothing."""
    target = os.path.abspath(target)
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".web-new-", dir=parent)
    retired = None
    try:
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                for name in bundle.namelist():
                    where = os.path.abspath(os.path.join(staging, name))
                    if os.path.commonpath([staging, where]) != staging:
                        raise WebAppError(
                            f"The archive holds a path outside its folder ({name}); nothing "
                            "was changed."
                        )
                bundle.extractall(staging)
        except zipfile.BadZipFile as error:
            raise WebAppError(
                "The download is not a valid archive; nothing was changed."
            ) from error
        if not os.path.isfile(os.path.join(staging, "index.html")):
            raise WebAppError("The archive has no index.html; nothing was changed.")
        if os.path.exists(target):
            retired = tempfile.mkdtemp(prefix=".web-old-", dir=parent)
            os.rmdir(retired)
            _rename(target, retired)
        try:
            _rename(staging, target)
        except PermissionError as error:
            if retired:
                _rename(retired, target)  # the old app goes back where it was
                retired = None
            raise WebAppError(
                "Windows kept the new files busy (a virus scanner, usually), so nothing was "
                "changed. Try again in a moment."
            ) from error
    finally:
        for leftover in (staging, retired):
            if leftover:
                _remove(leftover)
