# Project fact pointers, October 17, 2026

Factual questions about a named project could stop at its overview, leaving separately
approved facts undiscoverable in the first packet. Also, related IDs could exist in packet
metadata without being rendered in focus-only text. MCP sends that text to the model, so
metadata alone does not prove that a source was reachable.

The correction lists relevant project-associated facts as bounded pointers and renders
those pointers in project-only packets. A calling model can open the original evidence.
The body-selection thresholds, token budgets, pointer limit, evaluation labels, calibration
banks and all numerical gates are unchanged. General overviews stay concise. Membership
is cached with the index; newly filed notes rebuild it and callers are admitted separately.

## Regression evidence

Ten targeted tests cover approved undated facts, model-visible pointers, facts filed outside
the project folder, private/manual exclusions, per-caller cache isolation, invalidation on a
new note, general overviews, no-tools clients and session delivery after opening a note.
The tests initially reproduced missing pointers; the new behavior passes. Existing retrieval
and mandatory-rule tests also pass.

All measured aggregate counts are identical on the ten generated Brains, four demos and
enriched private snapshot, using the same clock, meaning model and 100 off-topic requests
per Brain. The private results remain 72/88 needed, 70/88 whole, 82/88 reachable, 106/158
precision counts, 93/100 off-topic abstentions and 2/63 false-empty cases. The source
fingerprint remains unchanged. No additional private model requests were made.

Exactly three of 180 golden packets intentionally append an existing-size related-pointer
section: the programmer Friday-update question, queue-release remaining-work question and
current-version question. Each exact diff was reviewed. The original packet text is preserved
as a prefix; no full body or rule is added or removed. The other 177 packets are unchanged.
Only those three expected strings are updated, not the benchmark labels or numerical floors.

## Native model follow-through

A separate experiment uses the already approved fictional workshop facts, Claude Haiku 5.5
and the real production MCP transport. The test server exposes only gnomon_get_context,
notes_get and notes_search. Each of three requests gets its first response with no retries,
labels or expected answers in the prompt. Both revisions correctly answer the approved
$4,800 budget, Jonas and the October 28 deadline, and recognize that catering ownership is
not established. The candidate reaches the budget with context then notes_get; baseline
needs context, notes_search and notes_get. Both answer the compound venue question from the
packet, including its pointer summary. This is a small integration check, not an answer
accuracy benchmark or a measured latency improvement. Source data remains unchanged.

An earlier simulated tool-choice experiment used a no-tools CLI system prompt and is
excluded from workflow conclusions. Its raw results remain in the local experiment record.

## Limits and release checks

This fixes a discovery/visibility gap; it does not raise the measured aggregate quality
numbers to production targets. The compound venue request still does not include both
source bodies in full, although its answer is reachable and the native calling model uses
it correctly. Broadly promoting project candidates to full notes added unrelated material
and was rejected. No paid verification call or generative model is enabled by this change.

Full local Windows and Linux checks, including real embedding/speech tests, PostgreSQL,
web and Docker smoke/restore, must pass on the committed revision before merge. macOS is
unavailable on this host. The PR records the exact local results.
