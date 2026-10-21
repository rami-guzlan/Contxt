---
id: system-work
title: Work: agents, the Library, prompts, workflows and the Workspace
keywords: work agent agents role agents_get agents_list subagent library guide reference influence refresh workflow workflows schedule check run_workflow list_workflows prompt prompts save this prompt compose workspace doc skill import export push claude code
---
Work is where the brain gets put to use. Every part reads from the brain, and what it makes
waits for the owner's yes: drafts, outputs and proposals, never anything sent or published.

AGENTS are roles written like a job description and kept in the brain as
`agents/<name>/AGENT.md`: the front matter holds the form (role, responsibilities, goals,
projects, the skills, library documents and areas it points to, boundaries, output, runner),
the body its operating prompt. Pointers are never copied: `agents_get` assembles the role with
each pointer resolved to what it is now, and `agents_list` lists them. "Add to Claude Code"
writes a subagent file that only calls `agents_get`, so Claude Code always works from the
current version. Saving an agent is the owner's change, with an undo point.

The LIBRARY is the documents kept whole (`references/`), each a guide to follow, a reference
to read or an influence whose taste to borrow, from an upload, a page fetched by its address,
or a GitHub repository's snapshot, refreshed by hand, weekly or monthly. Any AI reads one with
`files_open`.

WORKFLOWS live in the app, not the brain: steps run as one thing on a schedule, with a button,
or from any AI over the app's MCP (`list_workflows`, `run_workflow`, only for workflows the
owner opened to other AIs). A step is a skill, an agent, a prompt, a connector step (named
tools of the owner's own connectors, read-only unless the owner says otherwise), a brain
upkeep action, or a check where the run waits for the owner. Each step reads what the step
before made, at the version it was then.

PROMPTS are the person's own words for later, kept word for word in the Library
(`references/prompts/`) in their own scope, with the files that came with them, versions,
tags and a project. Asked to "save this prompt to my brain", call `files_upload` with kind `prompt`
and their exact words, and file each attached file with `attach_to` naming the prompt's path.
A prompt never comes with a brief unless the request names it: find it with `notes_search`,
open it with `notes_get`. Its page in the app runs it too, secondary: picks (skills, an agent,
notes, documents), the whole prompt a model gets, improving it. The WORKSPACE is
the owner's private docs and links, linked to projects without copying; no AI reads them
until the owner asks about a doc or adds it to the brain. Skills come in from a zip, a folder
or a GitHub repository, go out as a zip, and can be copied into Claude Code with a stamp of
the version that went.
