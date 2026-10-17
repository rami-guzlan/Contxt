# Reuse vector magnitudes between requests

October 17, 2026. Base: `52d21e417c6d2e59b33e19b7a241b57662ff6210`.

Cosine scoring recalculated both vector magnitudes for every query/item pair. Stored
vectors are immutable for the lifetime of an index snapshot. Cache their magnitudes on
that index and calculate the query magnitude once per scoring pass. A rebuilt snapshot
gets a fresh cache. The existing lock protects initialization.

The dot product, denominator and enrichment-hint folding keep the same arithmetic. No
ranking formula, threshold, candidate limit, budget, scope or mandatory-rule policy changes.
The change adds no model or provider call and does not persist additional Brain data.

## Measurement

The existing scale generator combined public generated and demo notes into a 5,000-note
Brain. The same 38 requests ran in three paired passes, alternating old/new order. Query
embeddings were precomputed for both methods; the router's request-similarity cache was
cleared for each timed call. The same live snapshot, fixed clock and session identifier
were used. These are routing measurements, excluding new query inference and cold startup.

| Warm routing | Before | After |
| --- | --- | --- |
| Median | 209.0 ms | 173.1 ms |
| p95 | 270.2 ms | 228.3 ms |

All 114 paired packet texts and data dictionaries were exactly equal, excluding randomly
generated packet identifiers. This is about a 16% p95 reduction on this machine. Timing
varies with hardware and workload; the 150 ms production target remains unmet.

## Regression coverage and release requirements

Tests first reproduced repeated normalization: 16 stored vectors and eight queries required
256 magnitude calculations. The bound is now 24. Separate tests require exact equality
with pairwise cosine across multiple dimensions, zero/empty and non-unit vectors, negative
similarities and enrichment questions, plus isolation between snapshots.

Release requires the existing quality checks across ten generated Brains, four demos and
the read-only enriched private copy, with no changed counts, and complete local Windows
and Linux CI on the exact commit. The suites include PostgreSQL, web checks, real meaning
and speech models, install/connect/serve, and Docker startup/export/restore. The existing
180 frozen packets and all labels, fixtures and numerical gates must remain unchanged.

GitHub Actions billing is unavailable; the owner authorized local checks instead. Native
macOS is unavailable and is not claimed. This improves computation cost, not retrieval
precision or recall. Broader production quality targets remain unmet.
