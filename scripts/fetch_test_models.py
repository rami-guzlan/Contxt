#!/usr/bin/env python3
"""Fetch the local models the model tests use into one folder, laid out like a Brain's
vault/.brain/models: the embedding model that matches by meaning (bge-small-en-v1.5) and the
speech model (faster-whisper small.en).

    uv run python scripts/fetch_test_models.py .test-models
    BRAIN_TEST_MODELS=.test-models uv run pytest packages/brain/tests/test_semantic.py \\
        apps/server/tests/test_captures.py

Models already in the folder are kept, so a cached folder costs nothing. Exit code 1 when a
model could not be fetched.
"""

from __future__ import annotations

import os
import sys
import tempfile

from brainkit.index import Embedder
from workspace_server.speech import Speech


def main(argv: list[str]) -> int:
    folder = os.path.abspath(argv[1] if len(argv) > 1 else ".test-models")
    os.makedirs(folder, exist_ok=True)
    embedder = Embedder(tempfile.mkdtemp())
    embedder.model_dir = folder  # straight into the folder, not a runtime folder's models/
    if not embedder.present():
        print(f"Downloading {embedder.model_name} into {folder} ...")
        embedder.download()
    speech = Speech(folder)
    if not speech.present():
        print(f"Downloading the speech model {speech.model} into {folder} ...")
        speech.download()
    checks = ((embedder.model_name, embedder.present()), (speech.model, speech.ready()))
    missing = [name for name, ready in checks if not ready]
    if missing:
        print("Could not fetch: " + ", ".join(missing), file=sys.stderr)
        return 1
    print(f"Ready: {embedder.model_name} and {speech.model} in {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
