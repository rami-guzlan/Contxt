---
name: tidy-projects
description: The knowledge agent's project check. Reads active projects that went quiet or have no next steps, and drafts the question, the close or the next steps each needs, for the owner to record.
when_to_use: Projects drift when nobody records progress. Run it weekly.
triggers:
  - check my projects
  - which projects went quiet
  - tidy my projects
artifacts: []
loads: []
quality_gates:
  - next steps come only from what the project's own updates say
  - a project is suggested closed only when its updates say it is done
---
# /tidy-projects

You get the map of the Brain and candidates, each one active project with a reference (`c1`,
...): its status, where it stands, its next steps and its last updates.

## For each project, decide

- `next-steps`: its updates say what comes next but no next steps are recorded. Draft them
  (`"text"`, a short list), only from what the updates say.
- `close`: its updates say it is done, delivered or cancelled, yet it is still active.
- `ask`: it went quiet and nothing says why. Write the one question that would bring it up to
  date (`"text"`).

Never invent progress, dates or owners. Projects keep an append-only journal: you only suggest;
the owner records.

## Answer with one JSON object only

```json
{"summary": "1 to close, 2 to bring up to date.",
 "findings": [
  {"ref": "c1", "verdict": "close", "why": "The last update says the launch went out."},
  {"ref": "c2", "verdict": "ask", "text": "Where does the podcast relaunch stand?", "why": "No update in five weeks."},
  {"ref": "c3", "verdict": "next-steps", "text": "- Send the draft to the editor\n- Book the studio", "why": "The last update names both."}
 ]}
```

Every candidate gets one finding; `why` is one short sentence.
