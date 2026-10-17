---
id: status-page-update-cadence
title: Status page update rhythm during incidents
summary: Since 2026-07-09 support posts status updates every 30 minutes in a Sev 1 and every 60 in a Sev 2, the first within 15.
area: incidents
topic: summaries
kind: decision
scope: company
status: approved
load: on-demand
added: 2026-07-09
source: Priya Raghavan, in conversation
supersedes: none
asked_as:
  - How often do we post updates during a major outage?
  - How soon after a page does the first status post go up?
  - Nothing new to report, do we still update the status page?
  - Who writes the status updates during an incident?
  - What's the update rhythm for a Sev 2?
  - Draft a status page update for an ongoing outage
applies_when: Posting status page updates while an incident is ongoing.
not_when: The write-up after an incident is resolved.
role: rule
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 90c8c3e3ec742e51
---
Decided 2026-07-09 after the 7 July payments outage, when customers sat through two hours of silence. During a Sev 1, support posts a status page update every 30 minutes even if nothing changed; during a Sev 2, every 60 minutes. The first post goes up within 15 minutes of the page. Support owns the wording and engineering confirms the facts before it goes up.
