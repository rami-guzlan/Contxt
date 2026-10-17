# Progress intent, October 17, 2026

An approval phrase such as "is approved" used to classify a question or writing request as
a new project update. "What budget is approved for the workshop?" could therefore instruct
the caller to record progress rather than answer the question. The classifier now separates
questions, read requests and artifact production from reports of new progress. Explicit
recording instructions, including polite questions, retain the update path.

The regression suite first reproduced nine misclassifications. Twelve read/drafting cases and
nine progress/recording cases now pass, including short reports that name an existing artifact.
Existing routing tests, mandatory-rule and retrieval
floors, and all 180 golden briefs pass without changing snapshots, labels or numerical gates.

The frozen comparison covers ten generated Brains, four demos and the enriched private
copy, with the same meaning model, UTC clock, cases and 100 off-topic requests per Brain.
Every measured aggregate count is unchanged across all 15 Brains. The private copy retains
72/88 needed hits, 70/88 whole-note hits, 82/88 reachable hits, 106/158 precision counts,
93/100 off-topic abstentions and 2/63 false-empty cases. The private source fingerprint is
unchanged. These are regression results, not evidence that remaining quality targets pass.

A separate real Haiku 5.5 test on a fictional capture successfully produced a digest and five
reviewable, source-backed proposals, then approved them on the disposable Brain. It exposed
this intent error and a second issue: ordinary factual project questions can still take the
project-overview shortcut and miss approved notes. A proposed broader correction failed the
existing precision and mandatory-rule gates and is not included. Multi-part full-note
coverage also remains incomplete. No model verifier or paid request-time call is enabled.

Complete local Windows and Linux CI is required before this patch merges. macOS is not
available on this host. The PR records the exact tested commit and local check results.
