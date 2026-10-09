# Safeguards: results by phase

The same cases as the baseline (`docs/evals/safeguards-baseline.md`), rerun after each phase
with `scripts/safeguards_eval.py`. CI runs them by words only
(`packages/brain/tests/test_safeguards_eval.py`).

## Phase A: must-holds

Eight demo constraints became must-holds (`load: domain`, with their domains, trigger words
and one line each); the peanut allergy is also critical. The three that apply to all of their
Brain's work (approvals, secrets, sourced claims) stay standing.

| | Baseline (relevance alone) | Must-holds, words only | Must-holds, words and meaning |
| --- | --- | --- | --- |
| In-domain requests (88) | 47% | 100% | 100% |
| Held-out requests (24) | | 79% | 83% |
| Decoys including the constraint (44) | 7% | 2% | 2% |

The held-out requests were written after the trigger words were fixed and were never used to
tune anything. The router's two thresholds for this (a request's best topic at 0.25, its
second at 0.35, and closeness in meaning to a must-hold's domain at 0.57) were set from the
tuning requests and decoys only.

Still missed by held-out requests: "Should we get a second car?" (budget), "Book a cabin in
the mountains for New Year's" (travel), "Can I get the fix out before the weekend?" (deploys)
and "Who should get the webinar invitation?" (who we do not target), plus, by words only,
"Write the September update for the people who invested in Loopline" (investor updates).
Each needs a broader trigger ("car", "cabin", "get it out", "invitation", "invested"), which
is what the knowledge agent is now asked to propose and what the owner can add on the note.

The one decoy that brings a constraint in, "Summarize the last customer interview", reaches
the customers area, so "who we do not target" comes along as one line.

A fairness note: the same person wrote the triggers and the tuning requests. A stronger test
is triggers proposed by the knowledge agent, judged on requests written by someone else.

## Phase B: the baseline check

Every note proposal is now read against the notes it may disagree with: the most relevant
ones, every baseline where it goes (a rule, a must-hold, a standing note, a note the owner
confirmed, a note AIs used in 10 or more conversations this month), and every note that
gives a figure for the same thing. Checks 1 and 2 (words, figures, names, polarity) run at
once; check 3, the owner's own AI reading each pair through Claude Code with the app's prompt,
runs in the background.

| Detector | Tuning pairs (60, 24 contradictions) | Held-out pairs (20, 8) |
| --- | --- | --- |
| The sentence heuristic the review started from | 38% recall, 82% precision | 62%, 71% |
| Checks 1 and 2 | 58%, 100% | 50%, 80% |
| Check 3, your own AI | 100%, 100% | 100%, 100% |
| Checks 1 to 3, as the app decides | 100%, 100% | 100%, 100% |

Ordinary notes held by checks 1 and 2 (each live demo note proposed against the rest of its
Brain, where nothing disagrees): 32 of 81 (40%) with the first version, 4 of 81 (5%) now.

What that took, and what it means:

- **The pairs hid the false alarms.** The labeled pairs are short and close, and checks 1 and
  2 scored 71% recall at 100% precision on them at first. In a lived-in Brain, though, notes
  about the same people and days share words all the time, and two in five ordinary notes
  read as disagreeing with something. Checks 1 and 2 now compare two sentences only when they
  share content words that make up enough of the shorter one (people, places, days and times
  of day no longer count as what a sentence is about), and a figure disagrees only when the
  two give no value in common. The thresholds were set on the tuning pairs and the demo
  Brains' notes.
- **The held-out pairs were scored once before that.** They were written after checks 1 and 2
  were first fixed: 62% recall at 71% precision (5 of 8, two false alarms: a narrower case,
  and two notes naming the same Saturday practice). The run exposed a bug (plural day names
  counted as names), fixed since, and the overlap bar came after it, so the held-out numbers
  for checks 1 and 2 are no longer a clean held-out measure.
