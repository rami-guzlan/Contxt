"""The Brain's MCP server for the map evaluation (scripts/map_eval.py).

    python scripts/map_eval_server.py --vault <dir> [--no-map]

With --no-map the packet goes out without the Brain map, for the "packet only" condition;
otherwise this is `python -m brainkit --vault <dir> mcp`. Evaluation only: the product has no
switch that turns the map off.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))

from brainkit import brainmap, cli  # noqa: E402


def main(argv: list[str]) -> int:
    if "--no-map" in argv:
        argv = [a for a in argv if a != "--no-map"]
        brainmap.short = lambda *_args, **_kw: ""  # type: ignore[assignment]
        brainmap.changes = lambda *_args, **_kw: ""  # type: ignore[assignment]
    return int(cli.main(argv + ["mcp"]) or 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
