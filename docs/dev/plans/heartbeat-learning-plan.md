# Heartbeat learning and nightly distillation

Copied from section 14 of the v4 backend plan (outputs/plans/gnomon-v4-backend-plan.md, Oct 25, 2026), the owner's spec recorded as decisions. Built in five PRs: the ingest model (Haiku), buffer and capture, the distill, settings and UI, apply during the day.

The owner's spec, recorded as decisions against today's code. Today (#59, #61 to #64), each beat reads, then judges and writes in the same run (`heartbeat/service.py` `_run`, `judge_prompt`, `_write_all`). The change splits that in two:
- **Beats only capture.** Each change goes into a staging buffer.
- **A scheduled distill learns.** Nightly by default, it nets out the day's changes, routes them, and writes through the one proposal path. Governance, the always-wait categories and undo are unchanged.

## 1 Beats: capture only, no model calls

- **Reads stay as built:** batched CLI reads with a cadence per connector, n8n's token-free reads, Scout, and memory reads.
- **Each change goes into the buffer** with: source, item id, field, old value, new value, the time it changed, when it was seen, beat id, a relevance score, and the link to the item.
- **Relevance scoring is local and token-free,** per the Oct 24 decision not to add model calls to reads:
  - a meaning score against the goal, using the local meaning model, plus a words score;
  - negative filters are checked by code first (source, field, and words or patterns);
  - anything a filter clearly matches is dropped at capture and counted on the beat record;
  - anything unclear is kept, marked `filter?`, for the distill to judge.
- **Most beats cost nothing.** Only CLI reads spend tokens; the judge no longer runs per beat.

## 2 Staging buffer

- **Storage:** a `staged_changes` table in the app database. It's append-only during the day.
- **After a distill,** each entry is marked with its outcome (sheet, note, Catch up, discarded with its reason) and the proposal it became. It's archived, not deleted.
- **Kept 30 days, then removed** (a setting). The beat and distill records keep their counts, and receipts link to the archived entries while they exist.
- **Owner's view:** Heartbeat › Today shows what's waiting for tonight, grouped by source, with a filter reason on dropped items. "Forget this" removes an entry, and that counts as an undo signal.

## 3 The distill

- **Schedule:** nightly by default at the end of quiet hours' start (a setting); also "Distill now". If the PC is asleep, it runs at the next start.
- **Step 1, code:**
  - net change per (source, item, field): the first old value against the last new value;
  - equal means net-zero, and it's discarded as "undone the same day";
  - repeated edits collapse to one entry that keeps the edit count;
  - deletes win over earlier edits.
- **Step 2, one model call** (Haiku by default, the item 4 setting) over the netted set. It works in batches of about 60 items, each batch packed with:
  - the goal, the filters, and the Brain's alignment: the constitution, must-hold index, map and taste summary;
  - the relevant existing entries, found by the router.

  It returns, per item, one of the four routes, with a reason and a confidence. It also returns cross-item patterns, which become lesson proposals.
- **Step 3, routing rules applied by code:**

| Route | When |
|---|---|
| Short-term (context sheets, progress, tasks) | A value expected to change again: the field changed more than once this week, or it already lives in a sheet. Default for status, owner, dates and counts. |
| Long-term (notes) | A durable fact about the person's world: a person, an approval, how a project runs, a decision |
| Catch up | Model confidence under 0.7; conflicts with a kept entry or a must-hold; any always-wait category; `filter?` items the model can't settle |
| Discard | Net-zero; under the relevance bar; matched by a filter; a duplicate of what the Brain already holds |

- **Writes go through the existing `_propose` and `_write_all` checks:** scope, sealed, private, must-hold. Auto-governed writes go in with an undo point, as today.

## 4 Answers to the spec's open questions (proposed defaults)

| Question | Decision |
|---|---|
| How the distill routes | A model judgment against the Brain's alignment, with code rules for netting, conflicts, confidence (0.7) and always-wait categories |
| Scope of goals and filters | One global goal and global filters, overridable per connector. There is only one heartbeat, so nothing per beat |
| Unreviewed Catch up items | They stay. A later net change on the same item replaces the waiting one. After 14 days they're marked stale and gathered into one "still waiting" card; nothing expires silently |
| Is the buffer kept as an audit log | Yes, archived for 30 days with each outcome (14.2) |
| Check against alignment too | Yes: the distill packs the constitution, must-holds and taste with the goal, so a goal can't pull the Brain off its own rules |

## 5 Freshness

Nightly means a fast-changing value (an account's health, a deadline moved this morning) reaches the Brain tomorrow.
- **Option:** "Apply during the day," per connector or per sheet. Changes that net to a sheet cell are distilled in the beat that captured them, with code netting and a small Haiku call only on beats with such changes.
- **Default:** off for everything except sheets the owner marks live.
- The packet labels sheet values with their last update, so an AI knows a value may be a day old.

## 6 Settings

- Connected sources (as today).
- Beat interval (5, 15, 30 or 60 minutes, as today).
- Goal (plain language, with a per-connector override).
- Negative filters (a list, with a per-connector override).
- Distill schedule (nightly at a set time, or every N hours).
- Distill model (Haiku by default).
- Apply-during-the-day list.
- Buffer retention (30 days).

## 7 Tests and evaluation

- **Tests first** for each rule:
  - net-zero is discarded;
  - repeated edits collapse;
  - a delete wins;
  - a code filter drops at capture;
  - an unclear filter match goes to the distill;
  - a conflict and an always-wait category go to Catch up;
  - a stale card appears at 14 days;
  - a later change replaces a waiting item;
  - the distill resumes after the PC sleeps;
  - the buffer is archived, not deleted.
- **A recorded day:** a fixture of about 80 changes across 4 sources, with undos, churn, filtered items and three cross-item patterns. Each change's correct route is labelled before tuning.
  - Score route accuracy, net-zero caught, filter precision, and tokens per distill.
  - Ship gates: route accuracy at least 85%; no must-hold or always-wait item written without review; tokens per distill no more than the median beat judge cost today multiplied by beats with news per day.
- **One real night** on a scratch Brain, with the owner's say-so before any real account is read (item 2's rule).

## 8 Risks

| Risk | What stops it |
|---|---|
| Learning lags a day | Apply-during-the-day for marked sheets; packets show each value's age |
| A big buffer makes the distill expensive | Batches of about 60; capture-time drops; a cap per night with the rest carried to the next distill and the owner told |
| A filter drops something the owner needed | Dropped items stay visible in Today and the archive for 30 days, with "Bring back" |
| A goal drifts from the Brain's rules | The alignment pack in every distill; always-wait categories unchanged |
| Net change hides a meaningful intermediate state | The edit count is kept; the model sees counts and may propose a lesson ("changed 5 times today") |
| Distill fails overnight | It resumes on the next start; the buffer is untouched until outcomes are written; the run's record says what was done |
