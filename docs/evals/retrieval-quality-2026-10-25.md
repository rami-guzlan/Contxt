# Retrieval on a Brain with no setup, October 25, 2026

Item 1 of the pre-testing list: zero-config retrieval toward 90% held-out reach and 80% precision, with fewer look-alike must-holds. Measured by meaning (the CPU index) at main 9ac2654, on the generated Brains:
- **Tuned on:** the 4 tuning Brains only.
- **Checked once:** the 3 validation Brains, once per candidate.
- **Not used:** the IKN, demo and sealed sets were not tuned on.

## What ships in this PR (owner approved, Oct 25)

1. **Only the best note goes whole.** Notes close to it are listed by name as pointers (`whole_relative` 0.90 to 1.0).
2. **Must-holds by meaning are judged against the request's best note.** A must-hold's domain is in play by meaning only when its similarity is at least 0.90 of the request's best note match (`must_hold_relative`). A domain clearly less like the request than its best note is another part of the same Brain's work.
3. **General CI floors.** The quick set runs every tuning Brain and holds the aggregate and the worst Brain, the same for every Brain, naming none (scripts/quick_floors.py). This replaces the per-Brain floors.

| Validation (3 Brains), checked once | Today | With this PR |
| --- | --- | --- |
| Reach | 83.7% | 83.7% |
| Precision | 72.8% (worst 69.0%) | 77.3% (worst 72.4%) |
| Look-alike must-holds | 41.8% | 38.3% |
| Must-hold recall | 74.1% | 74.1% |
| Needed note sent whole | 56.9% | 48.8% |
| Off-topic gets nothing, false nothing | 95.3%, 2.4% | unchanged |

**The cost:** fewer needed notes go whole, so an AI opens a pointer more often. The owner accepted this for precision.

## Measured but not shipped

- **Twelve pointers instead of eight.** Reach on tuning went from 89.3% to 92.5%, but on validation look-alike must-holds rose to 47.8%, so it is dropped.
- **Raising the fixed must-hold meaning bar** from 0.57 to 0.70 moved look-alike must-holds by under 2 points. Most of them come in through trigger words and topics the packet already reached.

## Still open

- **Reach 90% held out:** validation is at 83.7%. Most misses are needed notes ranked below the first 8, or under the related bar. Listing more names reaches them but brings in their domains' must-holds, so the fix is better ranking, not looser bars.
- **Precision 80%:** 77.3% on validation. What remains is mostly:
  - requests that need nothing specific but get a weakly matching note;
  - a wrong best note.
  A cross-encoder rereading the top candidates is next, in its own PR.
- **Look-alike must-holds:** 38% on validation. They come mostly through trigger words and reached topics.
