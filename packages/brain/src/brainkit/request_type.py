"""What kind of request a packet answered, so briefs can be measured by type (brain-logic
plan 5.1).

Read from the request's words and the router's own signals, so it costs nothing:

    edit      a follow-up that changes what was just made
    code      software: code, tests, a repository, an error
    planning  a plan, a decision, a comparison or a recommendation
    writing   text someone will read: a post, an email, a page
    status    where something stands: a project's state, the portfolio
    lookup    a question answered from what the brain holds
    standard  anything else

The order matters: "plan dinners for next week" is planning before it is a status question,
and "write tests for the parser" is code before it is writing. Words that mean something else
outside software (a class, a module, a build, a test) are left out of the code words.
"""
from __future__ import annotations

import re

TYPES = ("lookup", "standard", "planning", "writing", "edit", "status", "code")

CODE_WORDS = frozenset({
    "code", "coding", "function", "functions", "bug", "bugs", "debug", "tests", "pytest",
    "repo", "repository", "script", "scripts", "exception", "traceback", "stacktrace",
    "python", "typescript", "javascript", "rust", "compile", "compiler", "refactor", "commit",
    "branch", "lint", "linter", "mypy", "npm", "endpoint", "endpoints", "regex", "sql",
    "codebase", "component", "components", "frontend", "backend", "api", "ui", "microservice",
    "dependency", "dependencies",
})
CODE_PHRASES = ("pull request", "unit test", "failing test", "stack trace", "merge conflict")
PLANNING_WORDS = frozenset({
    "plan", "planning", "strategy", "strategic", "decide", "decision", "decisions",
    "roadmap", "prioritize", "prioritise", "priorities", "options", "compare", "comparison",
    "recommend", "recommendation", "tradeoff", "tradeoffs", "evaluate", "assess",
})
PLANNING_PHRASES = ("should we", "should i", "pros and cons", "trade-off", "which is better",
                    "what would you do", "how should", "is it worth")
WRITING_VERBS = frozenset({"write", "draft", "rewrite", "compose", "edit", "proofread",
                           "summarize", "summarise", "outline", "caption"})
_WORD = re.compile(r"[a-z0-9]+")


def classify(route) -> str:
    """The request type of one routed request."""
    sig = route.signals
    text = " ".join(str(getattr(route, "request", "") or sig.request or "").lower().split())
    words = set(_WORD.findall(text))
    first = next(iter(_WORD.findall(text)), "")
    if sig.edit:
        return "edit"
    if words & CODE_WORDS or any(p in text for p in CODE_PHRASES):
        return "code"
    if words & PLANNING_WORDS or any(p in text for p in PLANNING_PHRASES):
        return "planning"
    if sig.composing or first in WRITING_VERBS:
        return "writing"
    if route.mode in ("focus-only", "focus-update", "portfolio") or sig.status_cue:
        return "status"
    if sig.question or (route.task_type == "knowledge" and route.scale == "micro"):
        return "lookup"
    return "standard"
