"""One word, one meaning (goals plan 9, G0): what a model reads says "run" for the app's runs,
so "task" means only the new kind (a piece of work with one owner). Tool names, field names
and records keep theirs (`claim_task`, `task_id`)."""

import json
import os
import re

from brainkit import mcp_server
from workspace_core.services import distill, docs, skills
from workspace_server import anchoring, templates
from workspace_server.mcp import render, tools

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# "task" or "tasks" as a word: not inside a name (claim_task, task_id, get_task_context).
WORD = re.compile(r"(?<![\w`/])[Tt]asks?(?![\w`])")


def model_facing() -> dict[str, str]:
    """Every text a model reads that names the app's runs, by where it comes from."""
    out = {f"tool {t.name}": json.dumps(t.listing()) for t in tools.TOOLS.values()}
    out |= {f"brain tool {t['name']}": json.dumps(t) for t in mcp_server.AGENT_TOOLS}
    out["brain instructions"] = mcp_server.INSTRUCTIONS
    folder = os.path.join(ROOT, "config", "templates", "workers")
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            out[f"template {name}"] = handle.read()
    out["fallback worker"] = templates.FALLBACK_WORKER
    out["fallback run"] = templates.FALLBACK_RUN
    for name in (
        "RUN_INSTRUCTIONS",
        "RUN_MANY_INSTRUCTIONS",
        "PICK_INSTRUCTIONS",
        "IMPROVE_INSTRUCTIONS",
        "NEW_INSTRUCTIONS",
    ):
        out[f"skills {name}"] = getattr(skills, name)
    out["skills contracts"] = json.dumps([skills.RUN_CONTRACT, skills.DRAFT_CONTRACT])
    out["docs push back"] = docs.PUSH_BACK
    out["docs continue"] = docs.CONTINUE
    out["anchoring finish check"] = anchoring.FINISH_CHECK
    out["packet"] = render.packet(
        {
            "task": {"id": "t1", "title": "Digest the call", "revision": 1},
            "run": {"id": "r1", "attempt": 1, "lease_expires_at": "later"},
        }
    )
    out["due"] = render.due(
        [{"id": "t1", "title": "Digest", "next_due_at": None, "review_policy": "human"}],
        [{"id": "r1", "task_id": "t1", "lease_expires_at": "later"}],
    )
    return out


# Where "task" is the new kind itself (G2: the Tasks sheet and hand_off), as the rule intends.
NEW_KIND = {
    "brain instructions",
    "brain tool gnomon_get_context",
    "brain tool sheets_get",
    "brain tool sheets_propose_update",
    "brain tool todos_update",
    "tool sheets_get",
    "tool sheets_propose_update",
    "tool todos_update",
}


def test_model_facing_text_says_run_for_runs():
    texts = model_facing()
    found = {where: WORD.findall(text) for where, text in texts.items() if where not in NEW_KIND}
    assert {where: words for where, words in found.items() if words} == {}
    # And where it says task, it means a task from the Tasks sheet.
    for where in NEW_KIND:
        if WORD.search(texts[where]):
            assert any(w in texts[where] for w in ("todos_update", "T-41", "State")), where


def test_distillation_still_names_its_kinds_from_the_one_vocabulary():
    assert "its kind (fact, rule, preference, decision or procedure)" in distill.INSTRUCTIONS
