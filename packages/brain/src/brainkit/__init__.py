"""brainkit: a governed, general-purpose AI brain engine.

    from brainkit import Brain
    brain = Brain("path/to/vault")
    packet = brain.context("Write a LinkedIn post about AI leadership")
    print(packet.text)          # what a model reads
    print(packet.data)          # what software reads

Every adapter (MCP server, CLI, local HTTP API, an embedding application) calls `Brain`.
Standard library only; `tiktoken` (exact token counts) and `fastembed` (semantic evidence)
are optional.
"""
from .api import Brain, Result
from .runtime import VERSION

__all__ = ["Brain", "Result", "VERSION"]
