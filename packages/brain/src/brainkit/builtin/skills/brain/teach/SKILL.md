---
name: teach
description: Teach the Brain something on purpose. Asks a few short questions so it is captured right (who it applies to, when, any exceptions), checks what the Brain already says, then proposes it.
when_to_use: The person wants the Brain, and so every AI they use, to know or always do something.
triggers:
  - teach the brain
  - remember this
  - add this to my brain
  - from now on
  - always do this
aliases:
  - teach my brain
artifacts: []
loads: []
quality_gates:
  - one idea per note, in the person's words where possible
  - nothing is proposed that a note already says
invocation: explicit
---
# /teach

Help the person put one thing into the Brain, said so that every AI gets it right.

1. Restate what they want kept in one plain sentence, and ask whether that is it.
2. Ask only what is missing, at most three short questions:
   - Is it a rule (how work is done), a fact, a preference, or a decision?
   - Where does it apply: everything, one project, one client, one kind of work?
   - Are there exceptions?
3. Search the Brain for it. When a note already says it, say which and stop. When a note says
   something different, quote it and ask which is current.
4. Open the note `you-goals`. When this does not fit what the Brain is for, say so gently and
   ask whether to keep it anyway.
5. Propose it as a note: a plain title, a one-line summary, the statement, and the person's own
   words in the evidence. Name the note it replaces, or contradicts, when there is one.
6. Tell them whether it applied at once or waits for their yes in Catch up.
