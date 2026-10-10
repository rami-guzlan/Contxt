# Retrieval baseline, October 9, 2026

Phase 0 of the brain-logic plan: needed-note recall on the demo Brains' labeled requests (`packages/brain/tests/evals/retrieval.json`, 37 requests, 10 held out), before any retrieval change; a must-hold delivered in the Must hold section counts as delivered. Recall and precision are those of commit 29211c7; the token averages are those of briefs with authority labels and a framed task, about 30 tokens more than at 29211c7 (185 by words, 187 by meaning). Run with `scripts/retrieval_eval.py` (add `--models <folder>` to match by meaning). The gate for the retrieval phase is 90% needed-note recall on held-out requests, with noise at 15% of brief tokens or less. "Whole" counts only notes the brief carried in full, not in short.

## By words

Matching: words only. Request type read right: 89%.

| Set | Cases | Needed-note recall | Whole | Listed too | Precision | Noise (tokens) | Avg tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tuning | 27 | 70% | 70% | 70% | 76% | 0% | 215 |
| holdout | 10 | 73% | 73% | 73% | 62% | 0% | 212 |
| all | 37 | 70% | 70% | 70% | 72% | 0% | 214 |

| Brain | Cases | Recall | Precision | Noise | Avg tokens |
| --- | --- | --- | --- | --- | --- |
| entrepreneur | 8 | 44% | 78% | 0% | 173 |
| knowledge-company | 13 | 81% | 62% | 0% | 223 |
| personal | 8 | 90% | 69% | 0% | 288 |
| programmer | 8 | 56% | 100% | 0% | 166 |

## Misses and noise

- entrepreneur, en-angel-check: missed investing-approach
- entrepreneur, en-mrr: missed ventures-loopline-metrics
- entrepreneur, en-ae-scorecard: missed hire-a-first-account-executive
- entrepreneur, en-plumbers-need (held out): missed plumbing-launch
- entrepreneur, en-call-tomas: missed me-schedule
- knowledge-company, kc-linkedin-webinar: missed q4-webinar-series
- knowledge-company, kc-podcast-guests: missed marketing-podcast-format
- knowledge-company, kc-subscriber-count (held out): missed company-numbers
- personal, ps-dinners: missed food-diet
- programmer, pg-review-pr: missed practices-reviews-checklist
- programmer, pg-backoff-bug (held out): missed practices-testing
- programmer, pg-react-form: missed stack-frontend
- programmer, pg-split-service: missed people-team

## By words and meaning (bge-small-en-v1.5)

Matching: words and meaning. Request type read right: 89%.

| Set | Cases | Needed-note recall | Whole | Listed too | Precision | Noise (tokens) | Avg tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tuning | 27 | 67% | 67% | 73% | 87% | 0% | 224 |
| holdout | 10 | 82% | 82% | 91% | 85% | 0% | 191 |
| all | 37 | 70% | 70% | 77% | 86% | 0% | 215 |

| Brain | Cases | Recall | Precision | Noise | Avg tokens |
| --- | --- | --- | --- | --- | --- |
| entrepreneur | 8 | 44% | 80% | 0% | 210 |
| knowledge-company | 13 | 75% | 85% | 0% | 210 |
| personal | 8 | 90% | 86% | 0% | 275 |
| programmer | 8 | 67% | 100% | 0% | 168 |

## Misses and noise

- entrepreneur, en-angel-check: missed investing-approach
- entrepreneur, en-mrr: missed ventures-loopline-metrics
- entrepreneur, en-ae-scorecard: missed hire-a-first-account-executive
- entrepreneur, en-plumbers-need (held out): missed plumbing-launch
- entrepreneur, en-call-tomas: missed me-schedule
- knowledge-company, kc-linkedin-webinar: missed q4-webinar-series
- knowledge-company, kc-podcast-guests: missed marketing-podcast-format
- knowledge-company, kc-subscriber-count (held out): missed company-numbers
- knowledge-company, kc-audience-worries: missed customers-pains
- personal, ps-dinners: missed food-diet
- programmer, pg-review-pr: missed practices-reviews-checklist
- programmer, pg-react-form: missed stack-frontend
- programmer, pg-split-service: missed people-team
