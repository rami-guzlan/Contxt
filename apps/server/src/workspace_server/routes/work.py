"""Work as one place: what in it needs a look, for its overview. Each part has its own routes
(compose, workspace, skills, agents, workflows, library, outputs)."""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter

from ..deps import WS, Who

router = APIRouter(prefix="/api/work")

KEEP = 60.0  # seconds a look is kept: reading every skill's history is not free
_kept: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


@router.get("/attention")
def attention(who: Who, ws: WS, fresh: bool = False) -> dict[str, Any]:
    """Skills whose loads changed after their last edit, and agents whose pointers broke."""
    key = f"{ws.rt.workspace_id}:{who.actor_id}"
    with _lock:
        kept = _kept.get(key)
    if kept and not fresh and time.monotonic() - kept[0] < KEEP:
        return kept[1]
    found = ws.work_attention(who)
    with _lock:
        _kept[key] = (time.monotonic(), found)
    return found
