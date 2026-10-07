---
id: work-architecture
title: How the routing services talk
summary: The dispatcher UI calls the route planner over REST.
area: work
topic: architecture
kind: fact
scope: person:kai
status: approved
load: on-demand
added: 2026-08-14
source: Kai Tanaka, in conversation
supersedes: none
---
The dispatcher UI calls the route planner over REST. The planner reads orders from PostgreSQL and publishes route events to Kafka; the events pipeline turns them into driver notifications. The planner still shares a database with the old monolith; splitting it out is the current migration project.
