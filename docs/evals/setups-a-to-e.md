# Retrieval setups A to E (brain-logic plan 5.11.11)

Measured on the PC on October 12, 2026 (build step 9), on the public demo set: 48 labeled
requests on the four demo Brains (14 held out, 8 that should get nothing) and the must-hold
decoys, with bge-small in the find step. The cuts were chosen on the tuning part
(`scripts/fit_cuts.py`); the held-out part was read once. The PC is a GTX 1060 with 6 GB
(Pascal), a Ryzen 7 9700X and 62 GB of RAM, so `machine.py` reads it as the laptop setup. It ran
the laptop setup twice:

- **With its small GPU**: Qwen3-Reranker-0.6B and Kev-0.8B on the GPU in fp16.
- **As a laptop without a GPU**: every model on the CPU (`BRAIN_MODEL_DEVICE=cpu`), where the
  setup's reranker is MiniLM.

Qwen3-Embedding-0.6B is not in these tables: the engine has no meaning-index backend for it yet.

## With a small GPU (GTX 1060, 6 GB)

Relevance cut 0.02, gate cut 0.5 (the default). Setups C to E run Kev-0.8B's steps whether or
not it has qualified, since they are how it qualifies.

| Setup | Held-out recall | Recall | Noise | Decoys | Correct nothing | False nothing | Tokens | Brief ms p50 / p95 (warm) | Gates missed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 92% | 85% | 0% | 2% | 88% | 10% | 245 | 53 / 290 | decoys, correct nothing, false nothing |
| B | 83% | 75% | 0% | 2% | 100% | 15% | 236 | 894 / 1350 | held-out recall, decoys, false nothing |
| C | 33% | 25% | 0% | 2% | 100% | 85% | 84 | 1079 / 2069 | held-out recall, decoys, false nothing |
| D | 33% | 25% | 0% | 9% | 100% | 85% | 90 | 1657 / 3445 | held-out recall, decoys, false nothing |
| E | 92% | 85% | 1% | 2% | 12% | 8% | 530 | 7101 / 12320 | decoys, correct nothing, false nothing, tokens above setup A |

E ran before two fixes (Kev's steps and the goals notes, below) at the 0.5 relevance cut; it was
not run again, since Kev-0.8B keeps nearly everything as a relevance scorer and takes 7 s a brief.

The relevance cut on B, before the goals fix (tuning part): 0.02 gave 72% recall and 14% false
nothing, 0.05 gave 69% and 17%, 0.1 gave 69% and 21%, 0.5 gave 58% and 35%. Lower is better all
the way down: the reranker scores many needed notes near zero.

## As a laptop without a GPU (every model on the CPU)

MiniLM's relevance cut, on B (tuning part):

| Relevance | Tuning recall | Correct nothing | False nothing | Tokens | Brief ms p50 / p95 |
| --- | --- | --- | --- | --- | --- |
| 0.001 | 61% | 100% | 28% | 185 | 79 / 150 |
| 0.005 | 56% | 100% | 34% | 167 | 82 / 155 |
| 0.02 | 56% | 100% | 34% | 162 | 90 / 160 |
| 0.1 | 50% | 100% | 41% | 150 | 94 / 181 |
| 0.2 | 42% | 100% | 55% | 136 | 87 / 140 |

Chosen 0.001; held out, read once: 67% needed-note recall (over all requests 62% recall, 100%
correct nothing, 30% false nothing, 177 tokens). Kev-0.8B's gate on top (C, relevance 0.001):

| Gate | Tuning recall | Correct nothing | False nothing | Brief ms p50 / p95 |
| --- | --- | --- | --- | --- |
| 0.05 to 0.3 | 61% | 100% | 28% | about 825 / 930 |
| 0.4 | 36% | 100% | 66% | 786 / 870 |

## Each model's speed here

| Model | GTX 1060 | Ryzen 7 9700X (CPU) | Budget, Windows laptop |
| --- | --- | --- | --- |
| Qwen3-Reranker-0.6B, 50 short passages | 2.8 s (fp16, last-position logits) | 16 s (fp32) | 2 s |
| Qwen3-Reranker-0.6B, the cut in a real brief | 0.8 s p50, 1.3 s p95 | not run | 2 s |
| MiniLM, 50 note-sized passages | | 0.49 s | 2 s |
| Kev-0.8B, a gate request | 149 ms (fp16), 189 ms (bf16, emulated), 1978 ms (fp32) | 434 ms (fp32) | 600 ms |
| Kev-0.8B, ten second-pass questions | 356 ms (fp16) | 1727 ms | 1500 ms |
| Qwen3.5-4B (Q4_K_M), one short JSON answer | 2.6 s | 3.9 s | a background job |

## What this says

- **No setup clears every gate on the demo set.** By 5.11.11's rule (the fastest setup that
  clears every gate, a tie to the setup with fewer models), A stays the default here.
- **A small reranker is a poor relevance cut for this task.** Qwen3-Reranker-0.6B and MiniLM
  judge whether a passage answers a query, not whether an assistant needs it for a task. "What
  keeps plant managers up at night?" scored the needed `customers-pains` 0.001 (it says "our
  audience", never "plant managers"); "Plan dinners for next week" scored the needed `food-diet`
  0.002. Four instructions and three phrasings of the request changed neither. The cut buys
  perfect "correct nothing" with needed notes.
- **Kev-0.8B does not qualify here.** As a gate it gives most requests a yes between 0.3 and 0.5,
  so a cut either passes everything or blocks most real requests. As a relevance scorer (E) it
  keeps nearly everything.
- **Speed is not the problem.** On the GTX 1060 a brief with the reranker took 0.9 s at p50; on
  the CPU with MiniLM, 0.08 s; Kev's gate adds about 0.2 s on the GPU and 0.75 s on the CPU.

## Found and fixed on the way

- The engine routed notes loaded `manual` (the owner's goals) into briefs; the router never does.
  The real reranker scored a goals note 0.87 to 0.91 for requests it did not fit, so it reached
  their briefs. (The B row above is after the fix; the cut sweep before it.)
- The comparison could never qualify Kev: an unqualified model's steps fell back in the very runs
  that judge it. Its scratch Brains now run them (`engine.qualifying`).

## The development laptop's run (October 10, 2026)

No GPU and no verified model service, so only setup A ran (bge-small): held-out recall 92%,
recall 85%, noise 0%, decoys 2%, correct nothing 88%, false nothing 10%, 245 tokens, 60.8 / 163.0
ms (a CPU laptop's times).
