"""Every engine test runs without a local model service unless it starts a stand-in one: a
real service on a developer's machine never changes what retrieval returns in a test."""
import os

import pytest


@pytest.fixture(autouse=True)
def no_model_service(monkeypatch):
    if not os.environ.get("BRAIN_TEST_MODEL_SERVICE"):
        monkeypatch.setenv("BRAIN_MODEL_SERVICE", "off")
    yield