- **Check 3's verdicts were asked once**, on October 8, 2026, through Claude Code 2.1.272 on
  this computer, one pair per call with the app's prompt (80 calls, about 7 seconds each). It
  named the exact relation in 79 of 80 pairs. The verdicts are saved in
  `docs/evals/tension-verdicts.json`; the tests score those, so CI never calls a model. Another
  model or version may score differently: rerun with `scripts/safeguards_eval.py --ask-model`.
  The pairs are invented and easy next to real notes, and in the app the model reads one
  proposal beside up to eight notes at once, which single pairs do not test.
- **Nothing that goes in on its own is unseen.** Of the 24 contradictions, proposed in the
  owner's own scope against a rule (`test_baselines.py`), 14 wait at once (checks 1 and 2);
  the other 10 go in and are queued for the model, which then shows "Went in, but disagrees"
  in Catch up with one tap to take it back. A change to a baseline itself never goes in on
  its own.
- **What is built and tested:** a reason of four words or more for every baseline revision
  (approval or an edit on the note's page), never the one given last time, kept in the journal
  as `baseline_revised`; the impact of a rule, standing note or must-hold before it changes
  (conversations in 30 days, the latest requests, the domains); an optional day to think
  (`revision_delay`: the revision goes in 24 hours after the decision unless cancelled, applied
  by the worker); Catch up's "Changes a baseline" card (never in a quick group, choices only
  after the two are compared), "Both hold", and "Went in, but disagrees"; the seconds each card
  was shown, a plain word after five quick yeses in a minute, and two "Still right?" spot checks
  a week on what went in on its own or was kept in under four seconds; the share of approvals
  taken back within 30 days on Home.
- **Not built here:** the second approver for rules and must-holds belongs to the team edition.
  Check 3 runs only with Claude Code installed and signed in (at most 60 pairs a day); with
  Codex alone, checks 1 and 2 stand, and cards say no AI has read the pair yet.

## Phase C: time-aware briefs

Notes can say the day a changing value was true (`as_of`) and the last day it holds
(`valid_until`). When two dated notes (an `as_of`, or a state note) give different values for
the same thing, a brief carries the newest, labelled "as of", in the place of whichever was
picked, and lists the older ones under "Older values (not current)" by name and date, without
their text.

| | Baseline (Phase 0) | Phase C |
| --- | --- | --- |
| Dated cases where the brief carries the newest value and no unmarked older one (5) | 1 | 5 |

