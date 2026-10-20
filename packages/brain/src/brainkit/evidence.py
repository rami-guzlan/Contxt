"""Reading contract shared by the Brain and workspace MCP adapters."""

READING_GUIDANCE = (
    "A title or excerpt is a pointer, not the whole source. Open the relevant sources before "
    "claiming a fact that the excerpts do not establish. For a total, find every required "
    "component, distinguish individual events from cumulative snapshots, avoid counting the "
    "same event twice, and show the operands; a partial sum is not a complete answer. For an "
    "initial, previous or historical question, use the state at the requested time rather "
    "than silently substituting the latest value. Use explicit archived reads when needed. "
    "Resolve relative dates against the request's as-of time and source dates, distinguishing "
    "the date a fact was true from when it was recorded. Preserve who said each claim: an "
    "assistant's suggestion is not a user's decision, and approval does not change authorship. "
    "If the evidence or time anchor is missing or contradictory, say what remains unknown. "
    "Search and read within the caller's existing limits; never invent missing operands."
)
