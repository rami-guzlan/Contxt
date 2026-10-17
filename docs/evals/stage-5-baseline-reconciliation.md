# Stage 5 baseline reconciliation

The recorded stage-5 baseline was valid, but its calibration inputs changed after it was
measured. This was not a floating-point discrepancy or evidence of a stage-5 ranking regression.

## Provenance

- `c9373cb87ed93c955c33ce0bf36d9f4fb1147f0b` recorded the floors on October 17 at
  00:01 EDT, using the original **277** calibration requests.
- `5d87b81` subsequently added **15** everyday requests to stage 1 at 00:18 EDT.
- The stage branches were rebased onto that change. `2a493e0` retained the old floor values
  but now used **292** calibration requests. It is the rebased commit, not the original
  measurement tree.
- Replaying the actual original tree reproduced **every recorded quick-set rate exactly**
  after rounding to the existing three decimal places. Replaying that same tree with only
  the expanded bank reproduced the dental decline. Model files, labels and ranking code
  were held constant in this comparison.

| Same historical code and fixtures | Dental reachable | Separate off-topic set: correctly empty | Must-hold decoys |
| --- | --- | --- | --- |
| Original bank, 277 requests | 38/43 (88.4%) | 95/100 | 54/66 |
| Expanded bank, 292 requests | 36/43 (83.7%) | 96/100 | 52/66 |

The expanded bank changed the calibration distribution. Its lower reachable recall is real;
it is not erased or described as a retrieval improvement. The added requests remain in the
production bank. Broader precision, recall and must-hold quality targets remain future work.

## Required gates

Both gates run in `test_general_eval.py` with the actual meaning model:

1. **Historical stage 5:** preserve every value in `minimums.json`, including dental 0.884,
   against the original bank stored as `calibration-bank-277.txt`.
2. **Shipped bank:** independently gate all six Brains and all measured quality dimensions
   against the same original measurement tree (`c9373cb`), replayed with only the actual
   292-request production bank substituted. These values are in `minimums-current-bank.json`.

The second baseline isolates the input change on the immutable original reference code. It
was not fitted to candidate results. The existing 0.03 arithmetic allowance is unchanged for
both gates. No labels,
ranking weights, evidence thresholds, pointer limits or original quality floors changed.
A required metric with no denominator now fails instead of silently skipping the check.

`baseline-inputs.json` records source commits, the evaluation clock, calibration and fixture
fingerprints, model revision and hashes of all five model/tokenizer artifacts. Tests reject
changed inputs before comparing scores. The historical bank override is confined to its
test; the shipped-bank test reads the production bank without an override. Neither uses
private Brain data or generation models.

Run the model CI command with `BRAIN_TEST_MODELS` pointing to the downloaded model cache:

```text
uv run pytest packages/brain/tests/test_semantic.py apps/server/tests/test_captures.py packages/brain/tests/test_general_eval.py packages/brain/tests/test_calibration.py packages/brain/tests/test_enrich.py
```

The tests freeze October 16, 2026 at 12:00 UTC for both baselines. Normal tests also validate
the fixture and calibration identities without a model. Reproduce a changed input on both
the immutable reference and candidate before adding a new gate. Retain previous gates and
their inputs; do not run `--minimums` over an existing floor file to make a failure pass.
Retain per-request results for synthetic fixtures and aggregates only for private Brains.

## Cache correctness

Calibration caches previously recorded the note count, model name and domains, but not the
request bank. An upgraded Brain could therefore keep the old calibration while a fresh Brain
used the new one. Calibration now stores the fingerprint of the effective bank and rebuilds
when it changes. Legacy caches without that identity rebuild once. For large Brains the
fingerprint covers the existing sampled bank, preserving the current sampling policy.

Two synthetic regression tests first failed on the old implementation and now cover a
same-size bank replacement, legacy-cache migration and reuse of an unchanged cache. This
fix changes cache validity, not the scoring formula or any threshold.

## Limits of this reconciliation

These are stage-5 regression gates, not proof that stage 5 improves every measure over
stage 4. An additional replay of pre-stage-5 main (`54462e2`) with the shipped bank found
dental whole-note precision of 26/36 (72.2%); the stage-5 candidate produces 25/37 (67.6%).
Reachable recall is 36/43 in both. This precision tradeoff is reported, not tuned away or
used to choose ranking parameters. The original stage-5 precision floor remains 0.694 and
its established 0.03 allowance remains in force. A broader product-quality release still
needs the validation and sealed-Brain gates in the general retrieval plan.
