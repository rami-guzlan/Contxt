"""Prepare immutable blinded judge inputs. No provider calls or existing-file overwrite.

Input: a JSON list of cases for brainkit.answer_eval.prepare. Only reader-visible source
excerpts belong in evidence; never pass an entire note merely because its id was named.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "brain" / "src"))
from brainkit import answer_eval


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Input must be a list of cases")
    prepared = [answer_eval.prepare(row) for row in rows]
    payload = {
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "cases": [{"key": answer_eval.fingerprint(row), "payload": row} for row in prepared],
    }
    # Exclusive creation prevents a regrade from silently replacing the original evidence.
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
