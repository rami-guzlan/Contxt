# Retrieval baseline, October 9, 2026

Phase 0 of the brain-logic plan: needed-note recall on the demo Brains' labeled requests (`packages/brain/tests/evals/retrieval.json`, 37 requests, 10 held out), before any retrieval change. Run with `scripts/retrieval_eval.py` (add `--models <folder>` to match by meaning). The gate for the retrieval phase is 90% needed-note recall on held-out requests, with noise at 15% of brief tokens or less.

## By words

Matching: words only. Request type read right: 89%.

| Set | Cases | Needed-note recall | Listed too | Precision | Noise (tokens) | Avg tokens |
| --- | --- | --- | --- | --- | --- | --- |
| tuning | 27 | 64% | 64% | 76% | 0% | 186 |
| holdout | 10 | 55% | 55% | 62% | 0% | 183 |
| all | 37 | 61% | 61% | 72% | 0% | 185 |

| Brain | Cases | Recall | Precision | Noise | Avg tokens |
| --- | --- | --- | --- | --- | --- |
| entrepreneur | 8 | 33% | 78% | 0% | 147 |
| knowledge-company | 13 | 75% | 62% | 0% | 194 |
| personal | 8 | 80% | 69% | 0% | 243 |
| programmer | 8 | 44% | 100% | 0% | 149 |

## Misses and noise

- entrepreneur, en-angel-check: missed investing-approach
- entrepreneur, en-intro-candidate (held out): missed people-intros
- entrepreneur, en-mrr: missed ventures-loopline-metrics
- entrepreneur, en-ae-scorecard: missed hire-a-first-account-executive
- entrepreneur, en-plumbers-need (held out): missed plumbing-launch
- entrepreneur, en-call-tomas: missed me-schedule
- knowledge-company, kc-linkedin-webinar: missed q4-webinar-series
- knowledge-company, kc-podcast-guests: missed marketing-podcast-format
- knowledge-company, kc-small-shop-ads: missed customers-out-of-scope
- knowledge-company, kc-subscriber-count (held out): missed company-numbers
- personal, ps-dinners: missed food-diet
- personal, ps-eating-out (held out): missed money-budget
- programmer, pg-friday-deploy: missed work-deploys
- programmer, pg-review-pr: missed practices-reviews-checklist
- programmer, pg-backoff-bug (held out): missed practices-testing
- programmer, pg-react-form: missed stack-frontend
- programmer, pg-split-service: missed people-team

## By words and meaning (bge-small-en-v1.5)

Matching: words and meaning. Request type read right: 89%.

| Set | Cases | Needed-note recall | Listed too | Precision | Noise (tokens) | Avg tokens |
| --- | --- | --- | --- | --- | --- | --- |
| tuning | 27 | 61% | 70% | 87% | 0% | 196 |
| holdout | 10 | 73% | 82% | 85% | 0% | 163 |
| all | 37 | 64% | 73% | 86% | 0% | 187 |

| Brain | Cases | Recall | Precision | Noise | Avg tokens |
| --- | --- | --- | --- | --- | --- |
| entrepreneur | 8 | 33% | 80% | 0% | 182 |
| knowledge-company | 13 | 69% | 85% | 0% | 187 |
| personal | 8 | 90% | 86% | 0% | 230 |
| programmer | 8 | 56% | 100% | 0% | 148 |

## Misses and noise

- entrepreneur, en-angel-check: missed investing-approach
- entrepreneur, en-intro-candidate (held out): missed people-intros
- entrepreneur, en-mrr: missed ventures-loopline-metrics
- entrepreneur, en-ae-scorecard: missed hire-a-first-account-executive
- entrepreneur, en-plumbers-need (held out): missed plumbing-launch
- entrepreneur, en-call-tomas: missed me-schedule
- knowledge-company, kc-linkedin-webinar: missed q4-webinar-series
- knowledge-company, kc-podcast-guests: missed marketing-podcast-format
- knowledge-company, kc-small-shop-ads: missed customers-out-of-scope
- knowledge-company, kc-subscriber-count (held out): missed company-numbers
- knowledge-company, kc-audience-worries: missed customers-pains
- personal, ps-dinners: missed food-diet
- programmer, pg-friday-deploy: missed work-deploys
- programmer, pg-review-pr: missed practices-reviews-checklist
- programmer, pg-react-form: missed stack-frontend
- programmer, pg-split-service: missed people-team
