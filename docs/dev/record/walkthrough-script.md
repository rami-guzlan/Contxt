# The walkthrough (UX phase G, goals plan G4)

Written 2026-10-10 for build step 8. Two sittings: first every screen on the demo Brain, then a
real day on your own Brain. Each screen lists what to do, what to look for, and the bar it
should clear. Mark each line **ok**, **off** (with a word on what), or **unused**. Unused
blocks and templates are candidates to remove, not to extend (board restraint).

Start the demo from the step 8 branch, not the live app:

```bash
uv run contxt demo knowledge-company --port 8790
```

## Sitting 1: the demo Brain (about 45 minutes)

### Home
- [ ] The strip shows what waits, your goals (or one invitation line if none), and today's work.
- [ ] Nothing about goals beyond that one line when there are none.

### Catch up
- [ ] The plan reads as a time and a few groups, not a pile.
- [ ] "Keeping what it knows true": run "That's wrong" on a request first (Activity), then come
      back. The "Still true?" card names the right note. Answer it in one tap.
- [ ] Bent rules, approval health, corroboration, lessons and hand-ups each read clearly when
      present (the seeded soak makes them; the demo may show only some).
- [ ] Start, one card at a time, each with what is recommended; the finish says what changed.

### Capture
- [ ] Bring in a file and a pasted note; the left-out record is searchable.
- [ ] A meeting digest shows who said what.

### Goals and Projects
- [ ] Set a goal with the coach: **at most five turns, under two minutes.**
- [ ] The goal page: the board (blocks you add), the check-in, the trend, AI on this.
- [ ] A check-in: **under 20 seconds.** A disagreeing measure shows a flag beside your call,
      never over it.
- [ ] Private blocks stay in the app; shared blocks reach the plan file an AI reads.
- [ ] A project with an objective: open a task in it; its brief opens with the objective.
- [ ] Count which board blocks and templates you used (board restraint).

### Brain
- [ ] The map, entries, files and questions; an entry's history and undo.
- [ ] The knowledge agent: run an action; its findings land in Catch up; "How each run went,
      step by step" shows the tools it used and how it ended.

### Knowledge Work
- [ ] Overview leads with governance, not with running things.
- [ ] Workspace: a doc, and live context (a sheet as grid, board and calendar); an AI value
      waits for your tap where the column says so.
- [ ] Prompts, Skills (run, review, replay), Agents, Library, Outputs (by project and row).
- [ ] Workflows: open the canvas from a template. The node library, a box's settings and last
      run, a red line where a step does not fit. Build "Open a task" then "Hand off" and run
      it: T-1 appears in Activity's tasks, handed on.

### Activity
- [ ] Requests: what each AI asked and got, and why; "That's wrong"; "Teach it"; label for
      the eval.
- [ ] Cost and quality, Changes, Tasks and handoffs (the timeline matches what happened).

### Settings
- [ ] Alignment (purpose, goals, rules), approval, local models and machine setups, Test the
      Brain (built in its own chat; check it is there once merged).

## Sitting 2: a real day on your Brain

Only after the step 8 branch is merged and the live app is updated by you (the build never
touches 8787). Through one ordinary workday:

- [ ] Morning: Catch up in the time it says.
- [ ] One goal of yours set with the coach, one check-in at the end of the day.
- [ ] One task handed from an AI to you to a Claude Code session; the receiver works from the
      card alone (asks for nothing the card holds, redoes nothing, keeps every decision).
- [ ] One correction with "That's wrong", and its "Still true?" card answered.
- [ ] One workflow run from the canvas.
- [ ] Anything that slowed you down, confused you or felt like a pile: one line each.

## G4 with others

- [ ] The two interviewees each try the coach and a goal page; note where they hesitate.
- [ ] The T-41 story end to end (an agent verifies six much-used notes, hands it to you, you
      pass it to Claude Code, it finishes with evidence).

## Sign-off

- [ ] the owner signs off on the walkthrough, the real day and G4. Visual design starts after.
