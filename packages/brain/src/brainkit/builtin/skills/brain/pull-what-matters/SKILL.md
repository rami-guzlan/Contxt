---
name: pull-what-matters
description: The knowledge agent. Summarize something the person brought in (a meeting transcript, a document, notes) and pull out the context worth keeping, weighed against their goals for the Brain and their active projects. Says which goal or project each piece serves, and lists what it left out so nothing is lost.
when_to_use: The person shares a transcript, a file or notes and wants what matters from it kept, or asks what is worth remembering from something.
triggers:
  - pull what matters from this
  - what should my brain keep from this
  - summarize this and keep what matters
  - pull the context out of this transcript
  - what is worth remembering here
aliases:
  - knowledge agent
artifacts: []
loads: []
quality_gates:
  - every piece kept will still be true next month and serves a goal, a project, or how the person works
  - every piece kept names its goal and its project
  - what was left out is listed with why, never dropped in silence
---
# /pull-what-matters

Read something the person brought in and keep only what serves them.

## 1. Know what matters to this person

- Open the note `you-goals`: the person's own answers about what this Brain is for, and what
  it should leave out. When there is none, say so once and judge by durability alone.
- List the active projects, with what each is for and where it stands.
- When the person says what they want from it ("just the pricing discussion"), their words win
  over the goals.

## 2. Summarize it

- One line on what it is mostly about, naming the goal or project it serves, for example
  "Mostly about: Q4 webinar series; the goal to stop dropping follow-ups."
- Two or three sentences on what it is and what came of it.
- Its key points, one plain sentence each, each with the goal or project it serves (or none).

## 3. Pull what passes two questions

For each point, ask:

1. Will it still be true and useful next month?
2. Does it serve one of the goals, belong to an active project, or tell any AI who the person
   is or how they want work done?

Keep only what passes both. Search the Brain before keeping anything: skip what a note already
says, name the note a piece replaces, and the note it contradicts when it disagrees.

## 4. Keep it, and say what you left out

- Propose each piece to the Brain with a plain title, the statement, the evidence quoted from
  the source, the goal it serves and the project it belongs to.
- In a conversation, show the list first and ask which to keep. Run from the app, propose them
  directly: they wait for the person in Catch up.
- End with what you left out, one line each with why (small talk, already in the Brain, serves
  no goal or project), so the person can still pull any of it.
- When most of it is about work that is not a project yet, ask whether to start one. When it is
  about a subject none of the goals covers, say so: it may belong in the goals.
