# Retrieval setups A to E (brain-logic plan 5.11.11)

Run on the development laptop on October 10, 2026, with `scripts/engine_compare.py --models
<bge-small>`: no GPU and no verified model service, so only setup A (today's retrieval) ran.
Setups B to E, and the Qwen3-Embedding variants, run on a PC with an NVIDIA GPU or an Apple
Silicon Mac once the models are pinned, and the private set is labeled; the winner sets the
defaults and the cuts. Times here are a CPU laptop's, not the reference machines'.

| Setup | Find | Held-out recall | Recall | Noise | Decoys | Correct nothing | False nothing | Tokens | Brief ms p50 / p95 (warm) | Gates missed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | bge-small-en-v1.5 | 92% | 85% | 0% | 2% | 88% | 10% | 245 | 60.8 / 163.0 | decoys, correct nothing, false nothing |
| A | qwen3-embedding-0.6b | skipped: Qwen3-Embedding-0.6B needs a meaning-index backend the engine does not run yet | | | | | | | | |

No setup that ran clears every gate yet; the others need the models on a PC or Mac.
