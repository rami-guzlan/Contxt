---
id: weekend-bank-feed-bug
title: Open bug, weekend bank feed gaps
summary: State on 2026-10-09, feeds from two regional banks drop weekend transactions; P1, about 74 accounts, manual re-sync workaround.
area: product
topic: bugs
kind: state
scope: company
status: approved
load: on-demand
added: 2026-10-09
source: Tobias Lindqvist, in conversation
supersedes: none
asked_as:
  - Customer says Saturday transactions are missing from their feed
  - Is there a workaround for weekend transactions not syncing?
  - When will the bank sync bug be fixed?
  - Can I tell the customer when the fix ships?
  - How many customers are hit by the feed issue?
  - Draft a reply for someone with missing weekend deposits
  - What's the top open bug right now?
applies_when: Answering tickets about weekend transactions missing from bank feeds, or reporting on that bug.
not_when: Other bank feed problems such as reconnecting a feed or unsupported banks.
role: knowledge
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 4b1a471fd66aaca5
---
As of 2026-10-09 the biggest open bug is ENG-2291 (P1): bank feeds from two regional banks drop transactions dated on a Saturday or Sunday. About 74 accounts are affected. Workaround for customers: Settings, then Bank feeds, then Re-sync last 14 days. Leah expects the fix in the sprint ending 2026-10-23; that is internal only, not for customers.
