---
id: charge-only-within-grant-terms
title: Which grant a purchase may go on
summary: A cost goes only on a grant whose dates and aims cover it, and costs never move between grants without research finance.
area: grants
topic: budgets
kind: rule
scope: company
status: approved
load: domain
applies_to: grants/budgets
must_text: Charge a purchase only to a grant whose dates and aims cover it, and never move costs between grants without research finance (Freya Lund) agreeing in writing first.
added: 2026-06-01
source: Freya Lund, in conversation
supersedes: none
asked_as:
  - Which grant should pay for this cell culture order?
  - Can I put fish food on KF since it has more money left?
  - Can we move this invoice to another account afterwards?
  - The grant ends soon, can I buy reagents to use next year?
  - What do auditors check on our purchases?
  - Who needs to approve shifting a cost between grants?
  - Pick a budget code for this purchase
applies_when: Choosing which grant pays for a purchase or moving a cost between grants
not_when: Checking how much money is left on each grant
role: rule
suggested_triggers:
  - grant code
  - charge to
  - budget line
  - cost transfer
  - which account
  - invoice
  - purchase order
  - spending out
  - audit
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: f3f4fade9e91c85f
---
Auditors check every cost against the grant's period and aims, so cell culture reagents go on KF-2024-031 and fish work on RRC-22-4410, never on whichever account happens to have money left. Goods must arrive and be used before that grant's end date. Shifting a cost to another grant after the fact is a cost transfer and needs Freya Lund's written agreement; Elena got caught out by this once and will not do it informally again.
