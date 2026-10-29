# Retrieval ablation, October 29, 2026

Step 8 of the simplification plan asked which retrieval stages earn their place: each one
switched off on its own against the full pipeline, and a minimum pipeline (a hybrid words and
meaning score, the top three notes whole, the next five as pointers, one calibrated bar for
"nothing") against both. Engine at 0711400 (release 0.1.0), zero-config, by meaning
(bge-small-en-v1.5), with `scripts/general_eval.py` on the tuning and validation Brains, the
four demos and the private Brain (numbers only). Rates are pooled over each split's requests.

## What each stage is worth

Points against the full pipeline when the stage is off (validation split, then the private
Brain). Recall is needed notes sent whole; reachable adds those listed, one `notes get` away.

| Off | Recall | Reachable | Precision | Off-topic: nothing | Must-hold recall | Must-hold decoys | Private reachable | Private precision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Calibrated bars (stage 1): the hand floors instead | +17 | -6 | -22 | -20 | -7 | -6 | +1 | -11 |
| Standing out from the rest of the Brain (stage 2) | -3 | 0 | -3 | 0 | -4 | -2 | -1 | +1 |
| Enrichment at the door (stage 3) | -10 | -6 | -11 | +1 | -7 | -5 | 0 | 0 |
| A strong match by meaning alone | +2 | -2 | +2 | 0 | 0 | 0 | -1 | +1 |
| The topic's own match, as a prior | -1 | -2 | -1 | 0 | 0 | +1 | -1 | -1 |
| Close calls sent as pointers (section 16) | 0 | 0 | 0 | 0 | +7 | +7 | 0 | 0 |
| Refilling pointer slots with other areas | 0 | 0 | 0 | 0 | 0 (tuning -3) | 0 | 0 | 0 |
| Newer dated values first | 0 | 0 | 0 | 0 | 0 | 0 | 0 | +2 |
| Freshness and rule lifts, linked notes, project context, per-topic caps | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 to +3 |
| Everything above off at once | +27 | 0 | -34 | -19 | +19 | +5 | -1 | -10 |

The private Brain has no enrichment fields, which is why enrichment moves nothing there.

Learning from use (stage 4) is measured apart (`--learning`): requests asked before gain 8 to
26 points of reachable recall on five of seven Brains (contractor 65% to 91%, dental 78% to
100%), and the other half of the requests do not move.

## The minimum pipeline

| | Recall | Reachable | Precision | Off-topic: nothing | Must-hold decoys | Private recall | Private reachable | Private precision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full (today), tuning | 49% | 89% | 78% | 96% | 19% | 60% | 89% | 64% |
| Full (today), validation | 49% | 84% | 77% | 95% | 24% | | | |
| Minimum, tuning | 73% | 91% | 64% | 96% | 20% | 68% | 83% | 66% |
| Minimum, validation | 64% | 84% | 57% | 95% | 27% | | | |

The minimum sends more notes whole and holds reachability on the generated Brains, but loses
14 to 20 points of precision and 6 points of reachability on the private Brain, outside the 2
points the plan allowed.

## Decision

- Every measured stage keeps its place: calibration is the one bar for "nothing" (without it
  the off-topic set gets something a fifth of the time), enrichment and learning carry recall,
  close calls carry must-hold precision. Meaning alone is a small trade (precision for
  reachability) and stays.
- The minimum pipeline is not adopted: it costs the private Brain 6 points of reachability.
- The lifts and caps with no measured effect here (freshness, rules, links, project context,
  per-topic caps) act on what these Brains do not have (dated notes, linked notes, projects,
  hand topics): they are product behaviors, kept.
- What Step 8 changes is speed, with no change to any result (see below).

## Latency

Similarity to every note is now one matrix product instead of a Python loop over each note's
vectors (the same values, to 12 decimal places), and the router keeps what is fixed while a Brain does not
change (its calibrated bars, its dated notes) instead of working it out per request.

Past scoring, a large Brain carries its best 400 candidates (`router.RANK_LIMIT`) and every
later note a declared topic, the house style, the owner's taste or an intent needs: selection
takes from the top of the ranking, and the rest only cost time. A Brain of 400 notes or fewer
is untouched, so every result above is unchanged.

A brief on a 5,000-note Brain, 76 requests, the Python thread's own CPU time (this computer was
busy with other work, so wall time swung by a factor of two between runs; two runs each):

| | p50 | p95 |
| --- | --- | --- |
| 0.1.0 | 125 ms | 188 to 219 ms |
| Now | 47 to 62 ms | 125 to 141 ms |

The rest of a large Brain's brief is mostly Python work per candidate (each note's score and its
reasons), the request's match to every topic, and the session ledger's writes.
