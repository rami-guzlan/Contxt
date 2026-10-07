---
name: trip-planner
description: Plan a trip day by day within its budget, the way Taylor travels.
triggers:
  - plan the trip
  - itinerary
  - plan our days in
aliases:
  - itinerary
  - trip plan
artifacts: []
loads:
  - travel/preferences
  - travel/documents
  - references/packing-list.md
quality_gates:
  - within budget
  - one main thing a day
  - bookings listed, not made
scope: company
---
# /trip-planner

Plan a trip day by day.

1. Read the trip's project for dates, places and budget.
2. Follow Taylor's travel preferences: trains under four hours, kitchens with Ollie, at most
   one city change every three days.
3. Each day: one main thing, one easy backup for a tired kid, and where to eat (check for
   peanuts).
4. Add the costs and keep the total within the budget.
5. List what needs booking, by date. Bookings wait for Taylor's yes.
