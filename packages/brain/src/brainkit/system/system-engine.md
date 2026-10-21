---
id: system-engine
title: The local retrieval engine, its models and the model service
keywords: retrieval engine local models reranker qwen3 kev decision model gate relevance cut link loop pointers fallback model service lock pinned models why this note audit
---
The RETRIEVAL ENGINE decides what goes into a brief with small local models, when a verified
local model service runs on the machine: a gate (should this request get anything from the
Brain at all?), a wide find with no count cap (a ceiling only protects speed), a relevance cut
(a reranker scores every candidate), a second pass (a decision model asks whether a note adds
anything, contradicts another, is current, and which must-hold domains the request touches), a
link loop (what the survivors name, three rounds at most), and fit (what does not fit the
budget becomes a pointer, never a drop). Must-holds bypass relevance. A request the gate or the
cut finds nothing for gets one line.

WITHOUT A VERIFIED SERVICE (a laptop without a GPU, or no models yet) retrieval runs exactly as
before: keywords and the meaning index. `gnomon_health` says which mode runs.

THE MODELS are pinned in `models.lock.json` (repository, revision, the checksum of every file);
the service refuses any model the lock does not list or whose files differ. `brain models lock`
shows each pin and whether it is here; `brain models pin <name> <folder>` records a downloaded
copy; `brain models serve` runs the service on 127.0.0.1 (the app starts it). Decisions use
System One, Jev's request format, which Kev speaks; relevance uses a rerank interface.

THIS COMPUTER'S SETUP decides the default models: a laptop (16 GB) runs bge-small,
Qwen3-Reranker-0.6B, Kev-0.8B and the Qwen3.5-4B agent; a workstation (a 12 GB GPU or a 32 GB Mac)
Kev-4B and Qwen3.5-9B; a large one Kev-9B and Qwen3.6-35B-A3B; under 16 GB, code and the meaning
index alone. Settings, On this computer, Local models shows the machine, each role's options
(size, RAM, speed here) and lets the person download one, make it the default, remove it, or
check the computer again; a choice that will not fit in RAM is refused with the reason.
Kev-0.8B runs a step only once it qualified for it here: until then the gate falls back to the
reranker's best score, and the second pass is skipped. Claude Code for the knowledge agent is
the person's opt-in once a local agent model is here.

EVERY DECISION is kept in the ledger: each candidate's keyword, meaning and reranker scores, the
decision model's answers, the outcome and its reason, the lock's fingerprint, the gate and each
layer's time. Activity's request view shows "why this note" and "why not that one". The cuts
live in brain.json (`engine.cuts`, with the date and eval run they were fitted on).
