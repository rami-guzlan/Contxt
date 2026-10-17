# Retrieval quality and enrichment correctness, October 17, 2026

This change fixes stale retrieval inputs and enrichment races. It does **not** close the
remaining static precision and recall gaps. All measured counts on fifteen Brains are
unchanged from main `4a8bbf8958edf2b95326078c85dded1fa7768e4d`.

## What changes

- A note's versioned search hints stop influencing words, meaning, generated topics and
  must-hold domain descriptions when its title, summary or body changes. Its current text
  remains searchable. Stored hints remain available for review and can be refreshed.
- The Knowledge Agent carries the version it read through the application service and
  adapter. Under the Brain write lock, an answer for an older version is rejected. This
  also protects owner-edited hints while a model is answering.
- Rewording a changed note's search hints does not validate obsolete applicability fields.
- Calibration is keyed to its actual retrieval content, note/domain ids, phrase configuration,
  model and unrelated request bank. A same-count edit no longer reuses stale calibration.
  Existing caches without content provenance rebuild once; unchanged inputs reuse the cache.

## Evaluation discipline

The four tuning Brains informed experiments. Only the rank-fusion candidate proceeded to
the separate validation set; its regressions rejected it. The three sealed Brains were read
only for the final before/after comparison, with no subsequent ranking adjustments.
The private work Brain contributed aggregate counts only. Frozen clock:
`2026-10-16T12:00:00+00:00`, UTC. The existing pinned CPU embedding artifacts were used.
No new model, provider or GPU requirement ships.

Both existing calibration-bank gates, all fixtures, labels, floors, numerical allowances,
token budgets and pointer limits remain unchanged. The synthetic tuning and validation
fixtures already contain generated enrichment; missing enrichment does not explain their
remaining static errors.

## Before and after

Every pair below is identical before and after. Reachable includes pointers; precision
counts delivered notes, not proof that a downstream answer is correct. Small samples and
generated labels limit conclusions. The separate off-topic set has 100 requests per Brain.

| Brain | Split | Needed recall | Reachable | Precision | Off-topic: nothing |
| --- | --- | --- | --- | --- | --- |
| bistro | tuning | 25/42 | 38/42 | 28/41 | 96/100 |
| contractor | validation | 22/41 | 30/41 | 29/40 | 93/100 |
| dental | tuning | 21/43 | 36/43 | 25/37 | 96/100 |
| designer | sealed | 25/40 | 35/40 | 34/48 | 95/100 |
| foodbank | validation | 26/50 | 43/50 | 35/48 | 97/100 |
| lab | sealed | 20/35 | 30/35 | 28/42 | 97/100 |
| lawfirm | tuning | 26/36 | 35/36 | 33/45 | 94/100 |
| realtor | sealed | 21/39 | 36/39 | 26/41 | 93/100 |
| saas-support | validation | 21/32 | 28/32 | 29/47 | 96/100 |
| teacher | tuning | 22/38 | 34/38 | 31/44 | 97/100 |
| entrepreneur | demo | 6/9 | 9/9 | 10/14 | 95/100 |
| knowledge-company | demo | 15/18 | 18/18 | 15/17 | 99/100 |
| personal | demo | 11/11 | 11/11 | 14/15 | 98/100 |
| programmer | demo | 8/10 | 10/10 | 10/10 | 92/100 |
| Private work Brain | private | 60/88 | 78/88 | 95/151 | 94/100 |

## Rejected experiments

These remain outside production and outside the new tests' expected results:

- Removing freshness from whole-note eligibility lost a needed dental note.
- Reciprocal rank fusion increased some tuning hits, but reduced validation reach and demo
  precision. The knowledge-company and personal demo precision rates fell below their gates.
- Direct ordering by the existing MiniLM cross-encoder lost three needed bistro notes on
  tuning. The [upstream model](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)
  was evaluated locally; it is not added to setup or enabled by this change.
- Using generated exclusions as a hard whole-note filter either changed no measured tuning
  outcomes or removed useful notes when compared directly with applicability text.
- Normalizing each note against its own unrelated background gained some hits but increased
  unnecessary must-holds and created a teacher false-nothing case. Background centering
  also failed to provide a consistent improvement. Neither calibration formula ships.

The remaining quality work requires stronger evidence than gains on a few tuning requests.
In particular, generated applicability is not an authoritative veto, a high similarity is
not proof of answerability, and a pointer is not the same as delivering the needed fact.

## Regression coverage and release gate

Tests first reproduced stale hints, a same-count calibration edit, an in-flight text edit,
an owner edit during the Knowledge Agent call, and revalidation of obsolete applicability.
Those cases pass after the fix. Legacy unversioned owner hints remain searchable.

Release requires the complete local Windows/Linux CI lanes, PostgreSQL, web checks,
actual meaning/speech tests, both unchanged retrieval gates, install/connect/serve, and
Docker ownership/export/restore and default Compose health. Hosted Actions are unavailable
because of billing; macOS is unavailable locally. Passing available checks must not be
reported as a macOS pass or as achieving the outstanding quality targets.
