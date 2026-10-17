---
id: incident-summary-format
title: Writing up an incident afterwards
summary: Write-ups go out within 2 business days in a fixed order, with no engineer names, internal services or blame.
area: incidents
topic: summaries
kind: rule
scope: company
status: approved
load: on-demand
added: 2026-07-09
source: Priya Raghavan, in conversation
supersedes: none
asked_as:
  - Write the customer post-mortem for yesterday's outage
  - How long can the customer incident summary be?
  - Can I name the engineer who fixed it?
  - What time zone do incident times use?
  - When is the incident write-up due?
  - What extra goes in the internal version for Daniela?
  - Review this outage report for tone
applies_when: Writing up an incident after it is resolved, for customers or internally.
not_when: Live status page updates during the incident.
role: rule
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 0e2f285d09bc45fa
---
The write-up is due within 2 business days of resolution. Order: what happened in plain words, who was affected (how many accounts, which plans), start and end times in US Eastern, what we did, and what changes so it does not repeat. No engineer names, internal service names or blame. The customer version is 250 words at most; the internal version for Daniela adds ticket counts and a timeline.
