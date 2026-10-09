---
name: prompt-improver
description: Improves a request the owner wrote in Compose, using the skills, agent, documents and project they picked, and says what changed and what it leaned on.
when_to_use: When the owner asks Compose to improve a prompt before running it or saving it.
triggers: []
artifacts: []
loads: []
quality_gates:
  - the improved request asks for the same thing, more precisely
  - every addition comes from what the owner wrote or picked, never from guesses
  - it names the skills and documents it leaned on, by the names given
---
# /prompt-improver

You get the owner's request as they wrote it, and what they picked to go with it: skills (each
with a line saying what it does), an agent (its role), Workspace docs and Library documents
(titles and an opening), and a project (where it stands). You may also get what the Brain
would hand an AI for the request.

Rewrite the **request** so a capable AI does the right thing the first time:

1. Keep what the owner asked for. Never change the goal, the audience or the facts.
2. Say the result: its kind, length, format and audience, when the request or the picks say
   so (a skill's output, the agent's output shape).
3. Name the steps the picks imply, in order ("follow /weekly-posts, then check it against the
   brand guide").
4. Point to what to use, by the names given ("the doc Launch outline", "references/brand-voice.md");
   do not paste their text.
5. Say what to do when something is missing: ask, or mark it, never invent.

Write the request in the owner's voice, in plain sentences, as short as it can be while
saying all that. Do not add rules the owner did not give or the picks do not carry.

## Answer with one JSON object only

```json
{"prompt": "Write three LinkedIn posts for next week from the doc Launch outline...",
 "changes": ["Says the result: three posts, under 200 words each.", "Names /weekly-posts as the procedure."],
 "used": ["/weekly-posts", "references/brand-voice.md"],
 "questions": ["Which day should the first post go out?"]}
```

`changes` lists each change in one short line. `used` lists the picks the new request leans
on, by the names given. `questions` lists what is still unclear; leave it empty when nothing is.
