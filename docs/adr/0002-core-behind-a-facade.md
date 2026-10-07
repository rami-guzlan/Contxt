# 2. A pure core behind one facade; adapters translate

Date: 2026-09-28. Status: accepted.

## Context

The spec requires API parity ("MCP is an adapter, not a second source of business logic"),
provider integrations as adapters rather than domain logic, and a future hosted layer that
must not fork the domain model.

## Decision

`packages/core` holds the domain (records, state machines, schedules, permissions) and the
application services, reachable only through the `Workspace` facade. It imports no web
framework, model provider or Brain implementation. What it needs from outside is a protocol
in `ports.py`: `BrainPort`, `TextExtractor` and `Destination`. REST, MCP, CLI and the worker
are thin adapters over the facade.

Every service method takes the authenticated `Principal` first. Authorization, validation,
state transitions, the write and its domain event happen inside one transaction.

## Consequences

The same rules hold for the web UI, every MCP client and the worker, and are tested once, in
the core, without HTTP. A hosted edition adds accounts and tenancy around the facade instead
of changing it.
