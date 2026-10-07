---
id: practices-code-style-types
title: Types, names and small functions
summary: Type every function signature.
area: practices
topic: code-style
kind: rule
scope: person:kai
status: approved
load: standing
startup_text: Type every signature, prefer pure functions, names say what, comments say why.
added: 2026-08-03
source: Kai Tanaka, in conversation
supersedes: none
---
Type every function signature. Prefer pure functions and dataclasses over classes with state. Names say what a thing is for, not how it works. Comments explain why, never what. No print debugging left in a commit.
