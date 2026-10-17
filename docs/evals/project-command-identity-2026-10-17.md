# Project commands need subject evidence

October 17, 2026. Base: `f8cdc837aca100391573bddfc36616c03c5dd610`.

A project summary beginning with a capitalized command could turn that command into a
distinctive project name. For example, "Rewrite the launch material" could assign a
request to rewrite a birthday greeting to that project, bringing unrelated context with it.

If the only inferred distinctive match is an existing action word, require the project to
pass the ordinary note evidence bar as well. Query scoring already excludes those action
words. Calibrated routing uses calibrated evidence; word-only routing uses the existing
absolute floor. Explicit project names and aliases retain their existing behavior.
This adds no vocabulary, numerical threshold, provider call or configuration requirement.

## Verification

- Six focused tests cover unrelated commands, explicit names, action-word aliases, real
  entities in descriptions, subject-supported work and calibrated evidence versus rank.
  The unrelated-command test reproduced three false project matches before the change.
- All 180 frozen packets are byte-for-byte unchanged. No golden output was accepted anew.
- Aggregate counts are unchanged across all ten generated Brains, four demos and the
  read-only enriched private snapshot. This includes needed recall, whole-note recall,
  reachability, precision, off-topic behavior and false-empty packets.
- The first draft simply excluded inferred commands. A subject-recognition test and a
  demo regression exposed a valid project match it lost; the independent subject check
  preserves that behavior. The existing expected outputs were not changed to accommodate it.
- Full local Windows and Linux CI are required on the committed revision before merge.
  Native macOS execution is unavailable and is not claimed.

## Scope and limits

This fixes a demonstrated source of unrelated project context. It does not improve the
headline retrieval counts or establish production readiness. In the enriched private
snapshot, needed recall remains 72/88, whole-note recall 70/88, reachability 82/88,
delivered precision 106/158, correct generic off-topic abstention 93/100 and false-empty
packets 2/63. The broader quality and scale targets remain open.

Existing labels, fixtures, numerical gates, budgets and pointer limits are unchanged.
Previously inspected evaluation sets are regression evidence, not fresh held-out proof.
No private text or identifiers are included in this report. No private model calls were
needed for this fix, and the owner's real Brain was not used or edited.
