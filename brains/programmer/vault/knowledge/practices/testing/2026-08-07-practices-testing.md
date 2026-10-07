---
id: practices-testing
title: Testing rules
summary: For a bug, write the failing test first.
area: practices
topic: testing
kind: rule
scope: person:kai
status: approved
load: on-demand
added: 2026-08-07
source: Kai Tanaka, in conversation
supersedes: none
---
For a bug, write the failing test first. The unit suite stays under 10 seconds; anything slower is marked integration and runs in CI. Test behavior through public functions, not private helpers.
