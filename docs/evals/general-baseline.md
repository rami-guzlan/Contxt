# Retrieval across Brains: the stage 0 baseline, October 16, 2026

Stage 0 of the general-retrieval plan ([general-retrieval-plan.md](../dev/plans/general-retrieval-plan.md)):
retrieval measured the way anybody's Brain would be served, before any relevance change. Engine at
commit 048b439. Run with `scripts/general_eval.py` (and `scripts/third_party_eval.py` for
LongMemEval) on scratch copies.

**What was measured.**
- Ten generated Brains (packages/brain/tests/evals/general): a persona's 38 to 40 notes written by one
  model, 38 requests written by another from the persona alone (32 work, 6 off-topic), labels
  written by a third reading the notes. Split by Brain: four tuning, three validation, three sealed.
- The four demo Brains (already tuned on), zero-config and as configured.
- A private real Brain (the owner's work Brain, 130 notes, 68 labeled requests): numbers only.
- LongMemEval (MIT license): 60 questions, each its own Brain built from its chat history.
- Zero-config throughout unless said: no routing.json, no topics.md lines, no must-hold trigger words.
- Every Brain is also asked 100 off-topic requests (off_topic.json) and the 277-request calibration
  bank (null_requests.txt, kept apart from the scoring set).

**Measures.** Recall: needed notes the brief carried (whole or in short, or already held).
Reachable: those plus the ones listed, one `notes_get` away. Precision: delivered notes that were
needed or useful. Own off-topic: the Brain's own off-topic and uncovered requests that got nothing.
Off-topic set: the 100 general requests that got nothing. False nothing: requests that needed a
note and got nothing. Must-hold recall and decoys: the must-holds labeled in play, carried; those
not in play, carried anyway. Each with a 95% Wilson interval; the mean is over Brains, each counting
alike; the worst Brain beside it.

**Limits.** 38 requests a Brain: one request moves a Brain's rate by 3 to 8 points, and a split's
mean by more than its interval only when the change is broad. The notes, requests and labels were
written by models of one family; LongMemEval and the private Brain are the checks on that.

## By meaning, zero-config

| Brain | Split | Notes | Needed-note recall | Reachable | Precision | Off-topic set: nothing | Own off-topic: nothing | False nothing | Must-hold recall | Must-hold decoys | Avg tokens | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bistro | tuning | 38 | 64% (49% to 77%) | 79% (64% to 88%) | 51% (40% to 62%) | 91% (84% to 95%) | 67% (35% to 88%) | 0% (0% to 13%) | 100% (57% to 100%) | 13% (7% to 22%) | 432 | 77 |
| contractor | validation | 39 | 59% (43% to 72%) | 63% (48% to 76%) | 45% (35% to 57%) | 92% (85% to 96%) | 86% (49% to 97%) | 3% (1% to 17%) | 50% (15% to 85%) | 8% (4% to 17%) | 395 | 85 |
| dental | tuning | 40 | 79% (65% to 89%) | 84% (70% to 92%) | 55% (44% to 65%) | 93% (86% to 97%) | 60% (31% to 83%) | 4% (1% to 19%) | 80% (49% to 94%) | 55% (43% to 66%) | 545 | 74 |
| designer | sealed | 39 | 78% (62% to 88%) | 85% (71% to 93%) | 50% (40% to 59%) | 85% (77% to 91%) | 83% (44% to 97%) | 0% (0% to 12%) | 100% (70% to 100%) | 34% (24% to 46%) | 501 | 86 |
| foodbank | validation | 39 | 64% (50% to 76%) | 76% (63% to 86%) | 55% (45% to 64%) | 99% (95% to 100%) | 88% (53% to 98%) | 3% (1% to 17%) | 54% (29% to 77%) | 32% (22% to 44%) | 503 | 108 |
| lab | sealed | 39 | 71% (55% to 84%) | 80% (64% to 90%) | 51% (40% to 61%) | 91% (84% to 95%) | 75% (41% to 93%) | 0% (0% to 13%) | 67% (30% to 90%) | 17% (10% to 28%) | 476 | 80 |
| lawfirm | tuning | 38 | 83% (68% to 92%) | 94% (82% to 98%) | 54% (43% to 64%) | 95% (89% to 98%) | 78% (45% to 94%) | 0% (0% to 12%) | 88% (53% to 98%) | 24% (15% to 35%) | 473 | 91 |
| realtor | sealed | 39 | 67% (51% to 79%) | 79% (64% to 89%) | 38% (29% to 48%) | 93% (86% to 97%) | 62% (31% to 86%) | 0% (0% to 12%) | 58% (32% to 81%) | 36% (25% to 48%) | 549 | 87 |
| saas-support | validation | 39 | 69% (51% to 82%) | 75% (58% to 87%) | 36% (27% to 46%) | 88% (80% to 93%) | 56% (27% to 81%) | 0% (0% to 13%) | 70% (40% to 89%) | 14% (7% to 24%) | 494 | 99 |
| teacher | tuning | 39 | 79% (64% to 89%) | 84% (70% to 93%) | 50% (40% to 60%) | 83% (74% to 89%) | 62% (31% to 86%) | 4% (1% to 18%) | 70% (40% to 89%) | 18% (11% to 29%) | 530 | 106 |
| entrepreneur | demo | 21 | 67% (35% to 88%) | 67% (35% to 88%) | 77% (50% to 92%) | 96% (90% to 98%) | 100% (34% to 100%) | 12% (2% to 47%) | n/a | n/a | 215 | 87 |
| knowledge-company | demo | 28 | 94% (74% to 99%) | 100% (82% to 100%) | 67% (49% to 81%) | 93% (86% to 97%) | 67% (21% to 94%) | 7% (1% to 31%) | n/a | n/a | 289 | 76 |
| personal | demo | 22 | 91% (62% to 98%) | 91% (62% to 98%) | 87% (62% to 96%) | 94% (88% to 97%) | 100% (21% to 100%) | 0% (0% to 30%) | n/a | n/a | 250 | 80 |
| programmer | demo | 22 | 70% (40% to 89%) | 90% (60% to 98%) | 82% (52% to 95%) | 94% (88% to 97%) | 100% (34% to 100%) | 11% (2% to 44%) | n/a | n/a | 190 | 85 |

- tuning (4 Brains): needed-note recall mean 76%, worst 64% (bistro); reachable mean 85%, worst 79% (bistro); precision mean 52%, worst 50% (teacher); off-topic set: nothing mean 90%, worst 83% (teacher); own off-topic: nothing mean 67%, worst 60% (dental); false nothing mean 2%, worst 4% (dental); must-hold recall mean 84%, worst 70% (teacher); must-hold decoys mean 27%, worst 55% (dental).
- validation (3 Brains): needed-note recall mean 64%, worst 59% (contractor); reachable mean 71%, worst 63% (contractor); precision mean 45%, worst 36% (saas-support); off-topic set: nothing mean 93%, worst 88% (saas-support); own off-topic: nothing mean 76%, worst 56% (saas-support); false nothing mean 2%, worst 3% (contractor); must-hold recall mean 58%, worst 50% (contractor); must-hold decoys mean 18%, worst 32% (foodbank).
- sealed (3 Brains): needed-note recall mean 72%, worst 67% (realtor); reachable mean 81%, worst 79% (realtor); precision mean 46%, worst 38% (realtor); off-topic set: nothing mean 90%, worst 85% (designer); own off-topic: nothing mean 74%, worst 62% (realtor); false nothing mean 0%, worst 0% (designer); must-hold recall mean 75%, worst 58% (realtor); must-hold decoys mean 29%, worst 36% (realtor).
- demo (4 Brains): needed-note recall mean 81%, worst 67% (entrepreneur); reachable mean 87%, worst 67% (entrepreneur); precision mean 78%, worst 67% (knowledge-company); off-topic set: nothing mean 94%, worst 93% (knowledge-company); own off-topic: nothing mean 92%, worst 67% (knowledge-company); false nothing mean 8%, worst 12% (entrepreneur).

## The demo Brains as configured, by meaning

| Brain | Split | Notes | Needed-note recall | Reachable | Precision | Off-topic set: nothing | Own off-topic: nothing | False nothing | Must-hold recall | Must-hold decoys | Avg tokens | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| entrepreneur | demo | 21 | 78% (45% to 94%) | 78% (45% to 94%) | 77% (50% to 92%) | 96% (90% to 98%) | 100% (34% to 100%) | 12% (2% to 47%) | n/a | n/a | 222 | 82 |
| knowledge-company | demo | 28 | 100% (82% to 100%) | 100% (82% to 100%) | 66% (47% to 80%) | 93% (86% to 97%) | 67% (21% to 94%) | 7% (1% to 31%) | n/a | n/a | 274 | 97 |
| personal | demo | 22 | 91% (62% to 98%) | 91% (62% to 98%) | 87% (62% to 96%) | 94% (88% to 97%) | 100% (21% to 100%) | 0% (0% to 30%) | n/a | n/a | 267 | 94 |
| programmer | demo | 22 | 70% (40% to 89%) | 90% (60% to 98%) | 91% (62% to 98%) | 95% (89% to 98%) | 100% (34% to 100%) | 11% (2% to 44%) | n/a | n/a | 190 | 115 |

## The private Brain, by meaning

| Setting | Notes | Recall | Reachable | Precision | Off-topic set: nothing | False nothing |
| --- | --- | --- | --- | --- | --- | --- |
| Zero-config | 130 | 85% (76% to 91%) | 90% (82% to 95%) | 54% (48% to 59%) | 80% (71% to 87%) | 3% (1% to 11%) |
| As configured | 130 | 95% (89% to 98%) | 97% (90% to 99%) | 69% (65% to 73%) | 80% (71% to 87%) | 3% (1% to 11%) |

The configured lines carry the hints written against these same requests; zero-config is what a
new person's Brain would see.

## By words only, zero-config

- tuning (4 Brains): needed-note recall mean 53%, worst 45% (bistro); reachable mean 62%, worst 52% (bistro); precision mean 55%, worst 48% (teacher); off-topic set: nothing mean 50%, worst 46% (dental); own off-topic: nothing mean 31%, worst 0% (dental); false nothing mean 2%, worst 4% (dental); must-hold recall mean 81%, worst 70% (dental); must-hold decoys mean 23%, worst 62% (dental).
- validation (3 Brains): needed-note recall mean 51%, worst 48% (foodbank); reachable mean 53%, worst 48% (foodbank); precision mean 50%, worst 41% (saas-support); off-topic set: nothing mean 57%, worst 51% (contractor); own off-topic: nothing mean 38%, worst 25% (foodbank); false nothing mean 1%, worst 3% (contractor); must-hold recall mean 59%, worst 31% (foodbank); must-hold decoys mean 12%, worst 19% (foodbank).
- sealed (3 Brains): needed-note recall mean 56%, worst 49% (realtor); reachable mean 61%, worst 56% (realtor); precision mean 48%, worst 41% (realtor); off-topic set: nothing mean 52%, worst 49% (designer); own off-topic: nothing mean 28%, worst 12% (realtor); false nothing mean 1%, worst 4% (lab); must-hold recall mean 55%, worst 33% (lab); must-hold decoys mean 19%, worst 21% (designer).
- demo (4 Brains): needed-note recall mean 69%, worst 50% (programmer); reachable mean 69%, worst 50% (programmer); precision mean 77%, worst 62% (knowledge-company); off-topic set: nothing mean 73%, worst 67% (knowledge-company); own off-topic: nothing mean 54%, worst 0% (personal); false nothing mean 6%, worst 12% (entrepreneur).

## LongMemEval (small), by meaning, zero-config

Matching: words and meaning. 60 questions (10 per type, abstention questions left out), each its own Brain of 197 to 300 notes (median 242). 1129 s.

| Question type | Questions | Recall | Reachable | Avg tokens |
| --- | --- | --- | --- | --- |
| knowledge-update | 10 | 75% (53% to 89%) | 100% | 487 |
| multi-session | 10 | 77% (57% to 90%) | 86% | 706 |
| single-session-assistant | 10 | 90% (60% to 98%) | 100% | 762 |
| single-session-preference | 10 | 90% (60% to 98%) | 90% | 814 |
| single-session-user | 10 | 100% (72% to 100%) | 100% | 348 |
| temporal-reasoning | 10 | 61% (39% to 80%) | 83% | 557 |
| **all** | 60 | 79% (69% to 86%) | 92% | 612 |

## Latency by Brain size, by meaning

| Notes | First brief (index built) ms | p50 ms | p95 ms |
| --- | --- | --- | --- |
| 50 | 3878 | 40 | 83 |
| 500 | 15673 | 119 | 235 |
| 5000 | 161583 | 502 | 708 |

One request at a time on this PC (GTX 1060, scoring on the CPU), each in its own conversation after
one warm-up request. The first brief builds the index and embeds every note once (cached after).
The target is p95 under 150 ms at 5,000 notes; scoring walks every note in Python, which is the
work the plan's note-by-note index (3.7) is for.

## What it says

- **Precision is the gap everywhere:** about half of the notes a brief sends are needed or useful,
  on every split. The configured demos and the configured private Brain reach 69% to 80%: the hand
  hints were doing that work.
- **Validation Brains score lower than tuning ones** (reachable 71% against 85%): a fifth Brain
  cannot be predicted from four, which is why the gates read the mean and the worst Brain.
- **By words only, an off-topic request still gets a note about half the time:** a request that
  shares one word with a note scores like a real one.
- **Must-holds** come in through the area a selected note sits in, so a rule over a whole area
  (dental's patients) rides along with most requests (decoys up to 55%).
