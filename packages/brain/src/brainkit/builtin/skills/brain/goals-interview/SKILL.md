---
name: goals-interview
description: Interview the person about what their Brain is for, one question at a time, and write their answers up in their own words, ready to keep as their goals in the app.
when_to_use: The person is setting up their Brain, or its goals feel out of date, and they would rather talk it through in a chat than fill in the app's interview.
triggers:
  - help me set my brain goals
  - interview me about my goals
  - what should my brain be for
  - update my brain goals
aliases:
  - goals interview
artifacts: []
loads: []
quality_gates:
  - the answers are the person's own words, tidied, never invented
  - every answer is specific enough that another AI could act on it
invocation: explicit
---
# /goals-interview

Everything the person brings into the Brain later (meetings, files, notes) is summarized and
sifted against these answers, so they are worth getting right.

1. Open the note `you-goals`. When it exists, read the answers back briefly and ask which ones
   to revisit.
2. Ask these questions one at a time. After each answer, ask one follow-up when it is vague:
   for a number, a date, an example, or a name. Any question can be skipped.
   1. What do you want this Brain to help you do?
   2. What do you work on, and for whom?
   3. Where do things slip today? What do you forget, redo, or explain over and over?
   4. What should every AI always know about how you like work done?
   5. What should an AI never do for you without asking?
   6. When it reads your meetings and files, what should it leave out?
   7. What is in motion right now? (one per line: each can start a project)
   8. A month from now, how will you know it is working?
3. Keep their words. Tidy only the grammar and the order, and never add what they did not say.
4. Play it back as "Here is what I heard": the first answer as a short purpose statement, then
   every other answer under its question.
5. Tell them to keep it in the app (Settings, Your goals), where they can paste it or read it
   out. Only the person sets their goals: do not propose them as notes.
