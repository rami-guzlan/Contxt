# Match words through an inverted index

October 17, 2026. Base: `6968925bd08a37431c586dcc938105c3c9380523`.

BM25 scanned every requested document for every query term, including documents with
no matching words. Hybrid routing separately repeated the same scan for weighted query
coverage. Build term-to-document postings with each immutable index snapshot, score only
matching entries, and compute coverage for the candidate group in one pass.

Keep the original query-term addition order, BM25 formula and caller's document order.
No ranking weights, thresholds, labels, candidate or pointer limits, scope rules, token
budgets or models change. Postings are memory-only and rebuilt with each new snapshot.
Their cost is one additional mapping entry per distinct document term.

## Verification

Tests first reproduced 2,000 document-term probes for a sparse query against 1,000 notes.
The optimized scorer performs no per-document term probes for that request. Five tests
and 224 subtests check exact scores and order against the old formula, repeated terms,
missing/empty documents, restrictions, weighted coverage and isolation between snapshots.
A long-query regression also requires the original compensated floating-point summation,
not a tolerance that could hide a score change.

The existing public scale suite contains 5,000 notes. The same 38 requests ran in three
paired passes, alternating old/new order on the same snapshot. Query embeddings were
precomputed for both; the router's request-similarity cache was cleared before each call.
Every one of the 114 complete packets matched exactly, apart from random packet IDs.

| Warm routing | Before | After |
| --- | --- | --- |
| Median | 174.2 ms | 150.1 ms |
| p95 | 244.8 ms | 216.1 ms |

These timings exclude cold startup and query inference. They do not establish the
150 ms end-to-end production target. Timing varies by machine and workload.

All quality counts across ten generated Brains, four demos and the enriched private
copy are unchanged. All 1828 public case rows match except timing. Private
content and individual results stay outside the repository. No provider calls are needed.

Release requires complete local Windows and Linux CI on the exact commit, including
PostgreSQL, web, actual meaning/speech models, install/connect/serve, Docker ownership,
export/restore and default startup. The owner authorized local checks in place of
unavailable hosted Actions billing. Native macOS is unavailable and is not claimed.

## Quality experiment rejected

A separate source-support abstention study kept the existing model and numeric gates.
Its protected variant withheld ordinary notes only after existing mandatory-rule selection.
Validation ordinary off-topic errors fell from 14 to 1 out of 300 without losing ordinary
evidence or mandatory rules. Extension to other Brains exposed a programmer-demo regression:
needed recall fell from 8/10 to 7/10 and false-empty requests rose from 0/9 to 1/9.
The method is rejected, with no special-case exception added. It is not part of this change.

These quality sets have been exposed during development. They are regression evidence,
not fresh sealed acceptance. Broader precision, recall, abstention and production-quality
targets remain unmet. The performance change does not claim to improve those metrics.
