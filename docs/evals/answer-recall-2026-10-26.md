# Answer recall: what reached the AI by the end of its answer (Oct 26, 2026)

v4 backend plan, section 16.4. The lead number is no longer what the first packet holds. It is
whether every needed item reached the AI by the end of its answer, from its packets plus what it
fetched.

## How it is measured

`scripts/answer_recall_eval.py` (scoring in `brainkit/answer_recall.py`):

- Each generated Brain (`packages/brain/tests/evals/general`) runs on a scratch copy, the way a
  new person's Brain starts (zero-config), with its startup files written.
- Every labeled request goes to Claude Code headless (Haiku), in the Brain's folder, with only
  the Brain's MCP server. Retrieval is words only, as in the operating eval.
- Code scores the transcript. No model grades.
  - **A packet:** what the Brain delivers for the AI's own `gnomon_get_context` request,
    worked out again on the same Brain, counted as the retrieval eval counts it. Its notes,
    held and standing items and must-holds count; pointers don't.
  - **A fetch:** a note opened without an error (`notes get`, `gnomon open`, `skills get`). A
    search hit alone is a pointer, not the note.
- **Answer recall:** needed items reached, out of needed items. **Complete:** requests where
  every needed item reached the AI.
- **Wrong must-holds:** must-holds not labeled for the request that reached the AI.
- Not measured yet: answer correctness by the Haiku grader (section 15). It comes with the
  final report (PR E).

## Baseline, before sections 16.1 to 16.3

| Brains | Answer recall | Packet recall | Complete | Fetches per answer | Wrong must-holds (answers) | Cost |
|---|---|---|---|---|---|---|
| Tuning (4) | 121/159 (76.1%) | 99/159 (62.3%) | 77/106 (72.6%) | 1.11 | 49/152 (32.2%) | $0.79 |
| Validation (3) | 95/123 (77.2%) | 71/123 (57.7%) | 64/84 (76.2%) | 1.30 | 31/114 (27.2%) | $0.58 |
| Owner's private Brain, as configured | 71/88 (80.7%) | 64/88 (72.7%) | 49/63 (77.8%) | 1.06 | not labeled | $0.38 |

Each answer reads about 93,000 to 104,000 tokens, almost all of it Claude Code's own cached
context. That puts a request at about $0.0055 on Haiku.

| Brain | Split | Answer recall | Packet recall | Fetches | Wrong must-holds |
|---|---|---|---|---|---|
| bistro | tuning | 34/42 | 25/42 | 1.24 | 7/38 |
| dental | tuning | 30/43 | 23/43 | 1.16 | 21/38 |
| lawfirm | tuning | 30/36 | 29/36 | 1.03 | 7/38 |
| teacher | tuning | 27/38 | 22/38 | 1.00 | 14/38 |
| contractor | validation | 27/41 | 23/41 | 1.16 | 8/38 |
| foodbank | validation | 41/50 | 27/50 | 1.53 | 11/38 |
| saas-support | validation | 27/32 | 21/32 | 1.21 | 12/38 |

The owner's private Brain is the final measure only. Its run stays on the owner's computer. Only these
counts are recorded, and it is never tuned on.

## What it shows

- Fetching already adds about 14 points on the tuning Brains (62% to 76%) and 20 on validation
  (58% to 77%), at about one fetch an answer.
- The goals in 16.4 are still open:
  - answer recall 95% or more;
  - 1.0 fetch or fewer per answer;
  - wrong must-holds under 15%.

## Where the missed items are

Words only, zero-config, tuning Brains (`F:` diagnostic, no model). Of the 61 needed items the
first packets missed:
- 44 are in the top eight of the request's own search;
- 11 are already listed under "Also relevant";
- none is one or two relation hops from what the packet holds. The generated Brains have no
  links, so a graph route can't help on them.

This is the reason PR B points at the request's runners-up.
