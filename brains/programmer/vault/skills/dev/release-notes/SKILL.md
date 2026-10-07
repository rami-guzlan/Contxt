---
name: release-notes
description: Write release notes for tidyq from the merged pull requests since the last tag.
triggers:
  - write release notes
  - changelog for tidyq
  - release notes
aliases:
  - changelog
artifacts: []
loads:
  - topics/tidyq
  - references/tidyq-design.md
quality_gates:
  - breaking changes first
  - one line per change
scope: person:kai
---
# /release-notes

Write release notes for tidyq from the merged pull requests since the last tag.

1. Get the list with `git log --merges --oneline <last-tag>..HEAD` or the pull request titles
   provided.
2. Group them: breaking changes, new features, fixes, documentation.
3. One line each, in the imperative, naming the user-visible change, with the pull request
   number.
4. Breaking changes come first, each with a migration note.
5. Return Markdown for the GitHub release. Publishing the release waits for Kai.
