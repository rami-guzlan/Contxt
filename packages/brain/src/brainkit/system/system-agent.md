---
id: system-agent
title: The knowledge agent
keywords: knowledge agent upkeep tidy repeats duplicates drift alignment stale freshen projects skills gaps verify sources local model ollama suggestions side panel tools impact hand-up run record
---
The knowledge agent keeps the brain accurate, tidy and aimed at the owner's goals. Nothing it
does changes the brain on its own: what it finds waits for the owner.

Code does the looking (`agent.py`). The map lists every live note the owner may see, by area
and topic, with the flags upkeep cares about (stale, unused 90 days, disputed, must-hold, as
of a date, new), plus the goals, the projects and the skills. Eight actions each gather their
candidates the same way: `tidy-repeats` (notes that say the same thing), `check-drift`
(notes something newer may contradict: what went in on its own, older dated values, the
weekly cross-check), `check-alignment` (the goals and projects against what the brain holds,
notes no AI used in months, must-holds with nothing to bring them up), `freshen-up` (stale
notes, and much-used notes nobody checked in half a year), `tidy-projects` (active projects
gone quiet or without next steps), `tidy-skills` (skills unused, without words to ask for
them, or asked for with the same words), `fill-gaps` (what AIs asked that the brain could
not answer) and `verify-sources` (stale, single-source and much-used notes checked against
the web, five a run, each finding with its citations).

A model does the judging, and code runs the loop around it. Each action follows a procedure
that ships with the engine (`builtin/agent/<action>/SKILL.md`): one job, a worked example
marked as made up, and the exact JSON to answer with, by short reference (`c1`), so even a
small local model never copies an id. A brain skill of the same name replaces one. Each step
the model answers one bounded question; code checks the answer (known references, an allowed
tool, arguments in range), retries once, and calls the tool it names. A job has at most six
steps; one that stays invalid is handed up (a larger model, Claude Code if turned on, or the
owner through Catch up). The tools look (the map, search, a note, State, what changed since
the last run, a note's impact, past suggestions) or suggest (an edit, a merge, a retirement,
a State value, a challenge, a task through `hand_off`); none writes. Kev, when installed,
answers the typed checks (stale, duplicate, contradicts, worth suggesting); code answers them
otherwise.

An answer becomes suggestions in Catch up (a merge, a new text for a note) and questions with
one-tap answers (still true, retire it, mark it disputed, answer it in a sentence), each with
one impact line (the briefs that used the note, what points to it). What the model judged
fine is counted, never acted on. Every job leaves a run record (the model, the prompt version,
each step's answer, tool call and result, the ending), shown step by step on the agent's
page. What the owner decides is remembered by topic; a choice made the same way three times is
offered as a lesson to keep as a note, and the agent never cites its own suggestions as
evidence.
