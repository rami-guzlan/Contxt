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
"Also relevant", to open with `notes_get`. Writing tasks start with the owner's core style
rules (`house_style_notes`). Topic caveats (`with_notes`) travel with their topic's notes.

MUST-HOLDS (`load: domain`) are constraints that go into every brief whenever their domain is
in play, whatever their relevance, the note budget, the per-topic caps or how stale they are
(stale ones are flagged, never ranked down). A domain is in play when the request uses one of
the note's `triggers`, when the route already reached one of its `applies_to` areas, topics or
projects, when one of those topics is among the request's best topic matches, or (with an
embedding model) when the request is close in meaning to the must-hold's domain. They open
every packet under "Must hold", one line each (`must_text`), in every packet of a
conversation, and are listed past `must_hold_max`. Measured with
`scripts/safeguards_eval.py`.

DATED VALUES. A note can say the day a changing value was true (`as_of`) and the last day it
holds (`valid_until`; past it, the note is stale). When two dated notes (an `as_of`, or state
notes) give different values for the same thing, the packet carries the newest, labelled "as
of", and lists the older under "Older values (not current)" by name and date (`older_ids`).
A question about a project also gets the project's newest dated values close to what it asks.

Tune by editing content, never code: note titles and summaries, topic lines in `topics.md`,
hints, intents and caveats in `routing.json`, skill `triggers`/`aliases`/`loads`. Measure
with `brain bench`: context usefulness from `eval.json` (must, useful and noise
notes per request, with held-out cases) and behavior checks from `benchmark.json`.
