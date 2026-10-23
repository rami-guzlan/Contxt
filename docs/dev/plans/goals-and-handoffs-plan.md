# Gnomon goals, projects and handoffs: plan

Plan only: no code was changed. Written October 9, 2026 (prompt 143 in `rami-prompts-verbatim.md`)
and revised the same day with Rami's notes (prompt 145) and his follow-up (prompt 149). Sources:

- the design first drawn on the System Map (`gnomon-system-map.html`, Goals and handoffs view);
- the two plans being built now, `brain-logic-plan.md` (BL) and `knowledge-work-ux-plan.md` (UX);
- the current code: `brainkit/goals.py` (the eight-question goals interview, the `you-goals` note),
  `services/agents.py` (an agent's "Goals it serves"), `brainkit/focus.py` (project journals),
  `services/catchup.py`, and the Settings, Activity and project pages;
- Rami's notes: the Projects page becomes Goals and Projects, with his own goals at the top and a
  page per goal that is more human-in-the-loop than a project page;
- his follow-up: goals are optional, and every project has an objective that agents carry into
  their tasks;
- Meta's Muse as inspiration for setting goals (section 8);
- the research in section 14, checked on October 9.

Another chat is building BL and UX in the order of UX section 6. Section 9 says where each phase
here fits into that order, so one builder can carry all three plans. Gnomon is the working name;
the code says Contxt.

**Decisions: all 16 are set (section 12).** 1 to 10 were approved on October 9 (prompt 144) as
recommended, except 9, which became the `todos_update` tool. Rami's notes (prompt 145) moved his
goals to their own pages, revising 8 and adding 11 to 14. His follow-up (prompt 149) made goals
optional and gave every project an objective that agents carry into their tasks, adding 15 and
16. Decisions 11 to 16 were approved as recommended (prompt 150). The plan is ready for the
build chat (section 9).

## 1. Summary

Goals say what should stay true or what you want to achieve. Tasks are the work toward them.
Handoffs pass that work between you, your agents and your AI tools without losing the thread.
There are four levels:

- **The Brain's purpose**: your high-level Brain goal, in Settings.
- **Your goals** (optional): what you want to achieve with the help of your AIs and this Brain,
  each with its own page in Goals and Projects.
- **Agent goals**: what your agents keep true, measured by code.
- **Projects**: bounded work, each with an objective, serving your goals when you have them.

**Goals are optional.** A Brain can run on projects alone. Each project has an objective, a
short summary of the output it is chasing, and every agent working a task in the project gets
it first.

It all rides on tiers the Brain already has. One new tool, `todos_update`, lets every agent save its
progress and pass work on.

| Piece | What it is | Where you see it | Phase |
| --- | --- | --- | --- |
| Goals and Projects | The Projects page. With goals: your goals on top and your projects below, each linked to the goals it serves. Without goals: just your projects | The sidebar, where Projects is today | G1 |
| A goal's page | Your goal, with a strategy board, a check-in fill-in, its projects, docs and sheets, and the tasks and updates of the AIs working on it | Clicking a goal | G1, sheets and tasks in G2 |
| The strategy board | A simple board of blocks (notes, checklists, sheets, docs, projects, links, decisions) you arrange to plan the goal | On each goal's page; optional on projects | G1, sheets in G2 |
| Settings > Alignment | The Brain's purpose, your goals as links, agent goals with measures, and the rules every AI follows | Settings (replaces "Your goals") | G1 |
| Goal coach | Setting a goal by talking it through: what you want, how you'll know, what gets in the way, the plan | "Set a goal" anywhere goals appear; any AI chat | G1 |
| Check-ins and goal journals | Your quick fill-ins and agents' progress notes, in one feed per goal; agent goals speak up only when they slip | Goal pages, Home, Catch up | G1 |
| Tasks | One piece of work, one owner at a time, a row in a built-in Tasks sheet whose log records who did what and when | Goal and project pages; Activity > Tasks and handoffs | G2 |
| Handoffs and the `todos_update` tool | Cards with fixed fields that travel to the next owner on any tool; one call to take a task, save progress, pass it on or finish it | The hand-off composer; Catch up; every AI's first brief | G2 |
| Projects, semi-reflected | Project pages gain the same check-in, updates feed, AI rail and an optional board, kept execution-first | Each project's page | G1, G2 |
| Project objectives | A sentence or two on the output a project is chasing, at the top of every task brief in the project | Each project's page; every agent's task brief | G0 (field and briefs), G1 (page) |
| Workflows and teams | "Open a task" and "Hand off" steps; teammates as owners; admins for shared goals | Workflows canvas; team edition | G3 |
| Proof | Check-in, handoff, resume and measure evals; a walkthrough | Activity > Cost and quality; the walkthrough | G4 |

## 2. Principles

1. **Goals choose what gets worked on and what gets kept. They never hide anything from your
   AIs.** Retrieval stays goal-blind (BL 5.2, 15.2). A goal reaches a brief only as the reason
   for the task at hand, plus the parts of its page you chose to share.
2. **Goals are optional.** Projects alone are a complete setup. Until you set your first goal,
   nothing about goals shows except one line inviting you to, and agents take their direction
   from each project's objective.
3. **Your goals stay yours.** Agents never own, change or close your goals. They suggest, and
   they work only on tasks you accept or assign. Your check-in is the last word on how a goal of
   yours is going; a measure that disagrees is shown beside it, never over it.
4. **Think on the page first.** A goal's board is your thinking space. AIs read only the blocks
   you share with them (UX 4.3: your docs stay private until you add them).
5. **Simple on purpose.** Seven kinds of block, one or two columns, a few templates, no themes or
   nesting. The board helps you plan; it never becomes a project of its own.
6. **This is not a to-do app.** The October 6 pivot removed Goals, To-dos and Tasks pages because
   most of the workspace went unused. Tasks here exist for work done by or with your AIs, or for
   work tied to a goal or project that an AI should know about. No personal reminders, no Gantt
   charts, no time tracking, no comment threads.
7. **One item, one home, many doors** (UX section 2). Your goals live in Goals and Projects, agent
   goals in Alignment, tasks in the Tasks sheet, docs and sheets in Workspace. Every other screen
   links to them.
8. **Calm.** You hear from a goal only when something needs you: a check-in that is due, a slip,
   a handoff, a suggestion.
9. **Code measures, a model suggests, you decide.** Computed measures come from code, never from
   a model. Changes to the Brain still pass their gates.
10. **Done means evidence; one owner at a time; agents write their progress down.** A task closes
   with an output or a decided proposal. Ownership changes only through `todos_update`, with a card.
   Before an agent stops, gets blocked or passes work on, it saves what it knows.
11. **Team-ready, solo now.** Owners, scopes and admins are in the model from the start; the solo
    app shows "You" and your agents.

## 3. The ladder, and how the levels differ

### 3.1 The levels

| | The Brain's purpose | Your goals | Agent goals | Projects | Tasks (not goals) |
| --- | --- | --- | --- | --- | --- |
| What it is | Why this Brain exists: your high-level Brain goal | Something you want to achieve, with AI's help (optional) | Something an agent keeps true | Bounded work with an objective and a done-when | One piece of work |
| Example | "Keep my work straight across every AI I use, without explaining it twice" | "Grow webinar attendance to 150 a session by December" | Knowledge agent: "No much-used note goes 180 days unchecked." Accounts agent: "Every account row updated within 30 days" | "Q4 webinar series". Objective: "Three webinars that each bring 150 qualified attendees, and a follow-up sequence sales can use." Done when: 3 live by December 15 | "Pull sign-ups from the form export" |
| Home | Settings > Alignment | Goals and Projects, a page each | Settings > Alignment, and the agent's page | Goals and Projects, a page each | The Tasks sheet; shown on goal and project pages |
| Owner | You (company and department purposes in the team edition) | You (a person or a team later) | The agent | The project's owner | One person, agent or tool at a time |
| Ends? | Never | When you call it met or drop it; dated goals are met or missed | No; paused or retired | Done or dropped | Done or dropped |
| Progress | Two or three signals you pick from "how will you know it's working" | Your check-in, with an optional computed measure beside it | A measure the engine computes, against a target | Milestones (tasks marked as milestones) and the journal | Its evidence |
| AI's part | Steers what is worth keeping | Suggests next steps; works on tasks you accept or assign | Opens a task when its measure slips | Works its tasks, with the project's objective in every brief; saves, hands off | Its owner's next brief |
| Changing it | Your own act, with a reason and an undo point | Your own act, with an undo point | You approve; an agent may only propose | Like any project baseline: a reason and an undo point | Logged; owner changes only through `todos_update` |
| Never | Filters what a request receives | Filters what a request receives; changed by an agent | Filters what a request receives | Holds goals of its own | Changes owner without a card |
| Lives in | Alignment (the `you-goals` note, as today) | Alignment (goal notes) plus its page (board, check-ins) | Alignment (goal notes) | The project's baseline and journal | State (the Tasks sheet) |

Projects link to the goals they serve; an agent goal can serve the purpose or one of your goals;
a task can belong to a goal, a project, or both. Goals are optional: without them, the ladder is
the purpose, agent goals, projects and tasks.

### 3.2 The same thing in a few sentences (the explainer the app shows)

- **The purpose** is why your Brain exists. It never ends and has no target. A few signals show
  whether it is working, such as fewer corrections and fewer re-explanations.
- **Your goals** are optional: what you want to achieve beyond a single project. Each has a page
  where you plan it, check in on it, and see what your AIs are doing for it. Your AIs help, but the goal and the call on how it is
  going stay yours.
- **Agent goals** are what your agents keep true. The knowledge agent's keep the Brain itself
  healthy. Other agents' keep their domain current, such as the accounts sheet. Code measures
  them, and when one slips its agent opens a task.
- **Projects** are bounded pieces of work, done by a date. Each has an objective, a sentence or
  two on the output it is chasing, which every agent working in it reads first. If you set goals,
  projects link to them; if you don't, projects are all you need.
- **Tasks** are not goals. They are the work.
- **Rules are not goals either.** A rule says how work must be done ("never quote prices in a
  first email") and reaches every brief where its topic comes up. A goal says what outcome you
  are after.

### 3.3 How work happens under each kind of goal

- **Agent goals**:
  1. The engine checks the measure on its cadence (code only).
  2. The status worsens.
  3. The agent opens a task (capped, 5.5), works it, saves progress and hands off what needs you.
  4. It closes the task with evidence.
  5. The next check shows the measure moving.
- **Your goals**:
  1. You plan on the board and check in.
  2. Your AIs suggest next steps (from the goal coach, the knowledge agent and the agents serving
     the goal).
  3. You accept a suggestion or a checklist item, and it becomes a task owned by the agent or
     tool you pick.
  4. The agents work, save and hand off. Their notes appear in the goal's updates feed, beside
     your check-ins.
- **Projects only**:
  1. You give the project an objective and a done-when.
  2. Every task in it, yours or an agent's, carries the objective in its brief and its card.
  3. Agents work, save and hand off; their notes join the project's updates feed and journal.
  4. Milestones and the journal show the progress. Nothing else is needed.

## 4. Measures and check-ins

### 4.1 Seven kinds of measure, in plain words

| Kind | Reads as | Example |
| --- | --- | --- |
| You enter it | A number, a percent or a status you fill in at check-in | "71 a session", "On track" |
| Keep at or under | "At most N" | Overdue much-used notes: at most 0 |
| Keep at or above | "At least X%" | Account rows updated within 30 days: at least 90% |
| Reach by a date | "N of M by a date" | 3 of 3 webinars live by December 15 |
| Do it every period | "Every week" | A weekly review, done 3 of the last 4 Fridays |
| Trend | "Going down" or "going up" | Corrections per week, going down (purpose signals) |
| Your judgment | A one-tap answer at check-in | "Are drafts coming back on message?" Yes, mostly, no |

Your goals default to "You enter it". You can add a computed measure beside it, such as a column
of a sheet on the goal's page. Agent goals always use computed measures.

### 4.2 The signal library (what a computed measure can read)

Code computes every one from data the Brain already has. When you pick a signal, its current
value shows at once ("Right now: 64").

| Signal | Source | Available |
| --- | --- | --- |
| Much-used notes past their review date, or unchecked for 180 days | Brain index and the ledger's use counts (freshen-up's gather) | Now |
| Items waiting in Catch up longer than N days | Catch up | Now |
| Questions your AIs asked that the Brain could not answer, older than N days | The ledger (fill-gaps' gather) | Now |
| Active projects quiet for N days | Project journals (tidy-projects' gather) | Now |
| Must-hold recall on the eval set | BL0's eval runs | Now (needs the private set labeled) |
| Approvals taken back within a month; approval speed | Catch up, undo points | Now |
| Milestones done in linked projects | Project baselines and the Tasks sheet | G1 (milestones), G2 (tasks) |
| Corrections per week | Capture's correction cues; BL5's correction signals | Partly now, fully in step 7 |
| Drafts sent back by the output check | BL5 output checks | Step 7 |
| A column of any sheet: latest value, sum, count, average, by status | State summary rows (BL 8.2), including sheets made on the goal's page | Step 6 |
| State rows past their age limit; rows updated within N days | State cell logs (BL4) | Step 6 |
| Tasks done with evidence, handoffs claimed within a day, sessions resumed from a saved card | The Tasks sheet and `todos_update`'s log | G2 |

### 4.3 Status

- **Your goals**: your latest check-in sets the status (On track, At risk, Off track), and it
  stays current for one cadence period. After two periods without one, the goal shows "Not checked
  in" and any computed measure. When a computed measure disagrees with your call, a small flag
  says so, for example "The sheet says 64 of 150, behind an even pace". Your call still stands
  (decision 13).
- **Agent goals**: computed. On track when the measure meets its target; Needs attention within a
  tenth of it or after one missed check; Off track further out or after two misses in a row.
- **Both**: No data yet when nothing can be measured, plus Paused, Met, Missed (dated goals) and
  Retired.

### 4.4 Check-ins, the calm way

- **Your goals**: a check-in is due once per cadence (weekly by default). Home shows one line,
  "Check in on 2 goals", and the goal page shows the fill-in. A check-in takes two fields and a
  sentence. Skipping is fine; nothing nags.
- **Agent goals**: a check that keeps the same status writes a trend point and says nothing. A
  Catch up card appears only when a goal turns Off track, stays Needs attention for two checks,
  or is a judgment goal whose check-in asks you. At most one card per goal per check, and it says
  why it appeared.
- **New material**: when something new touches a goal (a meeting moves a date), the knowledge
  agent proposes the change, and it waits for you, the way Muse proposes plan changes.
- **Weekly review** (optional, off by default): a short Friday card on Home, built by code:
  - your goals with their latest calls and flags;
  - agent goals that moved or slipped;
  - tasks done, and by whom;
  - handoffs waiting;
  - the week's progress notes, one line each;
  - up to three next steps.

### 4.5 Goal journals

Each of your goals and each agent goal has an append-only journal, like a project's
(`journal/goals/<goal id>.jsonl`). It holds:

- your check-ins;
- agents' progress notes, written through `todos_update`;
- decisions recorded on the goal.

The goal page's updates feed reads it, with the task events of the goal's tasks interleaved. A
note never changes a computed status or a goal's definition. Only an amendment, or your own edit
for your own goals, does that.

## 5. Tasks and handoffs

### 5.1 The Tasks sheet

A built-in State sheet (BL 8), like Projects: it cannot be deleted, and its columns are fixed but
can be extended. Every change is a cell event with who, when and the source, so the history of
who did what is the log itself.

| Column | Holds | Who may change it |
| --- | --- | --- |
| Task | What to do, in a line | AIs may change |
| Goal | The goal it serves: one of yours, or an agent goal (optional) | Ask me first |
| Project, For | The project; the row it is for (an account, a repo) | AIs may change |
| Milestone | Yes or no; counts toward the project's done-when | Ask me first |
| Owner | A person, an agent, or a tool queue (5.2) | Only through `todos_update`, with a card |
| Tool | Where it is being worked: Claude Code, Codex, Cursor, Claude app, ChatGPT, Gnomon run | AIs may change |
| Status | 5.3 | Only through `todos_update`; Done needs evidence |
| Due | Date | Ask me first |
| Evidence | Links to outputs and decided proposals | Through `todos_update` |
| Card | The latest card: progress saved, or work passed on | Written by `todos_update` |
| Days open, Since update | Computed from the date and the cell log | Nobody: computed |

Views: a board grouped by Status, a list grouped by goal or project, a calendar by Due. A summary
row: open, waiting for you, blocked, overdue.

### 5.2 Owners

- **People**: you; teammates in the team edition.
- **Agents**: the knowledge agent and every agent in Knowledge Work > Agents.
- **Tool queues**: "Claude Code", "Codex", "Cursor", "Claude app", "ChatGPT", each optionally
  narrowed to a project or a repo ("Claude Code, repo contxt"). A tool queue is not a principal.
  The session that claims the task acts for you, and the cell log records both the session and
  you.

### 5.3 Statuses

The statuses are:

- **Open**.
- **Handed off**: waiting to be claimed.
- **Working**.
- **Waiting for you**: nothing moves until you act, whether it is a handoff to you or a proposal
  it waits on.
- **Blocked**: with a reason.
- **Done**: with evidence.
- **Dropped**: with a reason.

The board shows the first six columns; Dropped stays in the list.

### 5.4 The card

The card is the working context's resumption card (BL 8.3), made portable. It serves two
purposes: a save (progress kept for whoever comes next, the same agent included) and a handoff
(work passed to a new owner). Same fields every time:

| Field | Why it is there | Filled by |
| --- | --- | --- |
| Objective or goal, and done-when | The receiver knows what output is being chased and what finished looks like | Code fills in the project's objective and the goal's line, if any; the writer adds done-when (required to pass on) |
| Done so far | Nothing is redone | The agent in its own words; code adds links from the task's log, runs and outputs |
| Next step | Work can start at once | The writer (required) |
| Decisions made | Nobody re-decides or contradicts them | The agent; code adds decided proposals and disputed pairs |
| Open questions | Gaps are not silently filled | The writer |
| What to load | Pointers to notes, rows, skills, Library items and the goal's shared plan, read at their current version | The agent; code adds the task's links and what its runs opened |
| Must-holds in play | Your rules travel with the work | Code, from the domains touched |
| Lineage | Outputs from one brief count once as evidence | Code |

At most about 250 tokens rendered, because it is pointers, not bodies. An AI writes and passes
the card with `todos_update` (5.8); `sheets_propose_update` refuses the Owner, Status, Evidence and Card
columns, so there is one way to move a task. When the agent fills a field itself, code keeps its
words and adds only what it can verify.

### 5.5 Who opens tasks, and limits

- **You**:
  - from a goal's page (a checklist item, an accepted suggestion, "+ Task");
  - from a project;
  - from Activity;
  - from any AI chat ("make this a task", "hand this to the Accounts agent").
- **Agents, for agent goals they own**: on their own, at most one open task per goal and five per
  agent.
- **Agents, for your goals**: never on their own. They suggest next steps on the goal's page, and
  a suggestion becomes a task when you accept it.
- **Any AI, when you ask**: "make this a task" in a chat creates one with `todos_update`, owned by you
  or by the tool queue you name.
- **Workflows** (G3): an "Open a task" step.

### 5.6 How each receiver learns, claims and starts

| Receiver | Learns from | Claims by | Starts with |
| --- | --- | --- | --- |
| An agent | Gnomon schedules a run within the agent's schedule ("Run now" to hurry) | Its run, at start, with `todos_update` (claim) | The card as its call to action, under its kernel |
| Claude Code (a repo or project) | The session-start hook lists pending handoffs for this repo or project, one line each | You say "pick it up"; the session claims with `todos_update` | `gnomon_get_context` with `context` set to the task: the card |
| Codex, Cursor | The first brief lists pending handoffs for this tool | Same, over MCP | Same |
| Claude app, ChatGPT | The first brief lists pending handoffs | Same | Same |
| You | Catch up ("Handed to you"), Home and the goal or project page | "Start" in the app, or "pick up T-44" in any AI chat | The card, in the app or the chat |
| A teammate (later) | Their Catch up | Same | Same |

A handoff nobody claims within a day shows in Catch up with "Remind" and "Take back". If two
sessions try to claim, the first wins; the second sees who has it.

### 5.7 Done, and what it touches

- Done needs evidence: an output or a decided proposal.
- A milestone done moves its project's done-when.
- A task under a project writes a line to the project's journal (status, current, next); a task
  under one of your goals adds an event to the goal's updates feed. Neither needs approval.
- Each run that worked on the task keeps its transcript as an episode (BL 9).

### 5.8 The `todos_update` tool

This is decision 9, as amended on October 9. One call covers everything an agent does to a
task's ownership and progress, and to its goal's progress notes. Agents offload what they know to
the Brain instead of holding it in a context window, and anyone can see who did what.

```
todos_update(
  task           "T-41"; or new_task to open one
  new_task       { title, goal, project, for, due }                        optional
  goal           a goal id, for a goal progress note with no task          optional
  to             you, an agent, or a tool queue; leave it out to keep the task
  claim          true to take a task handed to you or your tool
  status         working, blocked, waiting_for_you, done, dropped
  done_so_far, next_step, done_when, decisions, open_questions, load, evidence
  goal_note      a line for the goal's journal                             optional
  reason         why it is blocked or dropped
)
returns: the card as stored, the owner and status now, what the receiver will see,
or a refusal that says how to fix the call
```

Four moves, one tool:

| Move | Call | What happens |
| --- | --- | --- |
| Take | `claim: true` | Status Working; the cell log records the session and the person or agent it acts for. The first claim wins. |
| Save progress | No `to` | The card becomes the task's resumption card, and a line joins the task's log. The next session, or the same agent after a compaction, starts from it. |
| Pass on | `to` set | The owner changes and the status becomes Handed off (Waiting for you when it is you). Done-when and Next step are required. |
| Finish | `status: done` | Needs evidence: an existing output or a decided proposal. A milestone moves its project; a project task writes a journal line. |

A `goal_note` can ride on any call, or `goal` alone can carry one. It adds a line to the goal's
journal (4.5), which shows in the goal's updates feed. It never changes the goal's status or
definition. On your goals, agents may add notes but can never set your status.

The card's first field fills itself from the task's project objective, and from its goal when
there is one, so agents never retype them.

Rules the tool enforces:

- Only the owner, or you, can pass on or finish a task. Agents claim only what was handed to them
  or to their tool queue. Agents cannot open tasks for your goals; they suggest instead (5.5).
- Blocked and Dropped need a reason; Done needs evidence.
- A save identical to the last one does nothing, and saves within ten minutes of each other
  collapse into one line in the feeds.
- Text is masked for secrets (BL 9's patterns) and stored as the agent's account, with who said
  it (an agent run, or a session acting for you). It is never evidence for notes (the
  circular-evidence rule) and never an instruction.
- Durable facts and decisions still go through `notes_propose`. When a save holds one, the reply
  says so, the way the capture hook nudges.
- The rendered card stays at about 250 tokens; longer text stays in the task's log, and the card
  points to it.

When agents call it (the tool's description, the server instructions and agents' kernels all say
so):

- when they take a task;
- after a step that took real work, and before their context gets long;
- when they are blocked, and before they stop;
- when someone else should continue;
- when they finish.

Reminders, so it does not depend on the model remembering:

- **Gnomon runs**: the finishing gate (run contracts, from the safeguards build) does not close a
  run that worked a task until it saved progress, passed the task on or finished it.
- **Claude Code**: with a task active, the Stop hook asks for a save before the session ends, and
  the brief after a compaction carries the latest card.
- **Other clients**: the first brief of a session with an active task reminds in one line.

What it is not:

- not a notes tool: knowledge goes through `notes_propose`;
- not a way to change a goal: goals change by amendment, or by your own edit for your own goals;
- not a free-form log: every save has the card's shape.

## 6. Screens

Sketches show structure only; visual design comes after (UX section 2).

### 6.1 Goals and Projects (the Projects page, renamed)

The sidebar entry and page title change from Projects to Goals and Projects; the address stays
`/projects`, so links keep working.

```
Goals and Projects                                        [+ Goal]  [+ Project]
What you want to achieve, and the work toward it. Your Brain's purpose is in Settings > Alignment.

YOUR GOALS
 Grow webinar attendance to 150 a session     On track      71 / 150   by Dec 15
   2 projects | 3 AI tasks this week | checked in Mon                     [Check in]
 Launch the Gnomon beta to 10 teams           At risk       3 / 10     by Jan 31
   1 project | 1 handoff waits for you | checked in 9 days ago             [Check in]
 Make the Brain trusted across the team       Mostly (your call)       ongoing
   no projects yet | 2 suggested first steps                              [Check in]
 [+ Set a goal]

PROJECTS                                    Goal: All v     Status: Active v
 Q4 webinar series     Grow webinar attendance    2 of 3 milestones   On track
 Website refresh       (no goal)                  2 of 5 milestones   At risk
 Paused or finished (3)
```

- Goal cards show the goal, your latest call and any flag, progress against the target with a
  small trend, the date or "ongoing", and one line of activity. "Check in" opens the fill-in on
  the card itself.
- Projects show the goals they serve; filter by goal. A project with no goal is fine.
- "+ Goal" opens the goal coach (6.8).
- **New project**: a name; the objective ("What output are we chasing?", a sentence or two that
  Ask AI can draft from the project's docs for you to edit); the done-when and due date; and the
  goals it serves, asked only when you have goals.
- **Without goals**, the page is simply Projects, with one quiet line under the title: "Goals are
  optional. Add one when you want to plan toward something bigger than a single project." The
  sidebar says Projects until you set your first goal (decision 15), and goal links, check-ins
  and goal lines on Home stay hidden.

### 6.2 A goal's page

A goal's page looks like a project's page, but it leads with your strategy and your check-in. AI
work sits beside it, in a rail.

```
Goals and Projects > Grow webinar attendance to 150 a session
Grow webinar attendance to 150 a session                         [Check in]  [Ask AI]
Why: "Webinars are our best source of qualified conversations."
On track (your call, Mon)   71 of 150 a session, by Dec 15   (trend)   Owner: You
  The sheet says 64 on average, behind an even pace.          (flag, 4.3)

CHECK IN  Where are we? [ 71 ] a session  (o) On track ( ) At risk ( ) Off track
          One line: [ Two partner promos booked for November            ]  [Save]

STRATEGY BOARD                                       [+ Block]   Columns: 1 | (2)
 +- Wish and outcome (note, AIs read) ---+  +- Key results (checklist) ----------+
 | 150 a session by December, half from  |  | [x] Pick the Q4 topics             |
 | target accounts ...                   |  | [ ] Book 2 partner promos   -> task |
 +---------------------------------------+  | [ ] Follow up within 48h    -> task |
 +- Obstacles and plan (note, AIs read) -+  +------------------------------------+
 | If sign-ups stall by week 2, then we  |  +- Sign-ups (sheet, drives progress) -+
 | add a partner promo ...               |  | Session | Date | Sign-ups | Source |
 +---------------------------------------+  +------------------------------------+

RAIL
 Projects     Q4 webinar series   2 of 3 milestones                        [+ Link]
 AI on this   Accounts agent  T-46 Pull sign-ups from the export   Working, saved 1h ago
              Claude Code     T-47 Build the follow-up email        Handed off
 Suggested    "Send a reminder 24 hours before"  (Knowledge agent)  [Make it a task] [No]
 Updates      Mon  You: 71 a session, on track. "Two partner promos booked"
              Mon  Accounts agent: added 3 sessions' sign-ups to the sheet
              Sun  Claude Code: follow-up draft proposed; waits for you
 Files        Q4 plan (doc) | Webinar brand guide (Library)                [+ Add]
 What your AI gets for this goal                                           [Preview]
```

What makes it human-in-the-loop:

- **You set the status.** The fill-in is the first thing on the page, and a computed measure
  shows beside your call, never over it.
- **AI suggests, you choose.** Suggested next steps come from the goal coach, the knowledge agent
  and the agents serving the goal. They wait in the rail, and in Catch up as a quick-yes group.
  "Make it a task" asks who should own it: an agent, a tool, or you. "No" is remembered, so the
  suggestion does not come back.
- **You see what AI is doing.** The "AI on this" rail lists each agent and tool working the goal,
  with its task, status and last save. The updates feed puts their notes beside your check-ins,
  and "show only mine" or "only AI" filters it.
- **You see what AI knows.** "What your AI gets for this goal" previews the card an agent
  receives: the goal, its why, the board blocks you shared, and pointers to linked projects and
  files.
- **Ask AI** opens the knowledge agent's side panel with this goal as its context. It can:
  - break the goal into projects;
  - draft a plan for an obstacle;
  - propose a computed measure;
  - find what the Brain already holds on it.

  Everything comes back as suggestions.

### 6.3 The strategy board

A simple board, closer to a one-page planning doc than to Notion:

- **Layout**: one or two columns. Drag to reorder, collapse a block, rename its title. No
  nesting, no colors, no fonts, no custom page properties.
- **Seven block types**:

| Block | What it holds | Where it lives |
| --- | --- | --- |
| Note | Plain rich text: the why, the outcome, obstacles, the plan | A Workspace doc linked to the goal (the app's existing editor) |
| Checklist | Key results or steps; any item becomes a task in one click | On the goal; items that become tasks move to the Tasks sheet |
| Sheet | A new sheet from a template (tracker, metrics, contacts, content calendar) or a linked one, in grid, board or calendar view; any column can drive the goal's progress | A State sheet (BL 8) linked to the goal, also in Workspace > Live context |
| Doc | A longer document, new or linked | A Workspace doc linked to the goal |
| Projects | The linked projects as cards; create one here | Project links on the goal |
| Links and files | Library items, uploads, web links | The Library and Workspace, linked to the goal |
| Decisions | What you decided for this goal, with dates; decided proposals join it | The goal's journal |

- **Templates**:
  - "Plan it" (the default): Wish and outcome, Obstacles and plan, Key results, a progress
    sheet. It is built on mental contrasting (section 14).
  - "Launch": milestones checklist, calendar sheet, projects.
  - "Grow a number": metrics sheet driving progress, experiments board.
  - "Blank".
- **What AIs can read**: each block has one switch, "Your AIs can read this". The template's
  plan blocks start on; new notes start off, so scratch thinking stays private. Shared blocks
  are written to the goal's plan file in the Brain (7), so every AI reads the same text, in the
  app or over MCP. Private blocks never leave the app's database.
- **One home, many doors**: a sheet or doc made on the board is a normal Workspace item with a
  link to the goal. You can find it in Workspace, open it in its own editor, and link it to
  projects too.

### 6.4 Checking in

The fill-in is the same everywhere: on the goal page, on a goal card, on Home, and in any AI chat
("check in on the webinar goal: 71, on track, two promos booked").

- **Fields**: the number or percent (when the goal tracks one), the status (On track, At risk,
  Off track) and one line. Keyboard first, under 20 seconds.
- **Saving** writes your check-in to the goal's journal, a point on its trend line, and an entry
  in the updates feed.
- **Blocked**: "What's in the way?" can become a suggested task in one click.
- **On a project**: the existing "Record progress" form is the same fill-in, writing the
  project's journal (status, current, blockers, next).

### 6.5 A project's page, semi-reflected

Project pages gain what goal pages have, kept execution-first:

```
Q4 webinar series            Serves: Grow webinar attendance        [Record progress]
Objective: three webinars that each bring 150 qualified attendees, and a follow-up
           sequence sales can use                                              [Edit]
Done when: 3 webinars live by Dec 15        2 of 3 milestones        On track
WHERE IT STANDS  Current: session 3 promotion   Blockers: none   Next: send reminders
TASKS            Open 2 | Working 1 | Waiting for you 1 | Done this week 3      [Board]
AI ON THIS       Accounts agent: T-46, saved 1h ago   Claude Code: T-47, handed off
UPDATES          journal lines, agents' saves and task events, newest first
PLAN             (an optional board with the same blocks; empty until you add one)
...then today's sections: Workspace, Files, Your AI on this project, What your AI gets,
Kept with it, the names your AI knows it by
```

| | A goal's page | A project's page |
| --- | --- | --- |
| Leads with | Your strategy and your check-in | Its objective, where it stands, and its tasks |
| Progress | Your call, with a computed measure beside it | Milestones and the journal |
| AI's part | Suggests; works only on tasks you accept or assign | Works its tasks; saves and hands off |
| Board | Always there, from a template | Optional; starts empty |
| Ends | When you call it met or drop it | When it is done or dropped |

The objective is the project's line in every task brief (BL 5.5, the call to action framed), so
an agent reads what output it is chasing before the task itself. Changing it is a baseline
change, with a reason and an undo point, because it reaches every brief in the project. A
project without one gets a one-line nudge on its page when an agent first works in it, and its
briefs use the project's summary meanwhile.

### 6.6 Settings > Alignment (replaces "Your goals")

The first tab in Settings. It has three views: Goals (default), Rules, and How these differ.

```
Alignment
What your Brain is for, the goals that serve it, and the rules every AI follows.
[ Goals ]  [ Rules ]  [ How these differ ]

THE BRAIN'S PURPOSE  (your high-level Brain goal)                  Never ends
"Keep my work straight across every AI I use, without explaining it twice."
How you'll know it's working:  corrections a week 3 (was 7)  |  re-explanations 2 (was 5)
                                                                  [Edit purpose]
YOUR GOALS  (they live in Goals and Projects)                              [Open]
 Grow webinar attendance (On track) | Launch the Gnomon beta (At risk) | Make the Brain trusted

AGENT GOALS                                   Group by: (Owner) Area Status
  KNOWLEDGE AGENT  keeps the Brain healthy; serves the purpose
   o No much-used note goes 180 days unchecked   6 / at most 0   Needs attention  weekly  1 task
   o Your rules reach every brief in their topic 83% / 95%       Off track        weekly
   o Nothing waits in Catch up over a week       0 / 0           On track         daily
   o Questions your AIs ask get answered in a week  1 / 0        Needs attention  weekly
  ACCOUNTS AGENT  serves: Grow webinar attendance
   o Every account row updated within 30 days    92% / 90%       On track         weekly  2 tasks
```

- **Agent goal rows**:
  - the goal in plain words;
  - now versus target;
  - a status word with its color and shape;
  - a small trend line (eight checks);
  - the cadence and open tasks;
  - a thin line on the left showing what the goal serves.
- **Your goals** appear as one line of links; their home is Goals and Projects. With none, the
  line reads "No goals yet: they are optional".
- **Rules view**: what every AI is told:
  - the constitution layers (company, role or agent, person) with their token budgets (BL 5.10);
  - the must-holds by domain;
  - the goals interview's "how" and "never" answers, where they belong.

  If step 3 of the build puts the kernel view somewhere else, G1 moves it here.
- **How these differ**: the explainer in 3.2, with the table in 3.1.
- **Team edition**: a scope switcher shows company, department and team ladders. Company and
  department goals change only through their admins.

### 6.7 An agent goal's drawer

Agent goals open in a side drawer from Alignment, an agent's page or Activity:

```
No much-used note goes 180 days unchecked          [Pause] [Edit] [Retire]
Owner: Knowledge agent   Serves: the Brain's purpose   Checked weekly, Mon 07:00
Why: "The notes AIs use most cause the most wrong answers when they go stale."
Measure     Much-used notes past review: at most 0     Now 6   (trend, 8 weeks)
How it's worked on   The knowledge agent opens a task when this slips (one at a time)
Tasks       T-41 Verify 6 much-used notes   Claude Code   Done Tue
Progress    Mon  Verified 6 notes; 4 need updates, 2 wait for you   (Knowledge agent)
            Tue  Skill figure fixed and proposed                     (Claude Code, for you)
History     Set Oct 9 by you. Target changed Oct 20: "too strict for 300 notes"
```

### 6.8 Setting a goal (the goal coach)

"Set a goal" opens a side panel with a short conversation, on your chosen model, as a background
job like the knowledge agent's. It follows mental contrasting, inspired by Muse: what you want,
the best outcome, what gets in the way, and the plan.

```
You     I want webinars to bring in 150 people a session by December.
Coach   Good. Three quick questions.
        What would reaching it get you?
        What usually gets in the way of sign-ups?
        And if that happens, what will you do?
You     More qualified conversations. Promotion stalls after the first email.
        If sign-ups stall by week two, we add a partner promo.
Coach   Here is your goal page. Change anything before you save.
        Grow webinar attendance to 150 a session, by Dec 15
        Progress: you enter it at check-in (weekly); right now about 64
        Board: "Plan it" with your why, outcome, obstacle and plan filled in
        First steps: 1. Book 2 partner promos   2. Follow up within 48 hours
        Link a project: Q4 webinar series?          [Save goal]  [Edit]  [Start over]
```

- At most three questions, then a draft page with at most three first steps. Every field is
  editable before saving, and the measure picker shows live values.
- For an agent goal, the coach asks how it will be measured and which agent owns it, and the
  result waits for your approval like any alignment change.
- First steps you keep become suggestions you can turn into tasks.
- **By hand**: the same page from a form.
- **Templates** by kind of Brain (the starters in `goals.py`).
- **First run**: after the purpose interview, one tap turns on the knowledge agent's four goals.
  Each line of "What is in motion right now?" becomes a project, and you are offered a goal for
  it.

### 6.9 Activity > Tasks and handoffs (new subtab)

Activity has Requests, Cost and quality, and Changes; this tab joins them. It has two views.

```
Activity   Requests | Cost and quality | Changes | Tasks and handoffs
[ Now ]  [ Timeline ]      Goal v   Project v   Owner v   Tool v

NOW
 Waiting for you (1)    T-44 Answer 3 open questions      from Knowledge agent   2h
 Handed off (1)         T-45 Update the pricing skill  ->  Claude Code, repo contxt
                        not claimed for 26h                       [Remind] [Take back]
 Working (2)            T-42 Keep Northwind current     Accounts agent   Gnomon run
                        last saved 40m ago: "4 of 9 rows refreshed"
 Blocked (0)
 Done this week (5)                                                       [Show]

TIMELINE (one lane per owner, last 7 days)
 You              *------*------>
 Knowledge agent  * . . *----->
 Claude Code                  *-.-*
 Claude app                          *
```

- **Now** is the Tasks sheet's board, filtered. Each working task shows its last save. Dragging
  a card changes its status, but nothing reaches Done without evidence: the app asks for it, or
  offers Dropped.
- **Timeline** draws who did what and when:
  - handoffs as arrows between lanes;
  - saves as small dots on the owner's lane;
  - claims and finishes as marks.

  On a phone it becomes a list by day.
- Clicking any event opens the task's drawer: its card, its saves in order, its runs, proposals
  and outputs.

### 6.10 Agents

- **An agent's page** (Knowledge Work > Agents), from the top:
  1. its kernel (UX 4.9);
  2. "Goals it keeps" (agent goals, with measures and latest notes);
  3. "Goals it serves" (links to your goals or the purpose);
  4. its tasks and handoffs;
  5. its runs.
- **The knowledge agent's page** (Brain > Knowledge agent): its four goals at the top. Each has a
  "Why I'm doing this" link from the actions it ran to the goal that slipped.
- **Overview** (Knowledge Work): each agent's goal status dot beside its heartbeat. "Waiting for
  you" includes handoffs.

### 6.11 Catch up

New kinds of card, following the existing tiers:

| Card | Tier | What it shows |
| --- | --- | --- |
| Handed to you | Needs your judgment | What, from whom, the next step; Start, Hand back or Later |
| Agent goal check-in | Needs your judgment | Why it appeared, the trend, the latest notes, the suggested step; Start, Not now or Change the goal |
| Suggested next steps for your goals | Quick yes, grouped by goal | Make it a task, or No |
| Not claimed for a day | Quick yes | Remind or Take back |

Your own goals' check-ins are not Catch up items; they live on Home and the goal page.

### 6.12 Home

A small strip, and nothing else, so Home stays calm. It shows only what applies; without goals,
only handoffs and agent goals that need you:

- the purpose in one line;
- "Check in on 2 goals", with the fill-in inline;
- at most three agent goals that need you;
- "Handed to you (2)";
- on review day, the weekly review card.

### 6.13 The hand-off composer

```
Hand off T-41
 To   ( ) Knowledge agent  (*) Claude Code, repo contxt  ( ) Codex  ( ) You
 Done when   [The pricing-page skill uses the corrected figure, and you approve it]
 Next step   [Update the figure in the skill and propose the change]
 Drafted from the task's saves and log (edit any line):
   Done so far | Decisions | Open questions | What to load | Must-holds
 [Hand off]                                                  Card: 180 tokens
```

It opens from a task's drawer, a goal's "AI on this" rail, a run's review ("Hand off the rest"),
or any AI chat, where the AI drafts the card, you confirm it, and the AI sends it with
`todos_update`. The composer calls the same engine function as the tool.

### 6.14 In any AI chat

| You say | What happens |
| --- | --- |
| "What's on my plate?" | Lists tasks owned by you and your tool queues, waiting-for-you first |
| "Check in on the webinar goal: 71, on track" | Records your check-in on that goal |
| "Pick up T-44" | Loads the card and claims the task with `todos_update` |
| "Save where we are on T-44" | Saves a progress card with `todos_update`, so the next session or another agent starts from it |
| "Hand this to the Accounts agent" | Drafts a card from the conversation; it goes out with `todos_update` when you say yes |
| "What happened with the stale notes?" | Answers from the task's log and the goal's journal |
| "Set a goal: ..." | Proposes it. One of your goals is set when you confirm in the app or the chat. An agent goal waits in Catch up, because alignment never applies from a chat on its own. |

### 6.15 Empty states, edge cases

- **No goals**: a complete setup, not an empty state. The page is Projects with one quiet line
  about goals, and nothing else about goals appears anywhere until you set one.
- **Pausing a goal** stops its check-in reminders, checks and suggestions. Its open tasks stay
  open.
- **Retiring or dropping a goal with open tasks** asks whether to drop them or keep them under
  their project.
- **Client partitions**: tasks, sheets and boards for a sealed client partition are visible only
  inside it (BL 8.8).
- **Blocked**: needs a reason, and appears in Catch up after two days.
- **A session ends without a save**: the Stop hook or the finishing gate asks for one. If the
  session still ends, the task keeps its last card and shows "no save since" in its feed.

## 7. Engine and data (for the builder)

- **The `goal` kind.** Add it to the one vocabulary in BL2. Decision 2 lists identity, rule,
  fact, decision, procedure, value and project; goals are alignment by BL 6 but have no kind
  yet. Fields:
  - owner (a principal);
  - level (purpose, yours, agent);
  - serves (parent goal ids);
  - scope;
  - progress (entered, computed, or both);
  - measure (kind, signal, parameters, target, direction);
  - due (optional);
  - cadence;
  - status (active, paused, met, missed, dropped, retired);
  - why (the owner's words), started, review_by.

  Goal notes are loaded `manual` and filed under the owner's area, like `you-goals`.
- **The purpose** stays the `you-goals` note (level purpose). Its interview answers keep their
  places:
  - "working" seeds the purpose signals;
  - "in_motion" seeds projects;
  - "how", "never" and "leave_out" show under Rules.
- **Projects.** The project's baseline gains `objective` (a sentence or two on the output being
  chased, about 60 words at most, governed like the rest of the baseline) and `goals` (optional
  links to the goals it serves), and keeps its own done-when, due date and milestones. Workspace
  items gain `labels.goals` beside `labels.projects`. State sheets gain goal links in their
  schema.
- **The objective in briefs.** When a request's working context is a project, or a task belongs
  to one, the brief's call to action (BL 5.5) opens with the project's objective (about 60 tokens
  at most), then the goal's line if there is one. Cards fill their first field from the same
  place, and `gnomon_get_context` with a project as `context` returns the objective first.
- **Goals off until used.** Every goal surface checks whether the Brain has any goals of yours.
  With none, the app shows the projects-only layout, and briefs and cards never mention goals.
- **The goal page** reads:
  - the goal note;
  - its journal;
  - its checks;
  - its linked projects, Workspace items, sheets and Library items;
  - its tasks;
  - the suggestions waiting for it.
- **The board layout** (blocks, order, columns, collapsed, the "AIs can read" switch) is
  presentation. It lives in the app's database keyed by goal id, the same for a project's
  optional board. Block contents live where 6.3 says.
- **Shared blocks** are written to the goal's plan file in the vault (`goals/<goal id>/plan.md`,
  generated, one section per shared block, rewritten on save). The plan file is your own words
  in your own scope, so no approval is needed. A goal's working context and its tasks' cards
  point to it. Private blocks are never written to the vault.
- **Check-ins**: the app writes your check-in to the goal's journal and a point to `goal_checks`
  (source: you). Computed checks write points with source: code. The goal page shows both, and
  the flag rule in 4.3.
- **Suggestions** for your goals are stored like the knowledge agent's suggestions (dismissed
  ones remembered). Accepting one calls `todos_update` with `new_task` on your behalf. The knowledge
  agent's alignment check gathers three new kinds of candidate: your goals with no recent
  check-in, no projects, or an obstacle with no plan.
- **Agents.** AGENT.md's "Goals it serves" becomes links to goal ids, the purpose or your goals.
  Free-text lines that match no goal become suggestions in Catch up: "Make this a goal with a
  measure?". Goals an agent keeps are goal notes it owns. An agent's kernel role layer lists
  those goals, one line each, at most three, about 60 tokens. People's kernels carry no goals.
- **Measures**: `brainkit/measures.py`, the signal library in 4.2. Each signal is pure code with a
  plain-English description. State-based signals, including "a column of a sheet", reuse BL 8.2's
  safe evaluator.
- **Goal checks**: a worker job runs agent goals' checks on their cadence and on demand, and
  computed measures beside your goals. It writes to a `goal_checks` table in the Brain's ledger,
  kept for good. A check only queues a Catch up card under the rules in 4.4.
- **Goal journals**: `journal/goals/<goal id>.jsonl`, append-only, in the same pattern as project
  journals (`brainkit/focus.py`). They are written by your check-ins, the Decisions block and
  `todos_update`'s `goal_note`. No approval is needed, and they are never read as evidence for notes.
- **The Tasks sheet**: a built-in State sheet type (BL 8.2 templates), with the columns in 5.1.
  Owner, Status, Evidence and Card are written only by `todos_update`. Milestone, Goal and Due ask you
  first; the rest take `sheets_propose_update`. Ids are short and human (T-41).
- **The `todos_update` tool** (5.8): one engine function, for example `brainkit/handoff.py`, over the
  State API and the goal journals.
  - It is registered on the Brain's MCP server and on the app's MCP that runs use.
  - It backs the app's composer and `/api/work/handoffs`, so every path is validated once.
  - It refuses a new task for one of your goals unless the caller acts for you.
  - Its description stays near 80 tokens, and saves pass through BL 9's secret masking.
  - Saves and passes are cell events with who said it: the agent run, or the session and the
    person it acts for.
- **Working contexts**: each task, and each of your goals, is a working context (BL 8.3).
  `gnomon_get_context` with `context` set to a task returns the latest card as the brief's call to
  action (BL 5.5). With a goal as `context`, it returns the goal, its why and its plan file as
  pointers. Pointers are resolved and the must-holds in play are added. After a compaction, that
  card is what the brief resends (BL 4.2: deltas only).
- **Pending handoffs**: a first brief, and Claude Code's session-start hook, list them for that
  tool, project or repo, one line each.
- **Reminders**: the run finishing gate checks for a `todos_update` when a run worked a task; Claude
  Code's Stop hook asks for a save when a task is active; first briefs remind in one line.
- **MCP**: one new tool, `todos_update`, joins the core in BL 5.7 (`gnomon_get_context`,
  `notes_search`, `notes_get`, `notes_propose`, `sheets_propose_update`). `gnomon_get_context` returns a task's
  card or a goal's context. `notes_propose` with kind `goal` handles agent goals proposed from a
  chat. Check-ins from a chat go through `todos_update` with `goal` and `goal_note`, marked as yours
  when the session acts for you. The server instructions gain one sentence.
- **App API**:
  - `/api/brain/goals`: the ladder.
  - `/api/brain/goals/:id`: one goal, its checks, journal, links and tasks.
  - `/api/brain/goals/:id/check-in`: your fill-in.
  - `/api/brain/goals/:id/board`: the layout and blocks.
  - `/api/brain/goals/:id/suggestions`: what waits for you.
  - `/api/brain/goals/coach`: the coach conversation, as a background job.
  - `/api/work/handoffs`: compose, claim, remind, take back, through the same function as the
    tool.

  Bus events: goal checked, check-in saved, goal note added, task changed, progress saved,
  handoff sent, handoff claimed, suggestion added.
- **Routes**:
  - `/projects` keeps its address with the new label.
  - Goal pages live at `/goals/:id`, replacing the retired `/goals/*` page (decision 14).
  - Settings `?tab=alignment` (the old `?tab=goals` redirects there) and Activity `?tab=tasks`.
  - An agent goal's drawer opens with `?goal=<id>` on any page.
  - `/tasks/*` stays retired.
- **One word, one meaning.** The code already calls a run's definition a `Task`
  (`services/tasks.py`), and the runner prompt says "complete the task". From G0 on,
  model-facing text says "run" for runs, so "task" means only the new kind. The table and records
  keep their names.
- **Components reused**:
  - the board's sheet block uses UX D's grid, board and calendar;
  - drag and drop uses dnd-kit (UX decision 5);
  - notes use the app's existing rich editor;
  - Ask AI uses the knowledge agent's side panel.

  No new heavy library is needed.
- **System notes**: a new `system-goals.md`, and updates to `system-mcp.md` (the `todos_update` tool)
  and `system-agent.md`.
- **Token budget**:

  | Item | Cost |
  | --- | --- |
  | Goal checks | Code only, free |
  | The coach | One conversation per goal on your model, a few thousand tokens |
  | A card in a brief | About 250 tokens at most |
  | A goal's context | The goal, its why and pointers to its shared plan, about 150 tokens before anything is opened |
  | A pending handoff line | About 20 tokens |
  | A project's objective in a brief | About 60 tokens at most |
  | An agent's goals in its kernel | About 60 tokens |
  | `todos_update`'s description | About 80 tokens where a client loads tool definitions (Claude Code defers them until used) |

## 8. Muse: what we take, and what we change

Meta's Muse (launched September 8, 2026) sets goals by conversation. These details come from news
coverage and third-party guides, not Meta's documentation.

| Muse does | Gnomon does |
| --- | --- |
| You describe the outcome in everyday words, with personal context | Same: the goal coach starts from your words |
| It asks clarifying questions about routine and obstacles | At most three questions, following mental contrasting: what it gets you, what gets in the way, what you'll do then |
| It proposes a plan around a few core problems with gentle first steps you review | A draft goal page: the "Plan it" board filled in, a progress measure, at most three first steps |
| A Goals area, grouped by life area | Goals and Projects, with a page per goal; projects linked to the goals they serve |
| Nudges and check-ins tied to the goal | A weekly check-in fill-in that takes seconds; agent goals speak up only when they slip |
| Work continues in the background; you hear back when input or approval is needed | The same calm rule. The "AI on this" rail and the updates feed show progress without asking anything of you |
| It proposes plan changes when new information touches a goal | The knowledge agent proposes the change; it waits for you |
| One person, self-reported progress | Your call, a computed measure beside it, agents' notes in one feed, owners and scopes, governed changes, handoffs, and a log of who did what |

## 9. Where it fits in the build order

The build chat follows UX section 6 and was on step 3 when this was written. Insert:

| Build step (UX section 6) | Add from this plan |
| --- | --- |
| Step 4: BL2 one statement model, UX C skills | **G0**: the `goal` kind with levels purpose, yours and agent; the project `objective` field at the top of task briefs (if step 3 frames the call to action first, it uses the project's summary until the field lands); "run" instead of "task" in model-facing text |
| After step 5 (BL3), before step 6 | **G1**: Goals and Projects, with the projects-only layout and the new-project form (objective first); goal pages (header, check-in, board with notes, checklists, docs, projects, links and decisions; templates; shared plan files; suggestions; Ask AI; updates feed from journals); Settings > Alignment; agent goals with measures and checks; the goal coach; Home strip and weekly review; projects linked to goals; the knowledge agent's goals and its new gathers |
| Step 6: BL4 State, UX D, UX E | **G2**: the board's sheet block and sheet-driven progress; the Tasks sheet; the `todos_update` tool and its reminders; cards and claims; delivery to each tool; "AI on this" rails; Activity > Tasks and handoffs; project pages semi-reflected (tasks, AI on this, updates, optional board); Catch up cards; State-based signals |
| Step 7: BL5, UX F workflows | **G3**: "Open a task" and "Hand off" workflow steps, verification as tasks, correction signals, team scaffolding |
| Step 8: BL6 proof, UX G walkthrough | **G4**: the evals in section 11, then the walkthrough with a goal of yours, the T-41 story and the interviewees |

A line to give the build chat: "Read `goals-and-handoffs-plan.md` and fold its G0 to G4 into your
steps as its section 9 says; tick them in `build-progress.md`."

## 10. Phases

| Phase | Builds | Done when |
| --- | --- | --- |
| G0 | The `goal` kind and its fields; the project `objective` field and its place at the top of task briefs; "run" in model-facing text | Every existing note reads as before; `brain check` passes; every task brief in a project with an objective opens with it |
| G1 | Goals and Projects with the projects-only layout and the new-project form; goal notes and migration (`you-goals` as the purpose, agents' goal lines); goal pages with the check-in, updates feed, board (notes, checklists, docs, projects, links, decisions), templates, the "AIs can read" switch and plan files, suggestions and Ask AI; project links to goals; `measures.py` with today's signals; `goal_checks`; goal journals; Settings > Alignment; agent goal drawers; the goal coach and the form; Home strip and weekly review; the knowledge agent's four goals, its new gathers and "why I'm doing this" | You set a goal with the coach, see its draft page, check in, and see a suggestion turn into an accepted step, in under three minutes on the demo Brain. A check-in takes under 20 seconds. Only shared blocks ever reach a brief. A seeded agent goal slip makes exactly one card. No goal ever changes a brief's notes |
| G2 | The sheet block and sheet-driven progress; the Tasks sheet and its validation; owners and tool queues; the `todos_update` tool (take, save, pass, finish, goal notes) with its reminders; cards with the agent's words plus what code verifies; claims, reminders and take-backs; pending handoffs in first briefs and the session-start hook; agents' runs from handoffs; "AI on this" rails; Activity > Tasks and handoffs; project pages semi-reflected; Done with evidence; journal lines; milestones | On the demo Brain, a goal of yours gets a checklist item turned into a task for the Accounts agent, whose saves appear in the goal's feed. The T-41 story runs end to end: the knowledge agent, you in the app, a Claude Code session, and the Claude app answering "what happened?" from the log. A session that saved progress is resumed by a fresh session that redoes nothing |
| G3 | Workflow steps "Open a task" and "Hand off"; verification with sources as tasks; correction and output-check signals; teammates as owners and admins for shared goals (scaffold) | A workflow opens, works and hands off a task; the solo app shows nothing of teams |
| G4 | Evals (section 11); the walkthrough; the goal coach and a goal page tried by the two interviewees | Rami signs off |

Every phase follows the build's rules: a branch in `Contxt-safeguards` (never the live checkout),
full checks, a pull request, no auto-merge, and a look on the demo Brain.

## 11. How we will know it works

- **Your goals**:
  - Setting a goal with the coach takes at most five turns and under two minutes on the demo
    Brain.
  - A check-in takes under 20 seconds in the walkthrough.
  - The disagreement flag appears every time a seeded measure and your call disagree, and never
    otherwise.
  - Only shared blocks appear in briefs and cards (100% on a seeded test).
  - Private blocks never leave the app's database.
- **Board restraint**: at G4, count which block types and templates were used. Anything unused
  in the walkthrough and the interviews is a candidate to remove, not to extend.
- **Goals optional**: a demo Brain with no goals shows nothing about goals beyond the one
  invitation line, and its briefs and cards never mention goals (100%).
- **Objectives**: every task brief in a project with an objective opens with it, within about 60
  tokens (100%). On seeded project tasks judged blind, outputs made with the objective in the
  brief are compared with outputs made without it; if they are not better, the objective's place
  in the brief is reconsidered.
- **Measures**: computed values match a reference computation on seeded Brains, 100%.
- **Check-in noise**: agent goals make at most one card per goal per check and none while a
  status holds steady. Over a four-week seeded run, at most one card a week per goal that is not
  off track. Your goals get at most one reminder per cadence.
- **Handoffs**: seeded handoffs go from an agent to you to a Claude Code session, compared with
  handing off without a card. The receiver works from the card alone:
  - it asks for nothing the card already holds;
  - it redoes no done work;
  - it keeps every listed decision.

  The card stays at about 250 tokens or less.
- **`todos_update` in use**:
  - On seeded long tasks, agents save at the moments in 5.8: when blocked, before stopping, when
    passing on, and when finished, at 90% or more.
  - A fresh session resumed from a saved card alone continues correctly, compared with no saves.
  - Invalid calls are refused with a fix every time, including an agent opening a task for one of
    your goals.
  - Duplicate saves do nothing.
- **Integrity**:
  - every Done task has evidence (100%);
  - no owner changes outside `todos_update` (100%);
  - the timeline and the feeds match the logs (100%);
  - when two claims race, one wins (100%);
  - no task, sheet or board leaks across partitions;
  - no secret appears in a card, a goal note or a plan file on the seeded test.
- **No regressions** in the BL gates: brief tokens, noise, needed-note recall.

## 12. Decisions

Decisions 1 to 10 were set on October 9 (prompt 144): approved as recommended, except 9, which
was amended. Rami's notes (prompt 145) revised 8 and added 11 to 14, and his follow-up (prompt 149)
added 15 and 16. Decisions 11 to 16 were approved as recommended (prompt 150).

1. **Where Alignment lives**: Settings > Alignment, the first tab, replacing "Your goals".
   Approved. Since the notes, it holds the purpose, agent goals and rules, and lists your goals as
   links; their home is Goals and Projects.
2. **The word "tasks"** in the app, with runs called "runs" wherever a model reads it. Approved.
3. **Where tasks are managed**: Activity > Tasks and handoffs as the main place; each goal and
   project page shows its slice; the Tasks sheet in Live context for bulk edits. Approved, goal
   pages added.
4. **Agents open tasks on their own** only for agent goals they own: one open task per goal,
   five per agent. Approved. For your goals they suggest and you accept (5.5).
5. **Claiming**: a handoff to a tool waits for a session to pick it up, with your yes in that
   session; a handoff to an agent starts its run within its schedule. Approved.
6. **Done needs evidence**, and no agent can mark a goal met. Approved.
7. **Check-ins**: weekly by default; agent goals send cards only on a slip or a judgment; your
   goals' check-ins live on Home and their page; the weekly review is off until you turn it on.
   Approved, with your goals' check-ins added.
8. **Projects and goals**: revised by the notes. Projects keep their own done-when, due date and
   milestones (tasks marked Milestone) and link to the goals they serve. Goals are yours or an
   agent's, not a project's.
9. **A `todos_update` tool**: agents take, save progress on, pass on and finish tasks, and add goal
   progress notes, in one validated call (5.8). `sheets_propose_update` no longer writes the Tasks sheet's
   Owner, Status, Evidence or Card. Approved as amended.
10. **The purpose in every kernel**: no. Goals reach briefs only as a task's reason or a goal's
    shared plan, and agents' kernels carry their own goals. Approved.
11. **The board's scope**: seven block types (note, checklist, sheet, doc, projects, links and
    files, decisions), one or two columns, four templates, no nesting, colors or fonts.
    Approved.
12. **What AIs can read on a goal page**: the blocks you switch on. The template's plan blocks
    start on and new notes start off, and shared blocks go to the goal's plan file in the Brain.
    Approved.
13. **When your check-in and a computed measure disagree**: your call sets the status and the gap
    is flagged on the page and in the weekly review. Approved.
14. **Addresses**: goal pages at `/goals/:id`, reviving the retired address, with Goals and
    Projects at `/projects`. Approved.
15. **Goals optional, and the label**: the sidebar and page say Projects until you set your first
    goal, then Goals and Projects; with no goals, every goal surface stays hidden. Approved.
16. **Project objectives**: every project gets an objective, a sentence or two on the output
    being chased. Ask AI can draft it and you approve it; it opens every task brief in the
    project; a project without one gets a nudge when an agent first works in it. Approved.

## 13. Risks

- **The board becomes a second Notion.** Seven blocks, no nesting or theming, templates first, and
  a G4 count of what got used, with unused pieces removed rather than extended.
- **Private thinking reaching your AIs.** One switch per block, scratch notes off by default, and
  "What your AI gets for this goal" shows exactly what is shared.
- **Three kinds of goal confusing people.** Different homes and names (purpose in Settings, your
  goals in Goals and Projects, agent goals with their agents), the explainer, and the same ladder
  view in Alignment. Goals are optional, so people who don't need them never meet them.
- **Objective, done-when and goal blurring together.** The objective is the output being chased;
  done-when says when it is finished; a goal is the bigger thing you want, if you want one. The
  new-project form and the explainer each say so in a line.
- **A stale objective steering every task.** It is part of the project's baseline: changed with a
  reason, reviewed on the project's 30-day shelf life (BL 6), and visible at the top of every
  brief.
- **Two truths about progress.** Your call and the measure side by side, the gap flagged, never
  silently resolved.
- **Rebuilding the retired to-do app.** Principle 6 and the creation rules in 5.5; a G4 review of
  what got used.
- **Noise.** Caps on agents' tasks, suggestions grouped in Catch up, check-in rules, collapsed
  saves, the weekly review off by default.
- **Gaming the measure.** Agents cannot edit goals or mark them met; computed measures come from
  code; the quarterly alignment review asks whether each agent goal still fits; pair speed goals
  with quality signals.
- **Saves that say little.** The evals score whether a resumed session needs nothing more, not
  how often agents save.
- **A tool the model forgets.** The finishing gate, the Stop hook and the first-brief reminder,
  not the model's memory.
- **One more tool on every turn.** About 80 tokens where a client loads tool definitions; Claude
  Code defers them until used.
- **A note mistaken for knowledge.** Saves, goal notes and plan files are accounts and plans, not
  approved facts; they never support a note and never instruct.
- **The word clash** with runs. G0's wording change; tests that grep model-facing text.
- **Depends on State.** The sheet block, tasks and the tool wait for step 6. G1 stands on its own.
- **Client data in tasks and boards.** Partitions and scopes apply to sheets, boards and the Tasks
  sheet alike.
- **Muse details** come from third-party guides. Treat them as inspiration, not a spec.

## 14. Research anchors

Each design choice and the research behind it. The figures were checked on October 9, 2026.

| Choice | Research |
| --- | --- |
| Purpose, then your goals, then projects, then tasks | Goal hierarchies: higher-order goals set the reference values lower-order goals pursue (Carver & Scheier 1998, On the Self-Regulation of Behavior) |
| The check-in fill-in, recorded and visible on the page | Monitoring progress raised goal attainment across 138 randomized studies (d = 0.40), and more so when progress was physically recorded or reported (Harkin et al. 2016, Psychological Bulletin) |
| The "Plan it" template, and a coach that asks about obstacles | Mental contrasting with implementation intentions (Oettingen's WOOP: wish, outcome, obstacle, plan). A meta-analysis of 21 studies found g = 0.34, stronger when delivered interactively (0.47) than on paper (0.28) (Wang, Wang & Gai 2021). That is why the coach talks it through instead of handing you a form |
| If-then plans in the template and in push delivery | Implementation intentions (Gollwitzer 1999) |
| Goals with a measure and feedback | Goal setting (Locke & Latham 2002) |
| A project objective at the top of every task brief | Commander's intent: a short statement of purpose and end state lets people keep pursuing it when the plan changes (US joint doctrine, JP 3-0; Army FM 100-8). Specific goals direct effort (Locke & Latham 2002). Each delegated task needs an objective (Anthropic 2025) |
| Goals optional, hidden until you use them | Feature fatigue: capability you do not need still costs usability (Thompson, Hamilton & Rust 2005) |
| The updates feed shows progress, yours and your agents' | Progress in meaningful work was the most common mark of people's best workdays, across nearly 12,000 diary entries from 238 people; setbacks weighed more than progress (Amabile & Kramer 2011, The Progress Principle) |
| A board to think on, not just a form | External representations improve reasoning in more ways than relieving memory (Kirsh 2010, AI & Society) |
| Seven block types, no theming | Feature fatigue: more capabilities win the purchase and lose satisfaction in use (Thompson, Hamilton & Rust 2005, Journal of Marketing Research) |
| Agents suggest, you choose, they act on what you accept | Levels of automation set separately for information gathering, analysis, decision and action selection, and action itself (Parasuraman, Sheridan & Wickens 2000) |
| Approvals and check-ins that mean something | Automation complacency (Parasuraman & Manzey 2010) |
| Cards as cues for resuming work; saving before a stop | Memory for goals (Altmann & Trafton 2002); attention residue (Leroy 2009); context-dependent memory (Godden & Baddeley 1975) |
| One structure for every handoff | I-PASS (Starmer et al. 2014): medical errors down 23%, preventable adverse events down 30% across nine pediatric programs |
| Owners, done-when, verified results | Multi-agent failures come mostly from system design, misalignment between agents and weak verification (Cemri et al. 2025) |
| The card's fields; saving the plan outside the context window | Delegated tasks need an objective, an output format, guidance on tools and sources, and clear boundaries (Anthropic 2025, multi-agent research system) |
| Who is doing what | Transactive memory (Wegner 1987); coordination as managing dependencies (Malone & Crowston 1994) |
| Goals never filter context | Lysenko, and schema-driven distortion (Bartlett 1932), as in BL 7.2 |
| An agent's own account is not evidence | The circular-evidence rule (BL 7.2); illusory truth (Hasher, Goldstein & Toppino 1977) |
