"""The knowledge agent's labeled set and its bars (brain-logic plan 17.9).

Each case seeds a copy of a demo Brain, gathers one action's candidates, asks a model through
the same code-run loop the app uses, and scores the answer:

- agreement: each labeled candidate got a verdict its label allows;
- valid answers: the answer read as the action's JSON, naming only its candidates and verdicts;
- no direct writes: the Brain's notes are byte for byte the same after the job;
- impact lines: each candidate note's impact (briefs that used it) matches a reference count.

Models: `oracle` (a stand-in that answers each case's label, to check the harness itself),
`local` (the shared model service's agent model), `claude` (Claude Code, `claude -p`). The
comparison of 4B, 9B and Claude Code per machine setup runs on the owner's machines.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from typing import Callable

from . import agent, agent_tools
from . import safeguards_eval as se

VERDICTS = {
    "tidy-repeats": ("merge", "narrow", "different"),
    "check-drift": ("revise", "retire", "dispute", "fine"),
    "check-alignment": ("question", "triggers", "retire", "keep", "fine"),
    "freshen-up": ("ask", "revise", "retire", "lasting"),
    "tidy-projects": ("next-steps", "close", "ask"),
    "tidy-skills": ("triggers", "retire", "fine"),
    "fill-gaps": ("teach", "route", "ignore"),
    "verify-sources": ("confirmed", "challenge", "ask"),
}
SET = "agent-set.json"


def _notes_hash(vault: str) -> str:
    digest = hashlib.sha256()
    for folder, _dirs, names in sorted(os.walk(os.path.join(vault, "knowledge"))):
        for name in sorted(names):
            with open(os.path.join(folder, name), "rb") as handle:
                digest.update(handle.read())
    return digest.hexdigest()


def load(brains_dir: str) -> list[dict]:
    with open(os.path.join(brains_dir, SET), encoding="utf-8") as handle:
        return list(json.load(handle)["cases"])


def _label(case: dict, candidate: dict) -> list[str] | None:
    for phrase, allowed in (case.get("expect") or {}).items():
        if phrase in f"{candidate.get('title', '')} {candidate.get('text', '')}":
            return list(allowed)
    return None


def oracle(case: dict) -> Callable[[str, list[dict]], str]:
    """A stand-in that answers each candidate with its label's first verdict."""
    def answer(_prompt: str, candidates: list[dict]) -> str:
        findings = []
        for c in candidates:
            allowed = _label(case, c) or [VERDICTS[case["action"]][-1]]
            finding = {"ref": c["ref"], "verdict": allowed[0], "why": "From the label.",
                       "text": "Is this still true?"}
            if case["action"] == "verify-sources":
                finding["sources"] = ["https://example.org/source"]
            findings.append(finding)
        return json.dumps({"summary": "oracle", "findings": findings})
    return answer


def claude(_case: dict) -> Callable[[str, list[dict]], str]:
    def answer(prompt: str, _candidates: list[dict]) -> str:
        done = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True,
                              timeout=600, check=False)
        return done.stdout
    return answer


def local(_case: dict) -> Callable[[str, list[dict]], str]:
    from . import models_client
    status = models_client.status(refresh=True)
    client = models_client.Agent(status)

    def answer(prompt: str, _candidates: list[dict]) -> str:
        return str(client.generate(prompt).get("text") or "")
    return answer


MODELS = {"oracle": oracle, "claude": claude, "local": local}


def run_case(brains_dir: str, case: dict, model: str = "oracle") -> dict:
    from .api import Brain
    vault = se.copy_vault(os.path.join(brains_dir, case["brain"], "vault"))
    brain = Brain(vault, embeddings=False)
    try:
        owner = brain.state().config.owner
        for seed in case.get("seed") or []:
            made = brain.propose(area=seed["area"], topic=seed["topic"], text=seed["text"],
                                 note_kind=seed.get("kind", "rule"), principal=owner,
                                 extra=seed.get("extra"), force_pending=True)
            if not made.is_error:
                brain.approve(made.data["proposal_id"], actor=owner)
        gathered = agent.gather(brain, case["action"])
        candidates = gathered["candidates"]
        before = _notes_hash(vault)
        prompt = (agent.skill_text(brain, case["action"]) or "") + "\n\n" + "\n\n".join(
            f"## {c['ref']}\n\n{c['text']}" for c in candidates)
        asker = MODELS[model](case)
        steps = []

        def call_tool(name, args):
            found, problems = agent_tools.call(brain, name, args)
            steps.append(name)
            return found, problems

        from importlib import import_module
        loop = import_module("workspace_core.services.agent_loop") if _has_core() else None
        if loop is not None:
            job = loop.run(prompt, lambda text: asker(text, candidates), call_tool,
                           action=case["action"])
            findings = (job.findings or {}).get("findings")
            ending = job.ending
        else:
            data = _json(asker(prompt, candidates))
            findings = (data or {}).get("findings")
            ending = "findings" if findings is not None else "hand-up"
        refs = {c["ref"]: c for c in candidates}
        valid = isinstance(findings, list) and all(
            isinstance(f, dict) and f.get("ref") in refs
            and f.get("verdict") in VERDICTS[case["action"]] for f in findings)
        labeled = right = 0
        for finding in findings or []:
            candidate = refs.get(str(finding.get("ref")))
            allowed = _label(case, candidate) if candidate else None
            if allowed:
                labeled += 1
                right += finding.get("verdict") in allowed
        impacts_match = True
        for c in candidates:
            for note_id in c.get("ids") or []:
                if brain.state().index.note(note_id) is None:
                    continue
                found = agent_tools.impact(brain, note_id)["briefs"]
                reference = sum(1 for row in brain.ledger.requests(limit=500)
                                if note_id in ((row.get("data") or {}).get("note_ids") or []))
                impacts_match &= found == reference
        return {"id": case["id"], "action": case["action"], "candidates": len(candidates),
                "valid": valid, "labeled": labeled, "right": right,
                "no_writes": _notes_hash(vault) == before, "impacts_match": impacts_match,
                "ending": ending, "tools": steps}
    finally:
        brain.close()
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


def _has_core() -> bool:
    try:
        import workspace_core.services.agent_loop  # noqa: F401
    except ImportError:
        return False
    return True


def _json(text: str) -> dict | None:
    start, end = (text or "").find("{"), (text or "").rfind("}")
    try:
        return json.loads(text[start:end + 1]) if start != -1 and end > start else None
    except ValueError:
        return None


def score(rows: list[dict]) -> dict:
    """The bars: agreement, valid answers, no direct writes, impact lines, hand-ups."""
    labeled = sum(r["labeled"] for r in rows)
    return {"cases": len(rows),
            "agreement": round(sum(r["right"] for r in rows) / labeled, 3) if labeled else None,
            "valid": round(sum(r["valid"] for r in rows) / len(rows), 3) if rows else None,
            "no_writes": all(r["no_writes"] for r in rows),
            "impacts_match": all(r["impacts_match"] for r in rows),
            "hand_ups": sum(r["ending"] == "hand-up" for r in rows)}
