# 4. A pull-based task bus with leases, fencing and idempotency

Date: 2026-09-28. Status: accepted.

## Context

Models run on their own platforms and schedules. The server owns task intent and exposes only
work that is due; it must prevent duplicate work and silent overwrites without becoming a
distributed scheduler (spec sections 09 and 10).

## Decision

- **Assignment is the queue.** A task has one assignee; `get_due_tasks` returns only the
  caller's ready tasks whose due time has come and whose dependency is done.
- **A claim is a run with a lease.** Claiming moves the task to `claimed` with a conditional
  update (first valid claim wins, the second gets a conflict) and creates a run whose lease
  expires unless renewed by a heartbeat. The worker returns expired runs' tasks to `ready`.
- **The run id is the fencing token.** Writes name their run; once the run ended or its lease
  ran out they are refused with `LeaseLost`, even before the sweeper runs.
- **The packet is frozen at claim time** and stored on the run: pinned input versions, the
  Brain context, the prompt version. Artifacts copy the input versions into their lineage.
- **Idempotency keys** on claims, run events, artifacts, approvals and completions: a retry
  returns the first result; reusing a key for a different request is refused.
- **Recurring tasks** complete a cycle (`done`) and come due again at their next occurrence;
  missed occurrences are skipped, never piled up. Each occurrence starts at attempt 1.
- **Review settles the task.** With a required review, completing a run opens an approval for
  every unreviewed artifact (or for the run itself); decisions then move the task to done,
  back to ready with the reviewer's note, or to failed.

## Consequences

Any MCP-capable platform can do the work with one scheduled prompt. Correctness does not
depend on the prompt: the server refuses what the rules do not allow.

## Since ADR 0006

The bus's work is now the AI work the app starts (finding what to remember in a note,
reconciling a clash), with auto review. Artifacts and approvals remain in the bus for work with
a required review, but no page shows them and no MCP tool creates them.
