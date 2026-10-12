# Test the Brain

Settings > Test the Brain is where you run your Brain's tests, watch them run, and see how the
Brain is doing and how it works. It is in every Contxt app. It reads one **results contract**,
so it works with a test Lab you point it at, and, with none connected, with the checks Contxt
can run on your own Brain.

What it never does: it writes no approvals, no bars (gates) and no labels. The only things it
writes are starting and cancelling a run, and which Lab folder it reads (kept in this app's data
folder, on this computer). Everything on it is for the owner only.

## The seven views

1. **Overview**: is the Brain helping? One card per pillar (Retrieval, Briefs, Context
   management, Knowledge agent) with the bars met out of the total, how many with confidence, the
   headline number with its interval and a trend. Then what your Brain adds (with against
   without), what is ready and what waits, label progress, and the report card's lines.
2. **Run**: one button per kind of run the source lists, with what it covers, how long it took
   last time and what it costs. A paid run shows its estimate and needs a second press. The run
   streams live, suite by suite, with failures as they happen, and can be cancelled at any time.
   One run at a time.
3. **Gates**: every bar with its value, interval, what it needs to be, the verdict (met, met with
   confidence, not met, not measured), its trend and its source. Read only. A row opens the cases
   behind it, worst first.
4. **Cases**: one case at a time, drawn for its kind: retrieval and briefs (each note colored by
   its label, with scores and why), outcomes (with and without side by side), worlds (plants found
   and missed), sessions (turns), and a table of expected against got for the rest.
5. **Watch it work**: pick a case, or type a request, and watch it pass through the pipeline the
   way the System Map draws it: stages left to right, the count in and out of each, its time, and
   dots moving along the lanes. Motion only explains, and stops with reduced motion.
6. **This computer**: which steps run here and which fall back, speed against budget, peak memory.
7. **History**: every run, filtered by kind; tick two to compare them (the measures that moved and
   the cases that flipped). Markers show where the engine, the snapshot or the bars changed.

## Without a Lab: the checks on your own Brain

Every Contxt user can test their own Brain. These run on what the engine already has and are
written into the same contract shape in `data/test-the-brain/builtin/results`:

| Run | What it does | Cost |
| --- | --- | --- |
| Health check | `brain check`, read only | free |
| Report card | `brain report`: cost by day and line, brief size by request type | free |
| Your labeled requests | `brain eval`: your labeled real requests and the Brain's own `eval.json`, scored on a second copy of the Brain with a throwaway ledger | free |
| See the difference | one request answered twice by Claude Code on this computer, with and without your Brain | uses your Claude Code plan; needs a second press |

Parts that need the local retrieval engine (build step 3b) say so: "Waits for the retrieval engine
(build step 3b)". They light up when the engine is part of the install: the page checks for it, and
only the stage adapter (`workspace_server/watch.py`, `engine_stages`) reads its record.

## Watch it work, and the test marker

A typed request is routed on this app's own Brain with `record=False`: it writes no ledger row, no
delivery and no usage count, so it counts as no request, in usage or in evals. It is marked as a
test in the reply (`test: true`, client `contxt-test`), so anything that lists it can tell. The
stages main can show come from the routing trace: read the request, admission (must-holds),
wide search, and fit. The gate, the relevance cut and the second pass with the link loop are drawn
as waiting until the engine is there.

A saved case of a connected Lab is drawn from the Lab's own record, and nothing is run again. If a
case's `view` has `stages` (a list of `{id, name, in, out, ms, note, dropped, added}`), they are
drawn as given.

## Safety

- **A run never inherits the app's settings.** The runner starts with only `PATH`, `SYSTEMROOT`,
  `TEMP`, `TMP` and `USERPROFILE`, plus the variables the Lab's contract lists in `env_allow`. A
  contract cannot list a `CONTXT_` or `WORKSPACE_` variable. Tests run with the live storage
  settings loaded write to the live store, so the runner never sees them.
- **A fixed command.** The runner is the executable and arguments from the contract, started
  without a shell, from a folder inside the Lab. An absolute path, a `..` or a link out of the Lab
  is refused, each time before a run (not only when the Lab was connected).
- **One run at a time**, and never while the Lab's own run lock is held. A run's process tree is
  ended on cancel and when the app stops.
- **The live Brain is never under test.** A Lab's folder cannot hold or sit inside this app's data
  folder or Brain. A run started here goes to the Lab's Brain.
- **Real text stays local.** Cases show real text on this computer only. Nothing is exported.

## The contract any runner can follow

The page depends on this contract, never on one test suite. `contract` is a number; the page
refuses a version it does not know and says so.

### `lab.contract.json`, at the root of the Lab's folder

```json
{
  "contract": 1,
  "name": "My Lab",
  "results": "results",
  "runner": {"exe": "bin/lab", "cwd": ".", "args": []},
  "env_allow": ["LAB_CONFIG"]
}
```

`runner.exe`, `runner.cwd` and `results` are relative to the Lab's folder and stay inside it.
`runner.args` goes before every command. The owner points the page at the folder once.

### The runner's commands

Run without a shell from `cwd`, with only the allowed variables:

- `run <kind> [--suite <suite>] --progress <file>` starts a run. It prints the run's id as its
  first line of output and keeps running until the run ends. It appends its events to the
  progress file it was given. It exits at once, with a message on its error output, if the run lock
  is taken or a cost cap would be passed.
