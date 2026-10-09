---
id: system-agent
title: The knowledge agent
keywords: knowledge agent upkeep tidy repeats duplicates drift alignment stale freshen projects skills gaps local model ollama suggestions side panel
---
The knowledge agent keeps the brain accurate, tidy and aimed at the owner's goals. Nothing it
does changes the brain on its own: what it finds waits for the owner.

Code does the looking (`agent.py`). The map lists every live note the owner may see, by area
and topic, with the flags upkeep cares about (stale, unused 90 days, disputed, must-hold, as
of a date, new), plus the goals, the projects and the skills. Seven actions each gather their
candidates the same way: `tidy-repeats` (notes that say the same thing), `check-drift`
(notes something newer may contradict: what went in on its own, older dated values, the
weekly cross-check), `check-alignment` (the goals and projects against what the brain holds,
notes no AI used in months, must-holds with nothing to bring them up), `freshen-up` (stale
notes, and much-used notes nobody checked in half a year), `tidy-projects` (active projects
gone quiet or without next steps), `tidy-skills` (skills unused, without words to ask for
them, or asked for with the same words) and `fill-gaps` (what AIs asked that the brain could
not answer).

A model does the judging. Each action follows a procedure that ships with the engine
(`builtin/agent/<action>/SKILL.md`): what the model is given, how to judge, and the JSON to
answer with, by short reference (`c1`), so even a small local model never copies an id. A
brain skill of the same name replaces one. The owner picks the model: Claude Code on their
computer, or a local model through Ollama, which gets a shorter map.

An answer becomes suggestions in Catch up (a merge, a new text for a note) and questions with
one-tap answers (still true, retire it, mark it disputed, answer it in a sentence). What the
model judged fine is counted, never acted on. Suggestions made by code, with no model, name
the action that deals with each; the app shows them at the bottom right as the brain changes.
