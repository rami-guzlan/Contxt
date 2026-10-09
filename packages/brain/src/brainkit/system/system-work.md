---
id: system-work
title: Work: agents, the Library, workflows, Compose and the Workspace
keywords: work agent agents role get_agent list_agents subagent library guide reference influence refresh workflow workflows schedule check run_workflow list_workflows compose prompt workspace doc skill import export push claude code
---
Work is where the brain gets put to use. Every part reads from the brain, and what it makes
waits for the owner's yes: drafts, outputs and proposals, never anything sent or published.

AGENTS are roles written like a job description and kept in the brain as
`agents/<name>/AGENT.md`: the front matter holds the form (role, responsibilities, goals,
projects, the skills, library documents and areas it points to, boundaries, output, runner),
the body its operating prompt. Pointers are never copied: `get_agent` assembles the role with
each pointer resolved to what it is now, and `list_agents` lists them. "Add to Claude Code"
writes a subagent file that only calls `get_agent`, so Claude Code always works from the
current version. Saving an agent is the owner's change, with an undo point.

The LIBRARY is the documents kept whole (`references/`), each a guide to follow, a reference
to read or an influence whose taste to borrow, from an upload, a page fetched by its address,
or a GitHub repository's snapshot, refreshed by hand, weekly or monthly. Any AI reads one with
`get_reference`.

WORKFLOWS live in the app, not the brain: steps run as one thing on a schedule, with a button,
or from any AI over the app's MCP (`list_workflows`, `run_workflow`, only for workflows the
owner opened to other AIs). A step is a skill, an agent, a prompt, a connector step (named
tools of the owner's own connectors, read-only unless the owner says otherwise), a brain
upkeep action, or a check where the run waits for the owner. Each step reads what the step
before made, at the version it was then.

COMPOSE shows the whole prompt a model gets for a request and what was picked with it (skills,
an agent, notes, documents, a project), improves it, runs it and saves it. The WORKSPACE is
the owner's private docs and links, linked to projects without copying; no AI reads them
until the owner asks about a doc or adds it to the brain. Skills come in from a zip, a folder
or a GitHub repository, go out as a zip, and can be copied into Claude Code with a stamp of
the version that went.
