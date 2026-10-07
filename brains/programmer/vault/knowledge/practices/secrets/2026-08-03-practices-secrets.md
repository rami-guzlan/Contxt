---
id: practices-secrets
title: Secrets stay out of code and chats
summary: Never put secrets, tokens or customer data in code, tests, logs, commits or chats.
area: practices
topic: secrets
kind: rule
scope: person:kai
status: approved
load: standing
startup_text: Never put secrets, tokens or customer data in code, logs, commits or chats.
added: 2026-08-03
source: Kai Tanaka, in conversation
supersedes: none
---
Never put secrets, tokens or customer data in code, tests, logs, commits or chats. Local secrets live in .env files that git ignores; shared ones in the team's secret manager. If a secret is exposed, say so at once: it gets rotated, not hidden.
