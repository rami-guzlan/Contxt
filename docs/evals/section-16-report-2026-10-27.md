# Section 16, final report: filling gaps, measured by what reached the AI (Oct 27, 2026)

v4 backend plan, section 16. Every number comes from the answer-recall eval
(`answer-recall-2026-10-26.md`):
- Haiku answers each labeled request through the Brain's MCP server, words only, and code
  scores what reached it.
- Tuning was general only. Settings were chosen on the tuning Brains, each candidate was
  validated once on the held-out validation Brains, and no setting names a Brain, business
  or domain.
- The owner's IKN Brain was measured before and after, never tuned on. Only counts are
  recorded.

## What shipped and what didn't

| PR | What | Tuning | Validation | Decision |
|---|---|---|---|---|
| A (#98) | The answer-recall eval and baselines | | | merged |
| B | A coverage line in each packet | answer recall 121 → 123 | 95 → 94 | not merged |
| C | A second search route: titles and headings, one relation hop, the caller's rephrase, fused | 117 → 114 | not run | not merged |
| D (#99) | Must-hold scopes, and close calls as pointers | wrong must-holds 32.2% → 21.7% of answers | 27.2% → 17.5% | merged |

- **B**, branch `r1/coverage`.
  - Offline, its lines named a quarter of the needed items the packet missed. About one line
    in five pointed at a needed or useful note.
  - With Haiku reading the lines and choosing its fetches, held-out answer recall did not
    move. Section 16.7 says to drop a line that cries wolf, so it was dropped.
- **C**, branch `r1/search-routes`.
  - Offline, fusing a titles-and-headings route into the search found more of the missed
    needed items held out: 27 of 52 in the top three, against 20.
  - With Haiku choosing its own searches, tuning answer recall did not rise, so there was
    nothing to validate.
  - The generated Brains have no links between notes, so the graph route had nothing to walk.
- **D.** Haiku drafts scopes for $0.05 for all 14 rules. They wait in Catch up until the
  owner keeps them.

## The owner's IKN Brain, before and after

As configured, words only, 68 requests (63 with a needed item, none labeled for must-holds).

| | Before | After (A and D) |
|---|---|---|
| Answer recall | 71/88 (80.7%) | 77/88 (87.5%) |
| Packet recall | 64/88 (72.7%) | 66/88 (75.0%) |
| Complete | 49/63 | 53/63 |
| Fetches per answer | 1.06 | 1.25 |
| Tokens per answer | about 104,000 | about 117,000 |
| Cost of the run | $0.38 | $0.41 |

No scope was drafted or kept on the IKN Brain, so only the close-call pointers changed there.
The rise in answer recall came with more fetches. One run each way on Haiku can move by a few
items, so it is a direction, not a settled gain.

## Against the goals in 16.4

| Goal | Where it stands |
|---|---|
| Answer recall 95% or more | not met: 76% to 77% on generated Brains, 87.5% on the IKN Brain |
| 1.0 fetch or fewer per answer | not met: 1.1 to 1.3 |
| Wrong must-holds under 15% of answers | not met: 17.5% held out, down from 27.2% |
| No drop on the operating eval | not rerun after D: a step for the next run |

## What the measurements say about where to go next

- **The missed items are near misses of the request's own matching.**
  - 44 of the 61 missed needed items on the tuning Brains are in the request's top eight by
    its own words.
  - None of them is reachable by relations.
  - Pointing at near misses didn't make Haiku fetch them. Neither the coverage line nor a
    fused search did.
  - What's left is ranking, not pointing: putting more of the top eight into the packet
    within its budget, or ranking it better by meaning. Every run here was words only.
- **Words-only runs understate a Brain that has the meaning model.** The next rerun should
  use it on both sides.
- **Must-holds:** kept scopes do most of the work. They need drafting for new must-holds to
  happen on its own: the heartbeat or a scheduled run.

## Cost

About $6.50 of Haiku across every run in section 16, no single run past $1. That includes
one IKN run lost to a transcript parsing bug, now fixed.
