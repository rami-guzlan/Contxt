# Heartbeat learning: the recorded day, Oct 25, 2026

The recorded day (`scripts/heartbeat_day.json`) was run through the real capture code and one distill on Claude Haiku (the ingest model), on a fresh scratch Brain made from the Brightmill demo starter, offline (relevance by the words score; no meaning model). The day has 50 invented items with 75 changes across four sources. Every route was labelled before any tuning. Run it with `scripts/heartbeat_day_eval.py --env <scratch home>/.env`.

## Results

| Run | What changed before it | Route accuracy | Undone caught | Filter precision | Tokens | Lessons | Must-wait written | Gates |
|---|---|---|---|---|---|---|---|---|
| 1 | none | 88% | 10 of 10 | 100% | 26,322 | 0 (failed) | **2** | failed |
| 2 | code flags tasks and sheet values that send, post, reach a customer or spend | 82% | 10 of 10 | 100% | 28,854 | 0 (failed) | 0 | accuracy failed |
| 3 | the prompt: no sheet means project progress, not Catch up; lessons get their words; a must-wait item counts as right when it waits | 88% | 10 of 10 | 100% | 27,407 | 3 | 0 | **all pass** |
| 4 | the same, again | 88% | 10 of 10 | 100% | 23,458 | 3 | 0 | **all pass** |

Gates (plan 14.7):
- route accuracy at least 85%;
- nothing that must wait written without review;
- tokens per distill no more than the median beat judge cost (about 3,700) times beats with news a day (20), so 74,000.

## What the runs found

1. **What must wait can't be left to the model.** In run 1, Haiku routed "email all attendees that session 2 moved" and "raise the ad budget to 900 a month" as ordinary tasks, without the customer-facing or spending flags, so they went in under Auto. Code now flags every task or sheet value whose words send, post, reach a customer or spend money (the orchestrators' gate words, plus discount and pricing). Those wait for the owner whatever the model says. A test covers it.
2. **A young Brain has few sheets.** The model sent short-term values to Catch up because "the Brain has no sheet to hold it". The prompt now routes those to the project's progress, or to a task when they ask for an action. The remaining misses are CRM values for customers with no project in the Brain; they still go to Catch up, which is conservative.
3. **Lessons need words that bring them up.** The model's three patterns were refused until each lesson carried its words. The prompt asks for them, and code falls back to the title's words.

## Remaining misses (runs 3 and 4)

- Deal health, pipeline count and account health for customers with no project in the Brain: Catch up, labelled short.
- A renewal date: long-term, labelled short.
- A vendor newsletter whose title says "webinar": the words score called it relevant, so it was kept for the distill, which discarded it. It was labelled as dropped at capture.
- Once, a webinar platform receipt (filter matched, goal relevant): discarded, labelled kept.

## Not yet measured

- With the local meaning model installed: relevance by meaning, not words.
- A real night on real connectors.
