# Release 1 baseline (M00), October 20, 2026

The starting point for the Release 1 build (docs/dev/plans/release1-plan.md). Every later step is compared with these numbers. Nothing here is tuned. Numbers come from runs on the owner's Windows PC, by meaning, with the CPU meaning index.

**Frozen at:**
- **Code:** main at f24c811 (merge of #46).
- **Locks:** uv.lock, package-lock.json, packages/brain/src/brainkit/models.lock.json.
- **Test models:** F:\contxt-dev\test-models, written by scripts/fetch_test_models.py.
- **Question sets:**
  - the LongMemEval development and release cohorts in F:\contxt-dev\ci\passage-cohorts (the release cohort is untouched);
  - the generated Brains' sealed split (untouched);
  - packages/brain/tests/evals/scope.json (new, below).
- **Local CI:** F:\contxt-dev\tools\local_ci.sh runs every CI job, including the core on PostgreSQL 16.

## Retrieval across Brains, zero-config (scripts/general_eval.py --demos --null)

| Set | Recall | Reachable | Precision | Off-topic nothing | False nothing | Must-hold decoys |
| --- | --- | --- | --- | --- | --- | --- |
| tuning (4 Brains) | 60% | 90% (worst 84%) | 70% (worst 68%) | 96% | 1% (worst 4%) | 41% (worst 67%) |
| validation (3 Brains) | 58% | 84% (worst 73%) | 71% (worst 66%) | 95% | 2% (worst 7%) | 42% (worst 51%) |
| demo (4 Brains) | 82% | 100% | 88% (worst 71%) | 96% | 4% (worst 14%) | n/a |

**Latency at 5,000 notes, warm (#46):** median 114 ms, p95 207 ms.

**Against the master plan's targets:**

| Target | Status |
| --- | --- |
| Precision 80% | Missed on every generated set |
| Reachable 90% | Met on tuning only |
| Off-topic nothing 95% | Met |
| False nothing 2% | Met on average, missed on the worst Brains |
| p95 150 ms | Missed |
| Must-hold decoys at most 5% | Missed widely |

## Project scope and current values (new: scripts/scope_eval.py)

Four invented projects, each a Focus with an objective, two pinned notes and five filed notes, beside Brain-wide notes. 28 requests, plus dated updates and same-date conflicts.

| Measure | f24c811 | This PR |
| --- | --- | --- |
| Needed note reached, project named | 20/20 | 20/20 |
| Needed note whole, project named | 10/20 | 12/20 |
| Needed note reached, subject only | 4/4 | 4/4 |
| Status request delivers every pin | 0/4 | 4/4 |
| Named project recognized | 18/24 | 18/24 |
| No other project's notes, project recognized | 15/18 | 18/18 |
| No other project's notes, every request | 20/28 | 23/28 |
| Newest value current, older marked | 2/2 | 2/2 |
| Same-date conflict shows both values | 1/2 | 1/2 |

**Findings:**
- **A request that named a project still received other projects' notes.** It also received none of the project's pinned notes when it asked where the project stands. This PR fixes both:
  - notes filed with another project are removed after selection, so scope never brings in a weaker note;
  - pins go with every request about the project.
- **The rest of the leaks come from projects the router does not recognize.** These are requests like "the office move" against a project named "Office move to Pine Avenue". Recognizing the active project (an explicit project, a connected app's working folder) is a later step.
- **A conflict between two values dated the same day is resolved by picking one.** That is the newest-wins behaviour M04 replaces.

**One cost:** the programmer demo's precision falls from 100% to 86%. The router names the wrong project for "Can I ship the route planner change Friday afternoon?" (the tidyq release, through the distinctive word "ship"). That project's pin now goes with it. The wrong project was chosen before this PR too; the pin makes the mistake visible in precision.

## The owner's private Brain, aggregates only

On the owner's yes, Claude Haiku 5.5 enriched a private copy on F: (113 notes, none failed). Scored on the Brain's own 68 labelled requests, zero-config:

| | Recall | Reachable | Precision | Off-topic nothing | False nothing |
| --- | --- | --- | --- | --- | --- |
| Not enriched | 68% | 89% | 63% | 94% | 5% |
| Enriched with Haiku 5.5 | 70% | 89% | 59% | 93% | 5% |

Enrichment with Haiku did not move this Brain: every difference is inside the intervals. The owner's real Brain was not changed.
