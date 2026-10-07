# ai-brain

The Brain engine behind Contxt: curated, scoped, versioned context that every model reads
through one governed interface.

A brain is a folder of plain Markdown files with front matter (the vault), versioned with git.
The engine reads it into memory, routes a request to the notes, procedures and references it
needs, and returns one token-budgeted context packet. Models propose changes; a person, or an
explicit policy, approves them.

```bash
brain --vault path/to/vault status
brain context "Write a headline for our web design service page" --explain
brain inbox
brain mcp            # MCP server on stdio
brain serve          # review UI and JSON API on 127.0.0.1
```

It runs on the standard library alone. `pip install ai-brain[full]` adds exact token counts,
local embeddings for semantic routing, and PDF text extraction.

Documentation lives in [docs/brain](../../docs/brain): architecture, routing, configuration,
governance and automatic capture.
