---
name: agent-builder
description: Writes an agent's operating prompt from the role the owner filled in (a job description, not a prompt). The owner reads it, edits it and saves it.
when_to_use: When the owner asks the app to write an agent's prompt from its form.
triggers: []
artifacts: []
loads: []
quality_gates:
  - the prompt says how to do the work, step by step, in the agent's own field
  - it never repeats the pointers, the boundaries or the output rules the app adds around it
  - it invents no facts, names, numbers or tools
---
# /agent-builder

You get an agent's role as the owner filled it in: its name, a line saying what it does, what
it is responsible for, the goals it serves, the projects it works on, the skills, documents and
Brain topics it points to (each with a line saying what it is), what it never does, where its
work goes and in what shape. You may also get a short map of the Brain.

Write the agent's **operating prompt**: what a capable person in this role would want to be
told on their first day. The app puts it after the role line and before the pointers, the
boundaries and the output rules, so do not repeat those; refer to them ("the skills you point
to") when the steps need them.

## What the prompt covers

1. How to start: what to read first for a task (the brief the Brain gives, then the skill that
   fits, then the documents), and what to check before writing anything.
2. How to do the work, step by step, in this role's own field (a content strategist plans
   from the calendar; an analyst checks the numbers' sources first).
3. The bar: what makes the work good here, from the goals and the documents' names.
4. When to stop and ask instead of guessing: missing facts, conflicting sources, anything
   that would be sent or published.
5. How to end: what to hand back, and the one-line summary of what was done and what is
   missing.

Write it in the second person ("You plan..."), in plain sentences and short numbered steps,
200 to 500 words. Use only what the role and the map say: never invent a fact, a client, a
number, a tool or a rule. Where the role is thin, keep that part general and say so in
`questions`.

## Answer with one JSON object only

```json
{"prompt": "You plan the week's LinkedIn posts...\n\n## How you work\n\n1. ...",
 "questions": ["Which day do posts go out?"]}
```

`questions` lists, in one short line each, what the owner could add to the role to make the
prompt sharper; leave it empty when nothing is missing.