Two of the five were not about ranking at all: a question about a project ("How much of the
seed round is committed so far?", "Which version of tidyq is current?") got the project's
state and nothing else, so neither value reached the brief. A project question now also gets
the newest dated values close to what it asks (relevance 0.45 or more, at most three).

A newer dated value for the same thing is an update, not a disagreement: it never holds a
change that would go in on its own, never raises a "Changes a baseline" card, and Catch up
offers to retire the older note ("A newer value", two a week). Past `valid_until`, a note is
stale like any other (still found, flagged, and back for a check). The knowledge agent is asked
for `as_of` whenever a statement gives a figure that changes.

Limits: two values count as the same thing when a sentence in each shares content words and
gives a figure of one kind; a value given without a figure ("almost done") or spread over
several sentences is not matched. Undated facts that disagree are still a disagreement for the
baseline check, not history. The spec's second check for this phase, rerunning the film's
three-lane test, was not rerun here.

## Phase D: run anchoring

Work (multi-step workflows) is not built yet, so anchoring went into the runs the app already
starts: AI work on a task through Claude Code on this computer (finding what to remember,
reconciling, merging, running a skill that makes files).

- **A contract per run**: the objective (the task's title and purpose), its checks (claim
  first, propose with the tool the task names, finish with complete_task or a blocker, publish
  nothing), the must-holds a brief for the task would carry, its scope (the one folder it may
  touch when it works with files) and its budget (60 tool calls and the run's time limit). The
  run's prompt opens with it, and the run's record keeps it.
- **Claude Code's own hooks**, from a settings file made for the run and passed with
  `--settings` (`brainkit/hooks/run.py`). Before each tool call, a file outside the run's
  folder, a guarded shell command, or any call past the budget except the finishing ones is
  refused. After each tool call, the contract comes back every 8 calls, and a must-hold's line
  as soon as a tool's input or output uses one of its trigger words. When the run would stop
  without finishing, it is sent back once with what is missing.
- **The app's MCP replies** to a run end with the contract's line on the first call and every
  fifth, whatever CLI makes the calls.
- **The record**: tool calls, re-anchors, what was blocked and the finishing check, read from
  the hooks when the run ends, shown as one line in the run's console and kept on the run.

Checked on this computer with Claude Code 2.1.272: in `--restricted` mode it runs PreToolUse,
PostToolUse and Stop hooks from a settings file passed with `--settings`, and the context a
PostToolUse hook adds reaches the model (it quoted the added line back).

Not measured, and not built: the spec's drift set (anchored runs against unanchored ones on
the same tasks) needs Work's multi-step runs to mean something, and so do drift judged by
meaning and a model judging the output at the gate. Today's runs are a handful of tool calls,
so the cadence re-anchor rarely fires; the scope checks, the must-hold line and the finishing
gate are what matter now. Whether a run's output breaks a must-hold is not checked by a
model yet; the line is put in front of it at the moment its domain shows up.

## Phase E: dissent and challenge

- **Challenges are governed proposals** (`note.challenge`): a note, a claim, its evidence and
  its source, from any AI (`challenge_note` on the Brain's server, `propose_challenge` on the
  app's). They always wait. Accepted, the note is disputed and keeps the challenge as its other
  view; turned down, the same claim on the same evidence is refused, and new evidence is
  taken.
- **Briefs**: a disputed note with an other view brings it along ("Contested: ...") into
  planning, strategy and decision work, and stays a flag for a lookup (tested both ways).
- **The internal cross-check**, on by default: the notes AIs use most and the baselines
  longest since checked, read against other notes, quoted sections of filed documents, and
  proposals that say otherwise, waiting or turned down in the last 90 days. Words and figures
  read every pair; the owner's own AI reads three pairs a week, closest first, and its verdict
  wins. Catch up shows at most one belief a week; settling it (still right, or disputed) keeps
  that finding away for 90 days.
- **The external challenger** is offered once the Brain has 25 baselines or a baseline comes
  back stale, and never runs until it is turned on. Then, once a week, Claude Code gets the
  three highest-impact beliefs, each only as a claim under test (its task's packet carries no
  Brain context), with the web as its only extra tool, under a run contract, and what it finds
  comes back as challenges.

Measured on eight wrong beliefs seeded into the four demo Brains (an outdated price, version,
schedule or amount, a reversed decision or rule), each with evidence elsewhere in the same
Brain (another note, a waiting proposal, or one the owner turned down). A case succeeds when the
belief is among the first two the cross-check shows (two weekly cycles), with that evidence:

| | Seeded beliefs found in two weeks (8) |
| --- | --- |
| Words and figures alone | 6 (75%) |
| With your own AI's weekly pairs (six in two weeks) | 8 (100%) |

- The two that words and figures miss need meaning: a send day that moved (days are not
  figures) and a rule reversed in other words. The model read both.
- Two choices were made while measuring, both general: findings are ranked by baselines first,
  then the most used, then the longest since checked (the spec's order; ties had fallen to
  alphabetical order, which put one seeded belief third), and each belief's evidence is read
  closest first. The seeded beliefs are dated months back, since an outdated belief is an old
  one. In every case the seeded evidence was the closest text to its belief, so the model read
  it first by construction: real evidence will often be less obvious.
- On the demo Brains as they are, the cross-check shows 4 findings by words and figures
  (personal 1, programmer 2, knowledge company 1), each one a person would clear for nothing;
  in the model run, its pairs read those as extending or agreeing, which clears them.
- The model run (October 9, 2026, Claude Code 2.1.272) is saved in
  `docs/evals/seeded-beliefs-model.json`; the tests read it, and score words and figures live.
- Not measured: the external challenger (the seeded beliefs are invented, so the web cannot
  speak to them; it needs real beliefs to test). The team edition's parts (department scopes,
  dissent from every member's AI, monoculture signals, two-person approval) belong to the
  private repository.
