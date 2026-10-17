# Remember the evidence a conversation actually received

October 17, 2026. Base: `27ed07c2739de45536a9b4d0dc09e7057f872e05`.

Short notes include the sentence closest to the current request. Previously every short
view of an unchanged note had the same delivery marker. After a question about one fact,
a question about a different fact could withhold the newly needed sentence as already
delivered. File sections had the same problem: clipped quotes were recorded as though
the complete section had been sent, hiding additional evidence on a later larger request.

## Change

Record partial deliveries by source version and the exact rendered text. Record complete
sections separately from partial quotes. A conversation may receive a different excerpt,
a larger quote, or a full note without falsely treating unseen evidence as already held.
Repeated excerpts remain held even after another excerpt of the same source version.
The packet identifies held partial views as "excerpt only".

The ledger retains the latest hash, packet and timestamp fields, and derives the set of
rendered hashes from consecutive deliveries of that source version in the current session
epoch. A source change, reversion after an intervening delivery, or session refresh makes
the evidence available again. Stable row order resolves equal timestamps. No database
schema or stored knowledge changes are needed.

Older pointer and section markers cannot prove which text was delivered. They refresh
once within the existing budgets, then use exact delivery accounting. Full note markers
remain compatible with explicit note reads and existing startup hooks.

## Verification

Tests first reproduced seven failures: changed note excerpts, larger section views,
metadata-only pointer changes, and ambiguous legacy delivery records hid unseen evidence.
Five existing-behavior cases in the same new suite already passed.

Fifteen regression tests cover those failures, repeated views, pointer-to-full upgrades,
session separation and refresh, source changes and reversions, and equal timestamps.
Focused routing, file, engine and new packet tests pass together.

The same frozen retrieval suites were rerun on ten generated Brains, four demos and the
enriched private copy. All 15 sets of counts and all
1828 public case rows are unchanged except timing. These tests use fresh
sessions; they guard against ranking and admission regressions, while the new conversation
tests demonstrate the delivery fix. Private content and case-level results remain outside
the repository. No model calls are needed for this change.

No thresholds, labels, evaluation gates, token budgets, pointer limits, mandatory-rule
policy or scope rules change. The existing exposed sets are regression evidence, not
fresh sealed acceptance. This corrects session recall accounting; it does not establish
better general retrieval precision or claim production readiness.

Release requires complete Windows and Linux local CI on the exact commit, including
PostgreSQL, web, real meaning/speech models, install/connect/serve and Docker checks.
The owner authorized local checks in place of hosted Actions while billing is unavailable.
Native macOS is unavailable and is not claimed as tested.
