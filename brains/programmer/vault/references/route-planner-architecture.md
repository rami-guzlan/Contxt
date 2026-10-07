# Route planner architecture

## Today

The route planner is a FastAPI service. It reads orders from the monolith's PostgreSQL
database and writes planned routes back to it. It publishes a route.planned event to Kafka
for every plan.

## Target

The planner owns its own database: orders arrive as events, routes are stored locally, and
the monolith reads routes through the planner's API.

## Migration steps

1. Dual write routes to both databases behind a flag.
2. Backfill historical routes and compare counts.
3. Move reads to the new database carrier by carrier.
4. Stop writing to the monolith's tables; keep them read-only for 30 days, then drop them.

## Risks

- Event lag during peak hours: watch consumer lag on route.planned.
- Carriers with custom route rules: test each before moving its reads.
