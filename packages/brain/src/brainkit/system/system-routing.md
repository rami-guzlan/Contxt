---
id: system-routing
title: How routing decides what goes in a packet
keywords: routing router retrieval precision recall topics notes skills intents hints relevance gap tuning evaluation
---
Routing is deterministic and explainable (`brain context "<request>" --explain`).
Order: exact address (note id, `/skill`), Focus portfolio, questions about the brain itself,
a named Focus (status, progress update, or work on it), then standard routing.

Standard routing scores every note the caller may see on its own: BM25 over its title,
summary and body plus similarity from a small local embedding model. Where a note is filed
only adds evidence: how well its whole topic matches the request, a lift when a fitting
skill, an intent or a named Focus declares its topic, `fit_terms`, and a lift for notes added
or approved in the last 14 days. So a note approved into a brand-new topic is used on the
next relevant request. Notes that stand out go in; the next ones are listed by title under
"Also relevant", to open with `get_note`. Writing tasks start with the owner's core style
rules (`house_style_notes`). Topic caveats (`with_notes`) travel with their topic's notes.

Tune by editing content, never code: note titles and summaries, topic lines in `topics.md`,
hints, intents and caveats in `routing.json`, skill `triggers`/`aliases`/`loads`. Measure
with `brain bench`: context usefulness from `eval.json` (must, useful and noise
notes per request, with held-out cases) and behavior checks from `benchmark.json`.
