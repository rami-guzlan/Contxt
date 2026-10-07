"""A content-addressed file store: bytes are kept once, under their SHA-256.

Working-context items and artifact versions refer to objects by key, so one upload linked to
several tasks is stored once, and an object never changes after it is written.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass

_KEY = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int

    @property
    def sha256(self) -> str:
        return self.key


class ObjectStore:
    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def path(self, key: str) -> str:
        if not _KEY.match(key):
            raise ValueError(f"not an object key: {key!r}")
        return os.path.join(self.root, key[:2], key[2:4], key)

    def put(self, data: bytes) -> StoredObject:
        key = hashlib.sha256(data).hexdigest()
        target = self.path(key)
        if not os.path.exists(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".tmp-")
            try:
                with os.fdopen(handle, "wb") as out:
                    out.write(data)
                os.replace(temp, target)
            except BaseException:
                if os.path.exists(temp):
                    os.remove(temp)
                raise
        return StoredObject(key=key, size=len(data))

    def read(self, key: str) -> bytes:
        with open(self.path(key), "rb") as handle:
            return handle.read()

    def exists(self, key: str) -> bool:
        return os.path.exists(self.path(key))

    def keys(self) -> Iterator[str]:
        for _base, _dirs, files in os.walk(self.root):
            for name in files:
                if _KEY.match(name):
                    yield name
