# Report card, 2026-10-10

Every bar the brain-logic, UX and goals plans set, run again on the packaged demo Brains. Stand-ins are named where they stand in; what needs real models or a person is listed at the end.

## Retrieval

| Set | Cases | Needed-note recall | Whole | Listed too | Precision | Noise (tokens) | Avg tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tuning | 34 | 72% | 72% | 75% | 73% | 2% | 219 |
| holdout | 14 | 83% | 83% | 83% | 67% | 0% | 225 |
| all | 48 | 75% | 75% | 77% | 71% | 1% | 221 |

Should get nothing: 8 requests, 62% got nothing (correct nothing). Needed something but got nothing: 8% (false nothing).

| Brain | Cases | Recall | Precision | Noise | Avg tokens |
| --- | --- | --- | --- | --- | --- |
| entrepreneur | 10 | 67% | 80% | 0% | 172 |
| knowledge-company | 17 | 83% | 57% | 3% | 252 |
| personal | 10 | 91% | 71% | 0% | 273 |
| programmer | 11 | 50% | 100% | 0% | 169 |

## Gates, by plan section

| Section | Passed | Failed | Skipped |
| --- | --- | --- | --- |
| BL 5.9 to 5.11: retrieval, briefs, the kernel, the local engine | 74 | 0 | 0 |
| BL 6: one statement model | 15 | 0 | 0 |
| BL 7.4: ingestion and distillation | 27 | 0 | 0 |
| BL 8.9: State and working contexts | 11 | 0 | 0 |
| BL 9: the updating loop | 44 | 0 | 0 |
| BL 10.6: proof | 3 | 0 | 0 |
| BL 17.9: the knowledge agent run locally | 14 | 0 | 0 |
| Goals G1 to G4 | 44 | 0 | 0 |
| UX F and G3: workflows | 21 | 0 | 0 |

## Drift on long runs (stand-in with bounded attention)

| | Objective kept | Must-holds in view | Finished |
| --- | --- | --- | --- |
| With re-anchoring | 83% | 100% | 100% |
| Without | 0% | 8% | 0% |

Lost with re-anchoring: long-5, a distractor closer to the end than the cadence (8 calls).

## Four simulated weeks (knowledge-company)

| Week | Kernel stable | Briefs moved | Unexplained | Stale caught | Bent rules flagged | Goal cards |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | yes | 1 | 0 | 1 | 0 | 0 |
| 2 | yes | 1 | 0 | 1 | 0 | 0 |
| 3 | yes | 1 | 0 | 1 | 1 | 0 |
| 4 | yes | 1 | 0 | 1 | 1 | 1 |

## The alignment tax

- First brief of a chat (with the startup context): 42% of 994 tokens on alignment (414).
- Later briefs: 14% of 323 tokens (47).
- The deterministic output check: 0.04 ms at most per draft.
- Quality with and without alignment waits for real runs and a blind judge.

## The knowledge agent's labeled set (oracle stand-in)

24 cases: valid answers 100%, no direct writes 100%, impact lines matching 100%, hand-ups 0. The oracle checks the harness; agreement with Claude Code waits for the PC.

## Waiting for Rami

- Labels for the private eval set, including about 20 requests that should get nothing.
- Confirming Claude Code for the knowledge agent as an opt-in once a local agent model is here.
- Confirming a preference as a subtype of rule.
- Labeled transcripts and the interview sorting exercise (ingestion precision, recall and tier routing).
- The live Brain's content proposals (core facts to must-holds by domain, identity bullets), in his app.
- The walkthrough on the demo Brain and a real day on the live Brain, then sign-off.
- G4: a goal of his own through the coach, the T-41 story and the two interviewees; board restraint counted from those; objectives judged blind.
- The private agent set from his own Catch up decisions.

## Waiting for The PC and real runs

- Model downloads, pins and verification; the setup comparison B to E; defaults; cut fitting; speed; Kev-0.8B's qualification.
- The knowledge agent per machine setup: agreement with Claude Code, hand-up rates, speed; 4B against 9B against Claude Code.
- Triage measured; cost per hour of meeting; the coach timed on a real model.
- Drift on real Work runs (the stand-in here has bounded attention, not a model's); output quality with and without alignment, judged blind.
- Whether formulas help (kept only if proven helpful); the agent set grown to about 15 cases per action.

