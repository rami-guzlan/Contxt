# Safeguards: the baseline (Phase 0)

Measured October 8, 2026 on the packaged demo Brains, before any safeguard was built, with
`scripts/safeguards_eval.py`. The cases live in `packages/brain/tests/evals/`. Every run
uses scratch copies and a throwaway session ledger.

## Must-hold recall

Eleven constraint notes across the four demo Brains (the peanut allergy, the monthly budget,
deploy windows, secrets, investor updates, introductions, approvals, sourced claims and
others). Each has eight requests from its domain that never name it ("Plan Tuesday dinner
for the four of us") and four decoys from other domains. For this baseline every target was
set to `load: on-demand`, so it competed on relevance alone, which is where any constraint
not in the startup context sits today.

| Matching | In-domain recall | Decoys including the constraint |
| --- | --- | --- |
| Words only | 47% (41 of 88) | 7% (3 of 44) |
| Words and meaning (bge-small) | 43% (38 of 88) | 9% (4 of 44) |

By constraint, words only:

| Brain | Note | Recall | Decoys |
| --- | --- | --- | --- |
| entrepreneur | `fundraising-investor-updates` | 75% | 0% |
| entrepreneur | `people-intros` | 75% | 0% |
| knowledge-company | `customers-out-of-scope` | 50% | 0% |
| knowledge-company | `marketing-approvals-morgan` | 50% | 25% |
| knowledge-company | `brand-claims-sourced` | 88% | 50% |
| personal | `family-ollie` (the peanut allergy) | 38% | 0% |
| personal | `money-budget` | 0% | 0% |
| personal | `travel-preferences` | 50% | 0% |
| personal | `health-sleep` | 25% | 0% |
| programmer | `work-deploys` | 38% | 0% |
| programmer | `practices-secrets` | 25% | 0% |

Relevance alone drops a constraint in more than half of the requests it governs, and
meaning-matching does not close the gap: the selection bar is relative to the best match, so
better evidence for everything else crowds the constraint out. The allergy survived "Plan
Tuesday dinner" today only because the demo stores it in the startup context. Only 5 of the
47 misses were even listed under "Also relevant".

## Disagreement detection

Sixty labeled pairs (24 contradictions, 8 that narrow, 8 that extend, 10 that agree, 10
unrelated), graded on contradictions.

| Detector | Recall | Precision |
| --- | --- | --- |
| Today's sentence heuristic (`review.contradiction`) | 38% | 82% |

It misses ordinals ("the 5th" against "the 1st"), dates that share fewer than three words
with their sentence ("November 12" against "December 3"), changed names ("leads go to Sam"
against "leads now go to Priya"), and every contradiction that is phrased differently ("Never
deploy on a Friday" against "Fridays are fine for deploys"). Its two false alarms are
agreements where one side uses a negation ("Do not target companies under 100 employees"
against "Companies with fewer than 100 employees are out of scope").

## Dated values

Five cases where two dated notes give a figure for the same subject (MRR, the committed seed
round, grocery spending, a version number, webinar registrations), with a request for the
current value.

| Matching | Newest delivered, no unmarked older value |
| --- | --- |
| Words only | 20% (1 of 5) |
| Words and meaning | 20% (1 of 5) |

Two cases left the newest value out; two delivered both values unmarked.

## What this means for the build

All three gaps are real at the measured size. Workstream A (must-holds) targets 100% recall
on these requests; B (the baseline check) targets 90% contradiction recall with the model
check and reports the cheaper checks on their own; C (dated values) targets 5 of 5.
