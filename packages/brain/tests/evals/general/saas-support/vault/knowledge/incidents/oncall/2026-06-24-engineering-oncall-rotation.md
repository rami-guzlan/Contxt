---
id: engineering-oncall-rotation
title: How engineering on-call is set up
summary: Five engineers rotate weekly with a Tuesday 10:00 handover; Owen Pritchard steps in if a page goes unanswered for 15 minutes.
area: incidents
topic: oncall
kind: fact
scope: company
status: approved
load: on-demand
added: 2026-06-24
source: Owen Pritchard, in conversation
supersedes: none
asked_as:
  - Who's on call for engineering this week?
  - Nobody picked up the page, who do I call?
  - When does on-call hand over?
  - Should I page for a minor bug?
  - Where can I see the current on-call engineer?
  - How many engineers share the rotation?
applies_when: Finding out who is on call or what to do when a page goes unanswered.
not_when: The steps for paging during an incident.
role: pointer
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 90204d5f8b8fa968
---
Engineering on-call rotates weekly among 5 engineers, with the handover on Tuesday at 10:00 US Eastern. Who is on shows in PageRelay and in the #incidents channel topic. If nobody acknowledges a page within 15 minutes, call Owen Pritchard, engineering manager. Support never pages for Sev 3 or Sev 4; those go through the normal bug flow.
