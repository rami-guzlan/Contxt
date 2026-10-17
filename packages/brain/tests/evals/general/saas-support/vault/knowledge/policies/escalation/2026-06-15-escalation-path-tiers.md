---
id: escalation-path-tiers
title: How a ticket moves up the tiers
summary: Tier 1, then tier 2 by specialty, then engineering or Priya; every escalation is posted in the escalations channel.
area: policies
topic: escalation
kind: procedure
scope: company
status: approved
load: on-demand
added: 2026-06-15
source: Priya Raghavan, in conversation
supersedes: none
asked_as:
  - When should I hand a ticket to tier 2?
  - Customer mentioned a chargeback, who gets it?
  - Who takes integration problems?
  - Can I DM Marisol about an escalation?
  - This looks like a bug, how do I raise it to engineering?
  - Customer threatening to leave, what now?
  - Where do escalations get posted?
applies_when: Moving a ticket beyond tier 1 or flagging churn and legal risk.
not_when: Paging on-call for an outage.
role: procedure
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 1b876b39b2d71b2c
---
1. Tier 1 owns the ticket first.
2. If it is not solved in two replies, or it touches money movement, customer data or the API, use the ESCALATE: Tier 2 macro (Marisol for billing, Tobias for integrations and bank feeds).
3. Tier 2 opens an engineering ticket labelled support-escalation for a suspected bug; on-call is paged only for Sev 1 or Sev 2.
4. Churn threats or legal words (lawyer, chargeback, regulator) go straight to Priya.
5. Post every escalation in #support-escalations, never by direct message.
