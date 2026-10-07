"""Engine documentation the router can deliver when a request is about the brain itself.

These ship with the engine (`brainkit/system/*.md`) rather than with any vault, because how
the brain works is the same for every brain. They are delivered in their own packet section
and never mixed with governed knowledge.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from . import frontmatter as fm
from . import util

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system")


@dataclass(frozen=True)
class SystemDoc:
    id: str
    title: str
    keywords: str
    body: str

    @property
    def search_text(self) -> str:
        return f"{self.title} {self.keywords} {self.body}"

    @property
    def tokens(self) -> int:
        return util.tokens(self.body)

    @property
    def body_hash(self) -> str:
        return util.sha256(self.body)


@lru_cache(maxsize=1)
def load() -> tuple:
    docs = []
    if not os.path.isdir(FOLDER):
        return ()
    for name in sorted(os.listdir(FOLDER)):
        if not name.endswith(".md"):
            continue
        meta, body, _errors = fm.parse(util.read_text(os.path.join(FOLDER, name)))
        docs.append(SystemDoc(id=str(meta.get("id") or name[:-3]),
                              title=str(meta.get("title") or name[:-3]),
                              keywords=str(meta.get("keywords") or ""),
                              body=body.strip()))
    return tuple(docs)
