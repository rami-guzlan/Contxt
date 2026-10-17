# Orientation intent and retrieval, October 17, 2026

A concrete task mentioning a first day or week could take the general orientation path, which bypasses normal request-specific note selection. Creation tasks and incidental first-day/week mentions now use normal retrieval. Explicit general orientation remains available.

The natural-language expression also now reads the original lowercased text: search normalization removed single-letter pronouns and apostrophes, preventing some genuine orientation requests from matching.

The change has no provider, network, model, GPU, numerical threshold or corpus-specific rule.

## Frozen comparison

Same 15 Brains, UTC clock, embedding artifact, labels and 100 off-topic cases per Brain as the preceding pointer-domain correction. Private work runs on the frozen enriched copy and disposable ledgers. The real Brain is untouched.

| Brain | Measure | Before | After |
| --- | --- | --- | --- |
| contractor | precision | 29/40 | 28/37 |
| contractor | must_hold_decoys | 18/72 | 19/72 |
| lab | recall | 20/35 | 21/35 |
| lab | whole_recall | 20/35 | 21/35 |
| lab | reachable | 30/35 | 31/35 |
| lab | precision | 28/42 | 28/39 |
| lab | must_hold_decoys | 23/70 | 22/70 |
| saas-support | recall | 21/32 | 22/32 |
| saas-support | whole_recall | 21/32 | 22/32 |
| saas-support | reachable | 28/32 | 30/32 |
| saas-support | precision | 29/47 | 29/44 |
| saas-support | must_hold_decoys | 33/66 | 32/66 |

All unlisted counts are unchanged. The contractor Brain gains one unwanted rule while its note precision improves; this remains a known limitation of broad domain constraints, not a reason to change its labels. The private Brain retains 72/88 needed hits, 106/158 useful delivered notes, 82/88 reachable hits and 93/100 off-topic abstentions.

## Checks and limits

- Tests first reproduced four concrete tasks incorrectly classified as orientation and one explicit orientation request that was missed. Ten language cases now pass, along with the existing routing tests and all 180 parity briefs. No golden brief changed.
- Both historical and shipped-bank quantitative retrieval gates pass unchanged.
- Full local Windows/Linux checks are required before merging; results are recorded in the PR.
- This corrects routing intent. It does not claim that note precision, mandatory-rule decoys or all production-readiness targets have been solved.
- Separate query-verifier experiments remain outside product code. Wider discovery alone introduces irrelevant selections; it is not enabled by this change.
