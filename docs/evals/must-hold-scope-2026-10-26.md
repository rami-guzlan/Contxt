# Fewer wrong must-holds: scopes and close calls (Oct 26, 2026)

v4 backend plan, section 16.3, measured with the answer-recall eval
(`answer-recall-2026-10-26.md`): Haiku, words only, zero-config generated Brains.

## What changed

- **Close call → pointer.** Some must-holds are in play only because the task touches their
  domain. Such a rule goes as a one-line pointer under "May apply", naming the rule and what
  it is for and never its text, in either of two cases:
  - the request's words fit it at most 0.2 of the best note the packet holds
    (`must_hold_close`);
  - it has a kept scope that shares no word with the request.

  The model opens it if the task is about it.
  - Never demoted: a critical rule, a rule for every task, a rule the request names by a
    trigger, and a rule its meaning puts in play.
- **Scopes.** Haiku drafts "applies when" and "not when" from the rule's own text
  (`brainkit/rule_scope.py`, `scripts/scope_drafts.py`).
  - Each draft is proposed as a change to the rule and waits in Catch up. Keeping it needs the
    owner's reason, as any baseline change does.
  - Once kept, the rule is left out of a request that fits "not when" better than "applies
    when", by two words or more.
  - A rule for every task is never scoped out.
  - The fields are `must_applies_when` and `must_not_when`. They are apart from model
    enrichment, so only what the owner kept counts.

## Results

In the eval, the drafted scopes were applied as if kept: tuning drafts on tuning Brains,
validation drafts on validation Brains. That was 8 and 6 drafts, $0.05 in all.

| | Wrong must-holds reaching the answer | Answers with one | Answer recall | Fetches |
|---|---|---|---|---|
| Tuning, before | 68/271 | 49/152 (32.2%) | 121/159 | 1.11 |
| Tuning, after | 37/271 | 33/152 (21.7%) | 117/159 | 1.18 |
| Validation, before | 37/201 | 31/114 (27.2%) | 95/123 | 1.30 |
| Validation, after | 22/201 | 20/114 (17.5%) | 94/123 | 1.22 |

Without a model, counting must-holds in the packets:

| | Right ones sent whole | Right ones as pointers | Wrong ones sent whole |
|---|---|---|---|
| Tuning | 25 → 23 | 0 → 2 | 60 → 18 |
| Validation | 13 → 12 | 0 → 1 | 31 → 14 |

No right must-hold was left out; three became pointers. The goal in 16.4 is wrong must-holds
under 15% of answers. Validation is at 17.5%.

## Open

- Drafting is a script today. The heartbeat or a scheduled run should draft scopes for new
  must-holds by itself.
