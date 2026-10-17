---
id: premed-and-blood-thinner-check
title: Premedication and blood thinner check
summary: Patients flagged for antibiotic premedication or blood thinners are seen only once the premed and their medication are confirmed.
area: patients
topic: medical-history
kind: rule
scope: company
status: approved
load: domain
added: 2026-06-12
source: Nadia Okafor, in conversation
supersedes: none
applies_to: patients
must_text: For patients flagged for antibiotic premedication or blood thinners, confirm the premed was taken and Nadia reviewed the medication before any cleaning, extraction or surgery; if not confirmed, reschedule, never proceed.
asked_as:
  - A patient with a joint replacement is here for a cleaning
  - They forgot their antibiotic before the visit, now what?
  - Patient on anticoagulants is booked for an extraction today
  - Can we go ahead if the doctor hasn't checked their meds?
  - Write the appointment reminder for a heart valve patient
  - Should we reschedule a patient who skipped their premed?
  - What do we confirm at check-in for flagged medical charts?
applies_when: Seeing patients flagged for antibiotic premedication or blood thinners for cleanings, extractions or surgery.
not_when: Routine health history updates for patients with no flag.
role: rule
suggested_triggers:
  - check-in
  - cleaning
  - extraction
  - oral surgery
  - joint replacement
  - heart valve
  - antibiotics
  - medication list
  - reminder text
  - anticoagulants
enriched: 2026-10-16
enriched_by: model:claude-test-data
enriched_hash: 0689f3036d6b8075
---
Some charts carry a red PREMED flag (artificial heart valve, past heart infection, or a surgeon's instruction after a joint replacement) or a BLOOD THINNER flag. For these patients the visit goes ahead only if they confirm at check-in that they took the antibiotic an hour before, and I have looked over their current medication list. If either is missing we reschedule; we never start the cleaning and hope for the best. Reminder texts for flagged patients must include the line about taking their premed.
