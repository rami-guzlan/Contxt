---
id: paging-oncall-engineer
title: Paging the on-call engineer
summary: Check severity, page tallyline-core in PageRelay with ticket links, open an incidents thread, and post the holding macro.
area: incidents
topic: oncall
kind: procedure
scope: company
status: approved
load: on-demand
added: 2026-06-24
source: Owen Pritchard, in conversation
supersedes: none
asked_as:
  - Invoices are failing for lots of customers, who do I page?
  - How do I page engineering?
  - Is this outage a Sev 1 or Sev 2?
  - What info goes in the page?
  - It's after hours and payments are down, who else do I call?
  - What do I put on affected tickets during an incident?
applies_when: Raising a Sev 1 or Sev 2 incident with the on-call engineer.
not_when: Lower severity bugs, or how the engineering rotation is set up.
role: procedure
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 49d687f97915839f
---
1. Check severity. Sev 1 means many customers cannot send invoices or take payments; Sev 2 means one major feature is broken for a group, such as bank feeds for one bank.
2. Page the tallyline-core service in PageRelay with ticket links and how many customers are affected.
3. Start a thread in #incidents with the same details.
4. Put the INCIDENT: Sev 1 holding reply on affected tickets and tag them with the incident ID.
5. Outside business hours, phone Priya too.
