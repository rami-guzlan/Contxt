"""Behavior checks: does each request get the right KIND of packet?

The checks are content, so they live in the vault (`benchmark.json`). Each canonical case has
two calibration phrasings and one held-out acceptance phrasing; contrastive cases are single
prompts that sit next to a near miss ("Create a carousel cover" beside "Cover the routing
gap"). Every case states the expected task type, scale, procedure, Focus and skill, what MUST
be delivered, what must NOT, a token ceiling, and safety properties (no leaked personal
Focus, no skill for a lookup, no repeats in a session).

Whether the packet carries the RIGHT NOTES is measured by `evaluate.py` against `eval.json`.
Topics are not graded here: notes are chosen on their own relevance and a topic is only
where a note is filed, so an allowlist of topics would grade the filing, not the packet.
Precision here is over skills and references, which are still chosen as whole units.

Runs against a throwaway session ledger, so it never touches real conversation history.
"""
from __future__ import annotations

import json
import os
import tempfile
import time

from .sessions import Ledger

REQUIRED_KINDS = ("note_any", "topic_any", "skill_any", "reference_any",
                  "architecture_min", "focus_portfolio_min")


def expanded_cases(fixture):
    cases = []
    for canonical in fixture.get("canonical_cases") or []:
        variants = canonical.get("forbidden_by_variant") or {}
        for ordinal, prompt in enumerate(canonical["calibration"], 1):
            forbidden = (variants.get("calibration") or [[], []])[ordinal - 1]
            cases.append({"id": f"cal-{canonical['id']}-{ordinal}", "set": "calibration",
                          "canonical_id": canonical["id"], "prompt": prompt,
                          "setup_prompt": canonical.get("setup_prompt"),
                          "user": canonical.get("user"), "expect": canonical["expect"],
                          "variant_forbidden": forbidden})
        cases.append({"id": f"accept-{canonical['id']}", "set": "acceptance",
                      "canonical_id": canonical["id"], "prompt": canonical["acceptance"],
                      "setup_prompt": canonical.get("setup_prompt"),
                      "user": canonical.get("user"), "expect": canonical["expect"],
                      "variant_forbidden": variants.get("acceptance") or []})
    for row in fixture.get("contrastive_cases") or []:
        cases.append({"id": "critical-" + row["id"], "set": "critical",
                      "canonical_id": row["id"], "prompt": row["prompt"],
                      "setup_prompt": row.get("setup_prompt"), "user": row.get("user"),
                      "expect": row["expect"], "variant_forbidden": []})
    return cases


class Evidence:
    def __init__(self, data, standing_ids, route_keys):
        self.data = data
        self.standing_ids = set(standing_ids)
        self.route_keys = route_keys

    def notes(self):
        d = self.data
        return (set(d.get("note_ids") or []) | set(d.get("held_ids") or [])
                | set(d.get("standing_ids") or []) | self.standing_ids)

    def topics(self):
        d = self.data
        return set(d.get("topics") or []) | {self.route_keys[n] for n in d.get("note_ids") or []
                                             if n in self.route_keys}

    def skills(self):
        d = self.data
        out = set(d.get("candidates") or [])
        if d.get("skill_id"):
            out.add(d["skill_id"])
        return out

    def references(self):
        return set(self.data.get("reference_paths") or [])

    def hit(self, group) -> bool:
        kind = group.get("kind")
        values = set(group.get("values") or [])
        if kind == "note_any":
            return bool(self.notes() & values)
        if kind == "topic_any":
            return bool(self.topics() & values)
        if kind == "skill_any":
            return bool(self.skills() & values)
        if kind == "reference_any":
            return bool(self.references() & values)
        if kind == "architecture_min":
            return len(self.data.get("system_ids") or []) >= int(group.get("value") or 0)
        if kind == "focus_portfolio_min":
            return len(self.data.get("portfolio_ids") or []) >= int(group.get("value") or 0)
        raise ValueError(f"unknown expectation kind {kind!r}")


def _allowed(expect, axis, kind):
    allowed = set((expect.get("optional") or {}).get(axis) or [])
    for group in expect.get("required") or []:
        if group.get("kind") == kind:
            allowed |= set(group.get("values") or [])
    return allowed


