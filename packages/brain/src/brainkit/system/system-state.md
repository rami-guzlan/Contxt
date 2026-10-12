---
id: system-state
title: State sheets and tasks
keywords: state sheet row cell update_state get_state task tasks hand_off handoff card working context
---
State holds fast-changing values per entity (an account's health, a repo's owner, a standard's
version) as sheets in `vault/state/<sheet>/`: a schema, one append-only cell log per row, and a
generated snapshot. Nothing in State is reviewed before it applies, so every change is logged
with who, when and why. Read it with `get_state` (no sheet lists the sheets; a row gives its
values with dates). Write what you learned with `update_state`: columns the person lets AIs
change apply at once and are marked AI-filled until they touch them; "ask me first" columns
wait for one tap; columns that are theirs alone refuse you; under the regulated preset every AI
write waits. Computed columns are worked out from the others and nobody writes them. A request
that names a row by its key or alias gets a "Current state" block, dated. Tasks are rows of the
built-in Tasks sheet and move only through `hand_off`: claim, save progress, pass on with
done-when and next step, or finish with evidence. Name a task, goal, project or row as the
`context` of `get_task_context` to work in it; a task's card then leads the brief.
