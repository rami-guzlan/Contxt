# 5. The Brain stays files and git; private content never enters this repository

Date: 2026-09-28. Status: accepted.

## Context

The Brain started as a separate project whose repository held both the engine and one
organization's private knowledge. The product must be open source, and its history must never
contain a user's content.

## Decision

- The Brain engine is `packages/brain` (Python package `brainkit`), imported from that
  project at the point it reached parity. It stays generic: no organization, product or
  person is named in engine code, tests or docs; examples use the fixture brain of a small
  design studio.
- A Brain's content (the vault) is data. It lives outside this repository, versioned in its
  own git repository, and is mounted into the workspace by configuration
  (`CONTXT_BRAIN_VAULT`), exactly like the database and file store.
- The workspace reaches the Brain only through `BrainPort`: context for task packets, search,
  entries for pins, and proposals. Governance stays in the Brain: models propose, the owner
  (or an explicit policy) approves.
- The first public release is made from a fresh history of this repository.

## Consequences

Dogfooding with a real organization's Brain needs only a path in `.env`. The engine's earlier
history remains in the private project it came from.