def run(brain, fixture_path=None, verbose=False, only=None):
    fixture_path = fixture_path or os.path.join(brain.vault.root, "benchmark.json")
    with open(fixture_path, encoding="utf-8") as handle:
        fixture = json.load(handle)
    thresholds = fixture.get("thresholds") or {}
    owner = brain.state().config.owner
    system_skill = brain.state().router.system_skill
    tmp = tempfile.mkdtemp(prefix="brain-bench-")
    brain.close()
    brain._ledger = Ledger(os.path.join(tmp, "sessions.sqlite"), 30)
    st = brain.state()
    route_keys = {n.id: n.route_key for n in st.index.notes.values()}
    metrics = {name: {"hit": 0, "required": 0, "good": 0, "total": 0} for name in
               ("calibration", "acceptance", "critical")}
    failures, timings = [], []
    cases = expanded_cases(fixture)
    if only:
        cases = [c for c in cases if only in c["id"]]
    for ordinal, case in enumerate(cases):
        expect = case["expect"]
        user = case.get("user") or owner
        session = f"sess-bench-{ordinal:02d}"
        setup_ids = set()
        if case.get("setup_prompt"):
            setup = brain.context(case["setup_prompt"], principal=user, session_id=session)
            if setup.is_error:
                failures.append(f"{case['id']}: setup failed: {setup.text[:120]}")
                continue
            setup_ids = set(setup.data.get("note_ids") or [])
        started = time.perf_counter()
        result = brain.context(case["prompt"], principal=user, session_id=session,
                               explain=verbose)
        timings.append((time.perf_counter() - started) * 1000)
        if result.is_error:
            failures.append(f"{case['id']}: context failed: {result.text[:160]}")
            continue
        data = result.data
        chain = data.get("scope_chain") or []
        standing = {n.id for n in st.index.notes.values() if n.standing and n.scope in chain}
        evidence = Evidence(data, standing, route_keys)
        problems = []
        for label, actual, wanted in (
                ("task_type", data.get("task_type"), expect["task_type"]),
                ("task_scale", data.get("scale"), expect["task_scale"]),
                ("procedure_need", data.get("procedure"), expect["procedure_need"]),
                ("focus_mode", data.get("focus_mode"), expect["focus_mode"]),
                ("focus", data.get("focus_id"), expect["focus"]),
                ("skill", data.get("skill_id"), expect["skill"])):
            if actual != wanted:
                problems.append(f"{label} {actual!r}, expected {wanted!r}")
        bucket = metrics[case["set"]]
        for group in expect.get("required") or []:
            bucket["required"] += 1
            if evidence.hit(group):
                bucket["hit"] += 1
            else:
                problems.append(f"missed required {group}")
        forbidden = expect.get("forbidden") or {}
        forb = {"topic": set(forbidden.get("topics") or []),
                "skill": set(forbidden.get("skills") or []),
                "reference": set(forbidden.get("references") or [])}
        for item in case.get("variant_forbidden") or []:
            kind, value = item.split(":", 1)
            forb.setdefault(kind, set()).add(value)
        noise = ((set(forbidden.get("notes") or []) | forb.get("note", set()))
                 & set(data.get("note_ids") or []))
        if noise:
            problems.append(f"delivered off-task note(s) {sorted(noise)}")
        if evidence.topics() & forb["topic"]:
            problems.append(f"forbidden topic(s) {sorted(evidence.topics() & forb['topic'])}")
        for label, selected, allowed in (
                ("skill", evidence.skills(), _allowed(expect, "skills", "skill_any")),
                ("reference", evidence.references(),
                 _allowed(expect, "references", "reference_any"))):
            bucket["good"] += len(selected & allowed)
            bucket["total"] += len(selected)
            if selected - allowed:
                problems.append(f"unexpected {label}(s) {sorted(selected - allowed)}")
            if selected & forb.get(label, set()):
                problems.append(f"forbidden {label}(s) {sorted(selected & forb[label])}")
        note_ids = set(data.get("note_ids") or [])
        safety = set(expect.get("safety") or [])
        if "no_focus" in safety and data.get("focus_id"):
            problems.append("selected an unwanted Focus")
        if "no_skill" in safety and (data.get("skill_id") or data.get("candidates")):
            problems.append("selected unwanted skill context")
        if "no_reference" in safety and data.get("reference_paths"):
            problems.append("selected an unwanted reference")
        if "no_brain_notes" in safety and note_ids:
            problems.append("delivered brain notes for an external request")
        if "exact_focus_only" in safety and note_ids - {expect["focus"]}:
            problems.append(f"Focus-only packet also carried {sorted(note_ids)}")
        if "no_personal_focus" in safety:
            personal = {n.id for n in st.index.notes.values()
                        if st.config.is_focus(n) and n.scope.startswith("person:")}
            if note_ids & personal or data.get("focus_id") in personal:
                problems.append("personal Focus leaked outside its scope")
        if "architecture_lite" in safety and system_skill and data.get("skill_id") == system_skill:
            problems.append("operational question loaded the deep system procedure")
        if "deduplicated" in safety and note_ids & setup_ids:
            problems.append(f"repeated unchanged bodies {sorted(note_ids & setup_ids)}")
        if "focus_portfolio" in safety and (not data.get("portfolio_ids")
                                            or "## Focus portfolio" not in result.text):
            problems.append("Focus portfolio not delivered")
        visible = {n.id for n in st.index.notes.values() if n.scope in chain}
        if note_ids - visible:
            problems.append(f"delivered notes outside the caller's scope {sorted(note_ids - visible)}")
        if int(data.get("token_count") or 0) > int(expect["max_packet_tokens"]):
            problems.append(f"packet {data.get('token_count')} tokens exceeds "
                            f"{expect['max_packet_tokens']}")
        for problem in problems:
            failures.append(f"{case['id']}: {problem}")
        if verbose and problems:
            failures.append(f"    prompt: {case['prompt']}")
            failures.append("    trace: " + json.dumps(data.get("trace"), default=str)[:3000])
    scores = {}
    for name, m in metrics.items():
        recall = m["hit"] / m["required"] if m["required"] else 1.0
        precision = m["good"] / m["total"] if m["total"] else 1.0
        scores[name] = {"recall": round(recall, 3), "precision": round(precision, 3)}
        target = thresholds.get(name) or {}
        if recall + 1e-9 < float(target.get("required_recall", 0)):
            failures.append(f"{name}: recall {recall:.3f} below {target['required_recall']}")
        if precision + 1e-9 < float(target.get("precision", 0)):
            failures.append(f"{name}: precision {precision:.3f} below {target['precision']}")
    timings.sort()
    latency = {"p50_ms": round(timings[len(timings) // 2], 1) if timings else 0,
               "p95_ms": round(timings[int(len(timings) * 0.95) - 1], 1) if timings else 0,
               "max_ms": round(timings[-1], 1) if timings else 0}
    return {"cases": len(cases), "scores": scores, "failures": failures, "latency": latency,
            "semantic": bool(st.index.semantic_ready())}
