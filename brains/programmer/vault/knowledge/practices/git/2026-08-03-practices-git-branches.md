---
id: practices-git-branches
title: "Git: branches and commits"
summary: Never push to main.
area: practices
topic: git
kind: rule
scope: person:kai
status: approved
load: standing
startup_text: Never push to main or force push a shared branch; one branch per change.
added: 2026-08-03
source: Kai Tanaka, in conversation
supersedes: none
---
Never push to main. One branch per change, named feature/<short-name> or fix/<short-name>. Commit subjects are imperative and under 60 characters; the body says why. Never force push a shared branch.
