# One real connector read, Oct 26, 2026 (the owner's list, item 2)

This was one read of the owner's own account through Claude Code, on a scratch Brain (`F:\contxt-dev\tmp\notion-read`, the empty starter) and not their real one. It was read only, using just the tools Gnomon checks as read-only. Items are reported by count and kind only.

**Notion:** not read. This session's permission check refused it twice (personal data handling). The first time, the owner's approval had come through another session. The second time, the owner's in-session "finish out" did not override it either. The owner switched the test to Google Drive.

## Google Drive, through Claude Code

**Connector search:** Claude Code's account connectors were found (19). claude.ai Google Drive was listed with 11 tools. Gnomon checked 5 of them as read-only and refused the 6 that could change something.

**The read:** nine beats with only Drive on. None read an item.

| Outcome | Beats | Time | What happened |
|---|---|---|---|
| "Claude Code could not reach it just now" | 6 | under 1 s | The beat's own check of the account's connectors saw Drive not connected yet. Account connectors load in the background; the search a second earlier had found it connected. |
| "Claude Code could not load it from your account just now" | 1 | 10 s | Claude Code started, but Drive had not loaded in that run. |
| "Prompt is too long" | 2 | 11 s and 45 s | The run reached Drive and outgrew the model's context. A tool's answer (likely a whole file) had no cap. |
| "Its answer could not be read" | 1 | 6 s | After capping each tool's answer at 8,000 tokens (`MAX_MCP_OUTPUT_TOKENS` for account reads, `runners.py`), the run went through; Gnomon could not parse what it returned. |

**Tokens:** not measured. No beat finished a read, and Claude Code reports usage only for a finished run. The 17,000 to 21,000 token estimate stays unchecked.

**Sign-in and permissions:**
- Drive was signed in.
- Gmail needs signing in again in claude.ai (Settings, Connectors).
- Nothing was sent, posted, created or changed.

## After the race fix

The beat now lists the account's connectors again, fresh, up to twice (`ACCOUNT_RECHECKS`), when one it is about to read is still connecting.

Three more beats with only Drive on:
- none skipped Drive at once;
- one could not load it in its own run;
- two reached a read (17 s and 25 s) and stopped at "Its answer could not be read".

Still no item read, and still no tokens measured.

## What it takes to finish

1. **The race:** fixed (above).
2. **The answer Gnomon could not read:** this needs a look at what the read returned. That holds the owner's Drive content, so it waits for the owner to look, or to say that Claude may.
3. **n8n:** not tried. It needs a Google Drive credential set up in n8n first.
