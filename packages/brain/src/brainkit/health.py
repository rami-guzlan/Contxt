"""`brain check` and the `brain_health` tool: is this vault well formed and current?

Problems are things that make retrieval wrong (a note nothing can reach, a skill loading a
topic that does not exist, a scope nobody declared). Warnings are things a human should look
at (reviews past due, proposals waiting, a kernel over budget, a stale startup file).
"""
from __future__ import annotations


from . import kernel as kernel_mod
from . import util


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


INDEX_TOKENS = 250    # the startup index of must-hold domains should stay this small


def must_hold_warnings(config, index, chain) -> list[str]:
    """What the owner should look at about must-holds: an index past its size, more critical
    must-holds than the startup context shows, and a must-hold with nothing to bring it into
    play but its own area."""
    out = []
    index_tokens = util.tokens("\n".join(kernel_mod.must_hold_index(config, index, chain)))
    if index_tokens > INDEX_TOKENS:
        out.append(f"the must-hold index is {index_tokens} tokens, over {INDEX_TOKENS}: "
                   "fewer must-holds, or shorter titles")
    musts = kernel_mod.must_hold_notes(index, chain)
    critical = [n.id for n in musts if n.critical]
    shown = set(kernel_mod.critical_ids(musts))
    if len(critical) > len(shown):
        out.append("more must-holds are critical than the startup context shows in full: "
                   + ", ".join(c for c in critical if c not in shown))
    for note in musts:
        if not note.triggers and note.applies_to == [note.area]:
            out.append(f"{note.id}: a must-hold with no triggers comes up only when a request "
                       f"reaches its area ({note.area}); add a few words that bring it in")
    return out


