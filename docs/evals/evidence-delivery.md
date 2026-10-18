# Evidence delivery

Search returns a matching source excerpt while retaining the summary in structured data.
The existing hit ranking, admission rules, count limits and context budgets are unchanged.
Short note excerpts preserve explicit conversation timestamps and speaker labels within
the existing word allowance. Lexical matching uses the engine's existing light stemmer.

Opening a note displays its recorded speaker and effective date when present. Approval
does not change authorship. The Brain MCP tools expose the existing scoped archive search
and allow explicit reads of an archived original. Normal reads still follow replacements;
historical reads opt in. These flags do not bypass scopes or partitions.

This fixes evidence presentation and access, not arithmetic or complete-set recall.
A title or short excerpt is a discovery aid, not proof of an entire note. Callers still
need to open sources, establish all operands before computing a total, distinguish a
previous fact from a current one, and report missing evidence. No local generative model
or new provider call is introduced into retrieval.

Validation uses fresh fictional dialogue and archived-note tests, the existing routing,
scope, session, dated-value and semantic gates, all generated/demo Brains, an offline copy
of the private Brain, and a separately frozen public sample. Historical benchmark data,
thresholds and original results are not rewritten.
