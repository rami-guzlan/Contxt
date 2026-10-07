---
name: debug-playbook
description: "Work through a bug step by step: reproduce, test, hypothesize, fix."
triggers:
  - help me debug
  - debug this
  - why is this failing
aliases:
  - debugging
artifacts: []
loads:
  - practices/testing
quality_gates: []
scope: person:kai
invocation: explicit
---
# /debug-playbook

Work through a bug with Kai step by step.

1. Reproduce it: the smallest input that fails, and the exact error.
2. Write that as a failing test before changing anything.
3. Form one hypothesis at a time and test it with a print, a breakpoint or a log line.
4. Fix the cause, not the symptom; keep the test.
5. Remove every temporary print and log line.
6. Summarize: the cause, the fix, and how to stop it happening again.