def report(brain, *, strict=False):
    st = brain.state()
    config, index, snapshot = st.config, st.index, st.snapshot
    problems, warnings, facts = [], [], []

    for message in config.errors:
        problems.append(f"config: {message}")
    for path, message in snapshot.problems:
        problems.append(f"{path}: {message}")

    declared = set(st.scopes.declared)
    for note in snapshot.notes.values():
        if note.scope not in declared:
            problems.append(f"{note.path}: scope {note.scope} is not declared in brain.json")
        if note.area not in config.areas:
            problems.append(f"{note.path}: area {note.area} is not declared in brain.json")
        if note.partition and note.partition not in st.scopes.partitions:
            problems.append(f"{note.path}: partition {note.partition} is not declared")
        if note.status not in ("approved", "archived"):
            warnings.append(f"{note.id}: unusual status {note.status!r}")
    topics_with_notes = {n.route_key for n in index.notes.values()
                         if not config.is_focus(n) and n.kind != "identity"}
    project_topics = {n.route_key for n in index.notes.values() if config.is_focus(n)}
    unrouted = sorted(topics_with_notes - set(config.topics) - project_topics)
    if unrouted:
        warnings.append("topics with notes but no line in topics.md: " + ", ".join(unrouted))
    live_topics = {n.route_key for n in index.notes.values()}
    for skill in index.skills.values():
        for topic in skill.load_topics:
            if topic not in live_topics:
                problems.append(f"skill {skill.name}: loads {topic}, which has no live notes")
        for ref in skill.load_references:
            if ref not in index.references:
                problems.append(f"skill {skill.name}: loads {ref}, which does not exist")
        if skill.scope not in declared:
            problems.append(f"skill {skill.name}: scope {skill.scope} is not declared")
        for dependency in skill.depends_on:
            if dependency not in index.skills:
                warnings.append(f"skill {skill.name}: depends on unknown skill {dependency}")
    for focus in index.focuses.values():
        for pin in focus.pinned_notes:
            if index.note(pin) is None:
                problems.append(f"Focus {focus.id}: pinned note {pin} is not live")
        for pin in focus.pinned_skills:
            if pin not in index.skills:
                problems.append(f"Focus {focus.id}: pinned skill {pin} does not exist")
    for old, new in config.aliases.items():
        if new not in snapshot.notes:
            problems.append(f"aliases.json: {old} points at missing note {new}")
    referenced = set()
    for note in index.notes.values():
        for ref in note.references:
            referenced.add(ref)
            if ref not in index.references:
                warnings.append(f"{note.id}: points at missing reference {ref}")
    unpointed = sorted(r for r in set(index.references) - referenced
                       - {r for s in index.skills.values() for r in s.load_references}
                       if not r.lower().endswith("readme.md"))
    if unpointed:
        warnings.append("references nothing points at: " + ", ".join(unpointed))

    flagged = [f"{n.id} {flag}" for n in sorted(index.notes.values(), key=lambda n: n.id)
               for flag in util.text_flags(n.body)]
    if flagged:
        warnings.append(f"{len(flagged)} note(s) carry text that does not belong in them: "
                        + "; ".join(flagged[:6]) + (" ..." if len(flagged) > 6 else ""))
    from . import review
    twins = review.near_duplicates(st)
    if twins:
        warnings.append("notes that may say the same thing (archive one, or merge them): "
                        + ", ".join(f"{a} and {b}" for a, b, _s in twins[:6])
                        + (" ..." if len(twins) > 6 else ""))

    today = util.today_date()
    due = sorted(n.id for n in index.notes.values()
                 if n.stale_reason(today, config.review_days_for(n)))
    if due:
        warnings.append(f"{len(due)} stale note(s) to verify: " + ", ".join(due[:12])
                        + (" ..." if len(due) > 12 else ""))
    proposals = list(snapshot.proposals.values())
    if proposals:
        oldest = min((p.created for p in proposals), default="")
        warnings.append(f"{len(proposals)} proposal(s) waiting in the inbox (oldest {oldest[:10]})")

    owner_chain = st.scopes.chain(config.owner) or [st.scopes.root()]
    kernel_text, fingerprint = kernel_mod.render(config, index, st.scopes, owner_chain)
    kernel_tokens = util.tokens(kernel_text)
    budget = int(config.budgets.get("kernel_tokens") or 6000)
    facts.append(f"kernel for {owner_chain[-1]}: {kernel_tokens} tokens (budget {budget}), "
                 f"fingerprint {fingerprint}")
    if kernel_tokens > budget:
        problems.append(f"kernel is {kernel_tokens} tokens, over the {budget} budget")
    warnings += must_hold_warnings(config, index, owner_chain)
    on_disk = kernel_mod.file_fingerprint(brain.repo_root)
    if on_disk != fingerprint:
        warnings.append(f"CLAUDE.md is stale (has {on_disk}, current {fingerprint}); "
                        f"run `{util.cli_name(config)} kernel`")
    facts.append(f"{len(index.notes)} live notes, {len(index.archived)} archived, "
                 f"{len(index.skills)} skills, {len(index.references)} references, "
                 f"{len(index.focuses)} Focus items, {len(proposals)} pending proposals")
    tokenizer = util.tokenizer_status()
    facts.append("tokens: " + ("exact (tiktoken)" if tokenizer["exact"] else "estimated"))
    if brain.embedder is None:
        facts.append("embeddings: off")
    else:
        status = brain.embedder.status()
        facts.append("embeddings: " + ("available" if status["available"] else
                                       f"unavailable ({status['reason']})"))
    if getattr(brain, "reranker", None) is None:
        facts.append("reranker: off")
    else:
        status = brain.reranker.status()
        weight = st.router.policy.rerank_weight
        if not status["downloaded"]:
            facts.append("reranker: not downloaded (optional; brain models --download)")
        else:
            facts.append(f"reranker: {status['model']} downloaded, "
                         + (f"on (weight {weight})" if weight > 0 else
                            "off (set policy.rerank_weight in routing.json to use it)"))
    try:
        sessions = brain.ledger.recent_sessions(5)
        facts.append(f"sessions: {len(sessions)} recent")
    except Exception as exc:
        problems.append(f"session ledger unreadable: {exc}")
    from . import runtime
    stale, why = runtime.stale()
    if stale:
        warnings.append(why)
    facts.append(f"engine {runtime.VERSION} ({runtime.STARTED_WITH}) from {runtime.ENGINE_DIR}")
    unsaved = brain.unsaved()
    if unsaved:
        warnings.append(f"{len(unsaved)} governed file(s) are live but not saved to git (a commit "
                        "failed): " + ", ".join(unsaved[:6]) + (" ..." if len(unsaved) > 6 else "")
                        + ". The next change retries; commit them by hand if it keeps failing.")

    lines = [f"# Brain health: {config.name}", ""]
    lines += [f"- {fact}" for fact in facts]
    lines += ["", f"## Problems ({len(problems)})", ""] + ([f"- {p}" for p in problems]
                                                          or ["- none"])
    lines += ["", f"## Warnings ({len(warnings)})", ""] + ([f"- {w}" for w in warnings]
                                                          or ["- none"])
    ok = not problems and (not strict or not warnings)
    return _result("\n".join(lines) + "\n",
                   {"ok": ok, "problems": problems, "warnings": warnings, "facts": facts,
                    "kernel_fingerprint": fingerprint, "kernel_tokens": kernel_tokens},
                   is_error=not ok)


def status_line(brain) -> str:
    st = brain.state()
    return (f"{st.config.name}: {len(st.index.notes)} notes, {len(st.index.skills)} skills, "
            f"{len(st.index.focuses)} Focus items, {len(st.snapshot.proposals)} pending, "
            f"vault at {brain.vault.root}")
