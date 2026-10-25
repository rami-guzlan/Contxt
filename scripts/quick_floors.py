"""Measure and write the quick set's general floors (packages/brain/tests/test_general_eval.py).

    uv run python scripts/quick_floors.py --models <dir>

Runs every Brain of the tuning split the way the test does (the manifest's clock and model,
each calibration bank) and writes, for each bank's floor file, the aggregate over all of them
and the worst Brain: floors that name no Brain. It also records the fixtures' fingerprint in
baseline-inputs.json. Run it only when a change is meant to move the floors, and say why in
the commit; never to hide a failure.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "src"))
sys.path.insert(0, os.path.join(ROOT, "packages", "brain", "tests"))

import test_general_eval as gate  # noqa: E402

from brainkit import calibration, evalkit, util  # noqa: E402

KEEP = 3  # decimals


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--models", required=True)
    args = parser.parse_args(argv)
    path = gate.GENERAL / "baseline-inputs.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = gate._entries()
    fingerprint = gate._fixture_fingerprint(entries)
    at = dt.datetime.fromisoformat(manifest["as_of"])
    for row in manifest["baselines"]:
        if row["bank_file"] is None:
            bank = calibration.null_bank()
        else:
            text = (gate.GENERAL / row["bank_file"]).read_text(encoding="utf-8")
            bank = [line.strip() for line in text.splitlines()
                    if line.strip() and not line.startswith("#")]
        override = (mock.patch.object(calibration, "null_bank", return_value=bank)
                    if row["bank_file"] else contextlib.nullcontext())
        with override, mock.patch.object(util, "now", return_value=at), util.zone(dt.UTC):
            results = evalkit.run_suite(
                entries, models_dir=args.models,
                off_topic=evalkit.off_topic_cases(str(gate.GENERAL / "off_topic.json")),
                null_bank=True)
        found = gate.measured(results)
        floors = {"about": "General floors over every Brain of the tuning split, by meaning: "
                  "the aggregate and the worst Brain, the same for each (owner, October 25, "
                  "2026). Written by scripts/quick_floors.py; checked by "
                  "packages/brain/tests/test_general_eval.py.",
                  **{level: {m: round(v, KEEP) for m, v in sorted(values.items())}
                     for level, values in found.items()}}
        out = gate.GENERAL / row["minimums_file"]
        out.write_text(json.dumps(floors, indent=1) + "\n", encoding="utf-8", newline="\n")
        row["fixtures_sha256"] = fingerprint
        print(row["id"], json.dumps(floors["aggregate"]), flush=True)
    path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
