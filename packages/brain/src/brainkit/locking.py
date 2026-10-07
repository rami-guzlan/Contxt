"""One writer at a time: a lock that every process writing a vault shares.

Each Claude Desktop or Claude Code conversation starts its own Brain process, and the
workspace server holds another. Any of them may change the vault at any moment (a capture,
an upload, an approval) and commit the change to git. Their in-process locks cannot see
each other, so a change takes this lock: an operating-system lock on
`vault/.brain/write.lock`, held for the whole change (files, journal, undo point, kernel and
commit) and released when it ends. The lock belongs to the open file, so a process that
dies releases it with its handle: a crash never leaves the vault locked.

Reentrant within a process: a change made inside another (one decision in a batch) takes it
once. Readers never take it; they read whatever the files hold and rebuild their index when
the vault's fingerprint changes.
"""
from __future__ import annotations

import os
import threading
import time


class Busy(Exception):
    """Another process held the vault for longer than the wait allows."""


class WriteLock:
    def __init__(self, path: str, timeout: float = 60.0):
        self.path = path
        self.timeout = timeout
        self._thread = threading.RLock()
        self._depth = 0
        self._handle = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_exc):
        self.release()

    @property
    def held(self) -> bool:
        return self._depth > 0

    def acquire(self) -> None:
        self._thread.acquire()
        if self._depth == 0:
            try:
                self._handle = _lock(self.path, self.timeout)
            except BaseException:
                self._thread.release()
                raise
        self._depth += 1

    def release(self) -> None:
        if self._depth <= 0:
            raise RuntimeError("release of a write lock that is not held")
        self._depth -= 1
        try:
            if self._depth == 0 and self._handle is not None:
                handle, self._handle = self._handle, None
                _unlock(handle)
        finally:
            self._thread.release()


def _lock(path: str, timeout: float):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    handle = open(path, "a+b")
    deadline = time.monotonic() + max(0.0, timeout)
    delay = 0.01
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                raise Busy(f"The brain is busy with another change (waited {timeout:.0f} s "
                           f"for {path}); try again.") from None
            time.sleep(delay)
            delay = min(0.2, delay * 2)


def _unlock(handle) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
