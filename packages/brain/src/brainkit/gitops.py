"""Record governed changes in git: commit exactly the paths a change touched, nothing else.

`git commit --only` semantics (`git commit -- <paths>`) mean a staged but unrelated change in
the working tree is never swept into a brain commit. Pushing is never automatic.

Commits carry the identity git is configured with (git config or GIT_AUTHOR_* variables).
Where git has none, as in a fresh container or on a CI runner, they are by FALLBACK_IDENTITY
rather than failing.

Reading history (`locate`, `file_log`, `read_objects`) never changes anything: it is how an
entry's earlier versions are found (history.py).
"""
from __future__ import annotations

import os
import subprocess

FALLBACK_IDENTITY = ("AI Brain", "brain@localhost")
# Git for Windows refuses paths over 260 characters unless told otherwise; a Brain in a deep
# folder (a OneDrive path, a long home) would then fail every commit.
GIT = ("git", "-c", "core.longpaths=true") if os.name == "nt" else ("git",)
# Where governed changes live in a vault: what must reach git for the history and undo to hold.
GOVERNED = ("knowledge", "inbox", "references", "skills", "agents", "assets", "journal",
            "goals", "state")


def _env() -> dict:
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")


def _flags() -> dict:
    return ({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            if os.name == "nt" else {})


def _run(root, *args, timeout=20):
    kwargs = dict(cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                  timeout=timeout, stdin=subprocess.DEVNULL, env=_env(), **_flags())
    try:
        return subprocess.run([*GIT, *args], **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None


def locate(folder) -> tuple[str, str] | None:
    """(the repository's top folder, `folder`'s path inside it with a trailing slash, or "")
    when `folder` is inside a git work tree, else None."""
    proc = _run(folder, "rev-parse", "--show-toplevel", "--show-prefix")
    if proc is None or proc.returncode != 0:
        return None
    lines = proc.stdout.splitlines()
    if not lines or not lines[0].strip():
        return None
    return os.path.normpath(lines[0].strip()), (lines[1].strip() if len(lines) > 1 else "")


def file_log(top, path, limit=50) -> list[dict]:
    """The commits that changed one file, newest first, following it through renames:
    [{"commit", "at", "author", "subject", "path", "status"}], `path` being where the file
    was in that commit (relative to `top`). A commit that deleted it has status "D"."""
    proc = _run(top, "log", "--follow", f"--max-count={int(limit)}", "--name-status",
                "--format=%x1e%H%x1f%aI%x1f%an%x1f%s", "--", path, timeout=30)
    if proc is None or proc.returncode != 0:
        return []
    rows = []
    for chunk in proc.stdout.split("\x1e"):
        lines = [line for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        head = lines[0].split("\x1f")
        if len(head) < 4:
            continue
        status, where = "M", path
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) >= 2:
                status, where = parts[0][:1], parts[-1]
        rows.append({"commit": head[0], "at": head[1], "author": head[2], "subject": head[3],
                     "path": where, "status": status})
    return rows


def read_objects(top, specs) -> dict[str, bytes | None]:
    """{spec: bytes} for `<commit>:<path>` specs, read in one `git cat-file --batch`; a spec
    git cannot find maps to None."""
    specs = [str(s) for s in specs if s and "\n" not in str(s)]
    if not specs:
        return {}
    try:
        proc = subprocess.run(["git", "cat-file", "--batch"], cwd=top, capture_output=True,
                              input=("\n".join(specs) + "\n").encode("utf-8"), timeout=30,
                              env=_env(), **_flags())
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    out: dict[str, bytes | None] = {}
    data, pos = proc.stdout, 0
    for spec in specs:
        end = data.find(b"\n", pos)
        if end < 0:
            break
        header = data[pos:end].decode("utf-8", "replace").split()
        pos = end + 1
        if len(header) == 3 and header[1] in ("blob", "tree", "commit", "tag") \
                and header[2].isdigit():
            size = int(header[2])
            out[spec] = data[pos:pos + size]
            pos += size + 1  # the object, then a newline
        else:
            out[spec] = None
    return out


def is_repo(root) -> bool:
    proc = _run(root, "rev-parse", "--is-inside-work-tree")
    return bool(proc and proc.returncode == 0 and proc.stdout.strip() == "true")


def _identity(root) -> list[str]:
    """`-c` options for the fallback identity, only when git cannot name an author itself."""
    for ident in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        proc = _run(root, "var", ident)
        if proc is None or proc.returncode != 0:
            name, email = FALLBACK_IDENTITY
            return ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    return []


def owns_repo(root) -> bool:
    """True when `root` is the top folder of its git repository, not a folder inside another
    (compared as real paths, so a symlinked or short-named folder still counts as itself)."""
    found = locate(root)

    def same(path):
        return os.path.normcase(os.path.realpath(path))

    return bool(found) and same(found[0]) == same(root)


def locate_own(folder, root) -> tuple[str, str] | None:
    """`locate(folder)`, but only inside `root`'s own repository (the one the Brain commits
    into): a Brain that merely sits inside another repository reads no history from it."""
    found = locate(folder)
    if not found or not owns_repo(root):
        return None
    same = os.path.normcase(os.path.realpath(found[0])) == os.path.normcase(
        os.path.realpath(root))
    return found if same else None


def uncommitted(root, folders) -> list[str]:
    """Paths under `folders` (relative to `root`) whose changes are not committed: what a
    failed commit left live but unsaved. Empty when `root` is not the Brain's own repository."""
    if not folders or not is_repo(root) or not owns_repo(root):
        return []
    proc = _run(root, "status", "--porcelain", "--untracked-files=all", "--", *folders)
    if proc is None or proc.returncode != 0:
        return []
    out = []
    for line in proc.stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            out.append(path.strip('"'))
    return out


def commit(root, paths, message) -> dict:
    """Stage and commit `paths` (absolute or root-relative). Returns what happened.

    Only into the Brain's own repository: when `root` merely sits inside another one (say a
    Brain folder in an application checkout that never got its own `git init`), nothing is
    committed, so Brain content never lands in a repository that was not made for it."""
    if not is_repo(root):
        return {"committed": False, "reason": "not a git repository"}
    if not owns_repo(root):
        return {"committed": False,
                "reason": "the Brain folder is inside another git repository, not its own"}
    rels = []
    for path in paths:
        if not path:
            continue
        full = path if os.path.isabs(path) else os.path.join(root, path)
        rels.append(os.path.relpath(full, root).replace("\\", "/"))
    rels = sorted(set(rels))
    if rels:
        # A path git cannot stage would fail the whole commit: one that is gone and was never
        # committed (an undo removing a file git never saw), or one git ignores.
        listed = _run(root, "ls-files", "--", *rels)
        known = set(listed.stdout.splitlines()) if listed and listed.returncode == 0 else set()
        rels = [r for r in rels if r in known or os.path.exists(os.path.join(root, r))]
        ignored = _run(root, "check-ignore", "--", *rels) if rels else None
        skip = set(ignored.stdout.splitlines()) if ignored and ignored.returncode == 0 else set()
        rels = [r for r in rels if r not in skip or r in known]
    if not rels:
        return {"committed": False, "reason": "nothing to commit"}
    add = _run(root, "add", "--all", "--", *rels)
    if add is None or add.returncode != 0:
        return {"committed": False, "failed": True,
                "reason": (add.stderr.strip() if add else "git unavailable")}
    staged = _run(root, "diff", "--cached", "--name-only", "--", *rels)
    if staged is None or not staged.stdout.strip():
        return {"committed": False, "reason": "no changes"}
    proc = _run(root, *_identity(root), "commit", "--no-verify", "-m", message, "--", *rels)
    if proc is None or proc.returncode != 0:
        return {"committed": False, "failed": True,
                "reason": (proc.stderr.strip() or proc.stdout.strip()) if proc else "git failed"}
    head = _run(root, "rev-parse", "--short", "HEAD")
    return {"committed": True, "commit": head.stdout.strip() if head else None,
            "paths": rels}
