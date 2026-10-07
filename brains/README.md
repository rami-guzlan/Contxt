# Starter Brains

A Brain to begin from. `uv run contxt setup` copies one into `brain/` (the empty one unless
you pick another), and `uv run contxt demo <name>` runs a demo in a folder of its own so you
can look around without touching your own Brain.

| Starter | What it is |
| --- | --- |
| `empty` | The structure and nothing else: areas for you, your work, people, projects and topics. Start here for your own Brain. |
| `knowledge-company` | Brightmill, a made-up knowledge company for manufacturing operations leaders, as its one-person marketing team runs it: voice and approval rules, audience research, a webinar series, a podcast, content skills. |
| `programmer` | Kai, a made-up backend engineer: the machine, the stack, code style and git rules, services and deploys, an open source release, learning Rust. |
| `entrepreneur` | Riley, a made-up serial entrepreneur: a seed-stage startup and its numbers, a seed round, a past company's lessons, angel checks, an idea pipeline. |
| `personal` | Taylor, a made-up parent: family schedules and a food allergy, the house, the budget, half marathon training, a trip to Japan. |

Everything in the demos is invented: the companies, people, numbers and research. None of
it describes a real organization or person.

Each starter is a folder you can read: `vault/brain.json` declares the areas, scopes and
approval rules; `vault/knowledge` holds the notes; `vault/skills` the procedures;
`vault/references` the longer documents; `vault/journal/focus` each project's progress.

To add a starter, add a folder here with the same shape. The test suite checks every
starter with the Brain's own health check, so a starter that breaks a rule fails the build.
