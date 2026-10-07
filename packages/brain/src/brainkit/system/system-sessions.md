---
id: system-sessions
title: Sessions and deduplication
keywords: session id dedup deduplication fresh compaction context handle already delivered
---
Every `get_task_context` call returns a `session_id`. Pass it back on later calls in the
same conversation and the brain will not resend note bodies you already hold; it lists them
under "Already in this conversation" instead. After a context compaction or in a new chat,
pass `fresh: true` (or omit the session id) to receive everything again. The ledger lives in
`vault/.brain/sessions.sqlite` and is never knowledge: the detail of each handout is pruned
after the retention window (90 days by default), while daily counts of each entry's use are
kept for good.
