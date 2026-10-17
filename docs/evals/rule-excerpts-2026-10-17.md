# Render rule excerpts within their allowance

October 17, 2026. Base: `470612f74ad69fdfd97f8eff076f835e4e2d3532`.

When a rule did not fit in full, packing correctly selected and counted a short excerpt.
Rendering then emitted the entire rule body under Your rules and the excerpt again under
Notes. The packet therefore exceeded the allowance and the ledger undercounted its delivery.
The same mismatch affected the optional local engine's pointer decisions.

Render the chosen excerpt once, under Your rules, with an explicit instruction to open
the complete rule before applying it. Rules that fit remain complete. Mandatory must-holds
retain their separate full-text delivery outside the ordinary note allowance. Rules that
do not fit even in short remain named and available to open, as before.

## Evidence

Two new tests failed before the fix, reproducing the normal and engine paths. Five new
tests now check those paths, full-note upgrades, named overflow and mandatory-rule delivery
at both tiny and normal allowances. Together with packet, routing, file and engine tests,
136 focused tests and five subtests pass.

In the fictional regression, a rule with an estimated 1,001 tokens was recorded as a
22-token excerpt against a 150-token note allowance. The old packet contained the full
body as well as that excerpt, totalling an estimated 1,128 tokens. The corrected packet
contains the selected excerpt, retains its rule authority and open instruction, and totals
98 estimated tokens. This is a deterministic rendering example, not a corpus performance
or answer-quality claim. Token counts use the existing estimator.

The frozen quality suites were rerun on ten generated Brains, four demos and the enriched
private copy. All 15 sets of counts and all
1828 public case rows remain unchanged except timing. These regression
metrics already classified those rules as pointers, so they do not independently prove
downstream answer quality. The new tests prove that displayed content now agrees with the
selected form and delivery accounting. A caller must open the full rule when instructed.

No ranking, admission, scope, must-hold policy, labels, gates, budgets or pointer limits
change. Private case data remains outside the repository. Exposed evaluation sets remain
regression evidence rather than fresh sealed acceptance. General retrieval precision,
abstention, downstream answer quality and production-readiness targets remain open.

Release requires complete Windows and Linux local CI on the exact commit, including
PostgreSQL, web, real meaning/speech models, install/connect/serve and Docker checks.
The owner authorized local verification while hosted Actions billing is unavailable.
Native macOS is unavailable and is not claimed as tested.
