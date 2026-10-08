---
id: work-deploys
title: Deploy windows and rollbacks
summary: Deploy Tuesday to Thursday between 10:00 and 15:00 only.
area: work
topic: deploys
kind: rule
scope: person:kai
status: approved
load: domain
applies_to: work/deploys
triggers: [deploy, deploys, deployment, release, ship, shipping, hotfix, roll out, rollout, production, prod, go live, live, launch, promote, staging, rollback, push to production]
must_text: "Deploy Tuesday to Thursday between 10:00 and 15:00, never on a Friday; anything a customer sees ships behind a feature flag."
added: 2026-08-14
source: Kai Tanaka, in conversation
supersedes: none
---
Deploy Tuesday to Thursday between 10:00 and 15:00 only. Anything a customer sees ships behind a feature flag. Roll back with make rollback, then write up what happened. Never deploy on a Friday.
