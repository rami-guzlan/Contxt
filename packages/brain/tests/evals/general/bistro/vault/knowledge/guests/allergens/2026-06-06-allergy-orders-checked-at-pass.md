---
id: allergy-orders-checked-at-pass
title: Handling a guest's allergy order
summary: Allergies go on the ticket in red and only Hana or Marco can clear the plate at the pass; anything from the shared fryer is never allergen safe.
area: guests
topic: allergens
kind: rule
scope: company
status: approved
load: domain
added: 2026-06-06
source: Marco Bellini, in conversation
supersedes: none
applies_to: guests/allergens
must_text: Never tell a guest a dish is safe for an allergy unless Hana or Marco confirmed it at the pass; fried items share one fryer and are never allergen safe.
asked_as:
  - A guest has a shellfish allergy, can they have the fries?
  - Can I tell a table this dish is fine for a celiac?
  - Reply to an email asking if we can do a nut-free dinner
  - Who is allowed to sign off an allergy plate?
  - Can I promise a guest the kitchen is gluten safe?
  - How do I mark an allergy on the order?
  - Is the calamari okay for someone avoiding gluten?
applies_when: Taking, preparing or answering questions about any order for a guest with an allergy.
not_when: Listing which dishes contain hidden allergens.
role: rule
suggested_triggers:
  - allergy
  - ticket
  - gluten free
  - celiac
  - nut allergy
  - shellfish
  - fryer
  - the pass
  - dietary request
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 825281a4de506805
---
Every allergy is written on the ticket in red and called out when it prints. Hana or Marco checks that plate at the pass before it leaves, and nobody else can clear it. There is one shared fryer (calamari, arancini, fries), so anything fried is off the table for gluten, fish or shellfish allergies. If a guest asks ahead by email, the reply says the kitchen will take care but cannot promise a trace-free kitchen.
