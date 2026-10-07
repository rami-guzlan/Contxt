"""Stable, typed, time-ordered identifiers: `task_01J9Z3...` (a prefix and a ULID).

The prefix says what a record is when an id appears in a log, a URL or a model's output. The
ULID part sorts by creation time, so ids double as a stable creation order: ids made in the
same millisecond (every record one transaction writes shares its moment) count up from the
first, so they sort in the order they were made.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import UTC, datetime

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
_PREFIX = re.compile(r"^[a-z][a-z0-9]{0,11}$")
_ID = re.compile(r"^([a-z][a-z0-9]{0,11})_([0-9A-HJKMNP-TV-Z]{26})$")
_RANDOM = 2**80
_last = {"millis": -1, "random": 0}
_lock = threading.Lock()


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, index = divmod(value, 32)
        chars.append(_ALPHABET[index])
    return "".join(reversed(chars))


def new_id(prefix: str, at: datetime | None = None) -> str:
    """A new id for a record of kind `prefix`, ordered by `at` (default: now)."""
    if not _PREFIX.match(prefix):
        raise ValueError(f"invalid id prefix: {prefix!r}")
    moment = at or datetime.now(UTC)
    millis = int(moment.timestamp() * 1000)
    with _lock:
        if millis == _last["millis"] and _last["random"] + 1 < _RANDOM:
            randomness = _last["random"] + 1
        else:
            # A fresh start in each millisecond, low enough to leave room to count up.
            randomness = int.from_bytes(os.urandom(10), "big") >> 1
        _last["millis"], _last["random"] = millis, randomness
    return f"{prefix}_{_encode(millis, 10)}{_encode(randomness, 16)}"


def is_id(value: object, prefix: str | None = None) -> bool:
    """True when `value` is a well-formed id (of kind `prefix`, when given)."""
    match = _ID.match(value) if isinstance(value, str) else None
    if match is None:
        return False
    return prefix is None or match.group(1) == prefix


def prefix_of(value: str) -> str:
    match = _ID.match(value)
    if not match:
        raise ValueError(f"not an id: {value!r}")
    return match.group(1)
