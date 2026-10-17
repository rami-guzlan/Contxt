---
id: chilled-frozen-limits
title: Temperature limits for chilled and frozen food
summary: Chilled food stays at 41 F or below, frozen at 0 F or below; chilled food above 41 F for over 2 hours is thrown out and logged.
area: safety
topic: coldchain
kind: rule
scope: company
status: approved
load: domain
applies_to: safety
must_text: Keep chilled food at 41 F or below and frozen at 0 F or below; chilled food above 41 F for over 2 hours, or an unknown time, is discarded and logged, never distributed.
added: 2026-06-04
source: Tomas Reyes, in conversation
supersedes: none
asked_as:
  - Milk sat on the dock a while, can we still give it out?
  - This frozen product thawed, can we refreeze it?
  - What temperature should the truck cooler hold?
  - Nobody knows how long these cold items were out, keep them?
  - It looks fine, can't we just send it?
  - What do I write on the discard sheet?
  - What range should a pantry fridge stay in?
applies_when: Storing, moving or deciding whether to distribute chilled and frozen food anywhere along the chain.
not_when: Accepting or refusing donations at the dock, or the steps during a cooler outage.
role: rule
suggested_triggers:
  - fridge temperature
  - freezer reading
  - thawed
  - left out
  - warm product
  - discard log
  - reefer
  - cold chain
  - probe
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: fa5643bd1f2c92ab
---
Coolers hold 33 to 41 F and freezers 0 F or colder, in the warehouse, on the trucks and at every agency. Refrigerated product that sat above 41 F for more than 2 hours, or for a time nobody knows, goes in the dumpster and on the discard log with weight and reason. Thawed frozen product is never refrozen for distribution. "It still looks fine" is not an exception.
