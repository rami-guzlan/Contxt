"""Third-party notices: every package Contxt ships, with its license, from the lock files.

    uv run python scripts/third_party_notices.py           write THIRD_PARTY_NOTICES.md
    uv run python scripts/third_party_notices.py --check   exit 1 when the file is out of date

Python: the runtime packages `uv export` lists (no development tools), each with the license
its installed metadata declares. The web app: the packages bundled into it
(`npm ls --omit=dev`), each with the license in its package.json. Licenses that ask for more
than a notice (copyleft), and packages that state none, are listed first, for review.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib import metadata

from packaging.markers import Marker
from packaging.requirements import Requirement

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "THIRD_PARTY_NOTICES.md")
REVIEW = re.compile(r"GPL|MPL|EPL|CDDL|SSPL|EUPL|OSL|Commons Clause|BUSL|unknown", re.I)
CLASSIFIER = re.compile(r"License :: (?:OSI Approved :: )?(.+)")
# The opening words of the common license texts, for a package whose metadata names none but
# ships the text itself.
TEXTS = (
    (re.compile(r"\bMIT License\b|Permission is hereby granted, free of charge", re.I), "MIT"),
    (re.compile(r"Apache License,?\s+Version 2\.0", re.I), "Apache-2.0"),
    (re.compile(r"BSD 3-Clause|Redistributions .{0,400}?Neither the name", re.I | re.S),
     "BSD-3-Clause"),
    (re.compile(r"BSD 2-Clause", re.I), "BSD-2-Clause"),
    (re.compile(r"\bISC License\b", re.I), "ISC"),
    (re.compile(r"Mozilla Public License,?\s+(?:Version )?2\.0", re.I), "MPL-2.0"),
    (re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE", re.I), "LGPL"),
    (re.compile(r"GNU GENERAL PUBLIC LICENSE", re.I), "GPL"),
)


def _run(*command: str) -> str:
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          shell=sys.platform == "win32" and command[0] == "npm", check=False)
    if not done.stdout.strip():
        raise SystemExit(f"{' '.join(command)} printed nothing: {done.stderr.strip()[:300]}")
    return done.stdout


def _python_license(name: str) -> str:
    try:
        info = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "unknown (not installed on this system)"
    expression = info.get("License-Expression")
    if expression:
        return expression.strip()
    classifiers = [
        m.group(1) for c in info.get_all("Classifier") or [] if (m := CLASSIFIER.match(c))
    ]
    if classifiers:
        return "; ".join(dict.fromkeys(classifiers))
    text = (info.get("License") or "").strip()
    if text and len(text) <= 60 and "\n" not in text:
        return text
    return _license_file(name) or "unknown (see the package)"


def _license_file(name: str) -> str | None:
    """The license a package's own license file names, for metadata that names none."""
    dist = metadata.distribution(name)
    for path in dist.files or []:
        if "licen" not in path.name.lower() and "copying" not in path.name.lower():
            continue
        try:
            text = path.read_text(encoding="utf-8")[:3000]
        except (OSError, UnicodeDecodeError):
            continue
        for pattern, spdx in TEXTS:
            if pattern.search(text):
                return f"{spdx} (from its license file)"
    return None


def python_packages() -> list[tuple[str, str, str]]:
    rows = []
    exported = _run("uv", "export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-workspace",
                    "--format", "requirements-txt")
    for line in exported.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        requirement = Requirement(line)
        version = next(iter(requirement.specifier)).version if requirement.specifier else ""
        name = requirement.name
        if requirement.marker and not Marker(str(requirement.marker)).evaluate():
            rows.append((name, version, f"{_python_license(name)}; only on some systems"))
            continue
        rows.append((name, version, _python_license(name)))
    return sorted(rows, key=lambda r: r[0].lower())


def web_packages() -> list[tuple[str, str, str]]:
    tree = json.loads(_run("npm", "ls", "--omit=dev", "--all", "--json", "--long"))
    found: dict[tuple[str, str], str] = {}

    def walk(node: dict, *, top: bool = False) -> None:
        for name, child in (node.get("dependencies") or {}).items():
            if not isinstance(child, dict):
                continue
            workspace = str(child.get("resolved", "")).startswith("file:") or name.startswith(
                "@workspace/")
            if not workspace and child.get("version"):
                license_ = child.get("license") or "unknown"
                if isinstance(license_, dict):
                    license_ = license_.get("type") or "unknown"
                found[(name, str(child["version"]))] = str(license_)
            walk(child)

    walk(tree, top=True)
    return sorted(((n, v, lic) for (n, v), lic in found.items()), key=lambda r: r[0].lower())


def render(python: list[tuple[str, str, str]], web: list[tuple[str, str, str]]) -> str:
    review = [(kind, n, v, lic) for kind, rows in (("Python", python), ("Web app", web))
              for n, v, lic in rows if REVIEW.search(lic)]
    lines = [
        "# Third-party notices",
        "",
        "Contxt is built on these packages. Each keeps its own license; this list is generated",
        "from the lock files by `scripts/third_party_notices.py` and names the license each",
        "package declares. Development tools that are not shipped are left out.",
        "",
        "## For review",
        "",
    ]
    if review:
        lines += ["Licenses that ask for more than a notice, or packages that state none:", ""]
        lines += [f"- {kind}: {n} {v}: {lic}" for kind, n, v, lic in review]
    else:
        lines += ["None: every package states a permissive license."]
    for title, rows in (("Python packages", python), ("Web app packages", web)):
        lines += ["", f"## {title} ({len(rows)})", "", "| Package | Version | License |",
                  "| --- | --- | --- |"]
        lines += [f"| {n} | {v} | {lic.replace('|', '/')} |" for n, v, lic in rows]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    text = render(python_packages(), web_packages())
    if "--check" in argv:
        try:
            with open(OUT, encoding="utf-8") as handle:
                current = handle.read()
        except FileNotFoundError:
            current = ""
        if current != text:
            print("THIRD_PARTY_NOTICES.md is out of date: run scripts/third_party_notices.py")
            return 1
        print("THIRD_PARTY_NOTICES.md is up to date.")
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
