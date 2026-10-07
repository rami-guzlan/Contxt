---
name: code-review
description: Review a diff against Kai's checklist and report findings by severity.
triggers:
  - review this diff
  - review my pr
  - code review
aliases:
  - review
  - pr review
artifacts: []
loads:
  - practices/reviews
  - practices/code-style
  - practices/testing
  - practices/secrets
quality_gates:
  - every finding has a file and a fix
  - tests checked
scope: person:kai
---
# /code-review

Review a diff the way Kai does, and report findings by severity.

1. Read the ticket or the stated goal first; then the diff.
2. Go through the checklist in order: behavior, error paths, tests, names, secrets in logs,
   leftovers from debugging.
3. For each finding give the file and line, what is wrong, and the smallest fix.
4. Group findings as must fix, should fix, and nit. Say plainly when there is nothing to fix.
5. Never approve a change without tests for new behavior.