- `cancel <run>` stops the run cleanly and writes a `cancelled` event.
- `status --json` prints `status.json` (used when the file is not there yet).

### In the results folder

**`status.json`**, rewritten after every run:

```json
{
  "updated": "2026-10-12T14:03:00Z",
  "engine_ref": "dc4b3c0", "machine_setup": "laptop", "brain": "Lab Brain",
  "run_kinds": [
    {"id": "fast", "name": "Fast check", "covers": "...", "paid": false,
     "last": {"run": "...", "at": "...", "seconds": 212, "usd": 0.0}},
    {"id": "smoke", "name": "Outcomes smoke", "covers": "...", "paid": true,
     "estimate": {"usd": 4.5, "seconds": 900}, "suites": ["outcomes"]}
  ],
  "ready": [{"suite": "retrieval", "setup": "laptop", "state": "ready"}],
  "gates": [{"id": "retrieval.needed_recall.heldout", "name": "Needed-note recall, held out",
             "bar": {"op": ">=", "value": 0.9}, "kind": "hard", "source": "BL 5.9"}],
  "labels": {"labeled": 40, "total": 80, "sitting": {"state": "ready", "minutes": 20}},
  "qualification": [{"step": "The gate", "model": "small", "state": "on",
                     "speed_ms": 40, "budget_ms": 100, "peak_ram_mb": 900}],
  "lock": null
}
```

- A ready `state` is `ready`, `waiting_step`, `waiting_labels` or `pc_only`; `note` says what it
  waits for.
- A gate's `kind` is `hard` (fails a run) or `watch`. A gate belongs to a pillar by its `pillar`
  field, or by the start of its id: `retrieval`, `briefs`, `management` (also `ingestion`,
  `distillation`, `governance`, `updating`, `state`, `goals`) or `agent`.
- `lock` is `null` when free, else `{"run": "<id>"}` (or the run's id).
- `qualification[*].state` is `on` or `fallback` (with `fallback` saying what runs instead).

**`runs/<run>/summary.json`**:

```json
{
  "run": "2026-10-12T14-03_fast_A_dc4b3c0_1a2b3c", "kind": "fast",
  "config": {"engine_ref": "dc4b3c0", "snapshot": "2026-10-10", "setup": "A"},
  "valid": true,
  "metrics": [{"id": "retrieval.needed_recall", "split": "heldout", "n": 45, "value": 0.78,
               "ci": [0.69, 0.86], "gate": "retrieval.needed_recall.heldout",
               "met": false, "met_confident": false}],
  "cost": {"usd_estimate": 0.0, "tokens": 0, "seconds": 212},
  "failing_cases": [{"id": "RT-real-7f3a2c91", "title": "...", "why": "missed a note"}]
}
```

A metric with `outcome.brain_effect` as its id (or `O1`) is shown as what the Brain adds. A summary
may carry `card` (the report card's lines) to fill the Overview. Run ids use letters, digits, the hyphen and the characters `.`, `_` and `:` only.

**`runs/<run>/cases.jsonl`**, one JSON object per line:

```json
{"id": "RT-1", "suite": "retrieval", "kind": "retrieval", "title": "...", "sensitive": false,
 "pass": false, "measures": {"needed_recall": 0.5}, "request": "...", "gates": ["retrieval.noise_share"],
 "view": {}}
```

`kind` is `retrieval`, `outcome`, `world`, `session` or `table`. `gates` is optional: a case that
names none belongs to the gates whose id starts with its suite. The `view` per kind:

- `retrieval`: `request`, `brief`, `notes` (`id`, `title`, `label` one of `needed_delivered`,
  `needed_missed`, `useful`, `noise`, `wrong`, `judge`; `form` `body`, `pointer` or `none`;
  `scores`; `why`), `standards` (`id`, `name`, `pass`), and optionally `stages`.
- `outcome`: `with.text`, `without.text`, `key_points` (`text`, `with`, `without`), `violations`
  (`rule`, `arm`, `text`).
- `world`: `plants` (`id`, `what`, `found`), `false_alarms`, `suggestions` (`text`, `impact`).
- `session`: `turns` (`role`, `text`), `checks` (`name`, `pass`).
- `table` and anything else: `columns` and `rows` (`label`, `expected`, `got`, `pass`).

A line that does not fit is skipped and counted, never fatal.

**`runs/<run>/progress.jsonl`** (and the file named by `--progress`), one event per line:
`start`, `suite_start`, `case_done`, `failure`, `suite_end`, `end` or `cancelled`, each with `at`
and, where they apply, `suite`, `case`, `done`, `total`, `failures` and `message`. Other event
names are shown but not counted.

## Where the code is

- `workspace_server/lab_contract.py`: the typed contract, its checks and the results reader.
- `workspace_server/lab_runner.py`: starting and ending a runner with the short environment.
- `workspace_server/builtin_checks.py`: the checks on your own Brain.
- `workspace_server/watch.py`: the stages of a request.
- `workspace_server/brain_testing.py` and `routes/test_the_brain.py`: the service and its routes
  (`/api/test-the-brain`).
- `apps/web/src/pages/settings/test-the-brain/`: the page.
- `apps/server/tests/stub_lab/`: a tiny stand-in Lab (invented content) the tests run.
