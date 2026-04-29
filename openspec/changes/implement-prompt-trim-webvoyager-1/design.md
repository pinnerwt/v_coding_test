## Context

The agent loop accumulates every tool-call/tool-result pair in `messages` across all steps. By step 13 of webvoyager-1, `prompt_tokens` has grown from 1,084 to 21,522 (20x). The existing `_compact_messages` function drops early state messages when the total character budget is exceeded, but it does not target old tool-result pairs specifically. The result is that every prior observation snapshot and action result remains in the context window, driving ~6.5s of LLM latency per step.

## Goals / Non-Goals

**Goals:**
- Implement a `trim_history(messages, keep_steps)` function that removes tool-result messages (role `"tool"`) and their paired assistant tool-call messages that are older than `keep_steps` complete action cycles.
- Wire the function into `loop()` so each per-step prompt passes through it before the LLM call.
- Make `keep_steps` configurable via `HISTORY_TRIM_KEEP_STEPS` env var (default: 4).
- Cover the trim function with a unit test that runs in-memory with no LLM or network dependency.

**Non-Goals:**
- Trimming the system prompt or the initial user state message (step 1).
- Replacing or removing `_compact_messages` — both strategies compose (`_compact_messages` enforces the absolute token-budget cap first, and `trim_history` then applies the per-step structured cap for surgical reduction).
- Trimming planning LLM calls in `plan_module.plan` or `plan_module.replan`.

## Decisions

**Decision 1: Step window over character budget**

The trim uses a "keep the last N complete tool-call/tool-result cycles" strategy rather than a secondary character budget. Rationale: the bottleneck is prompt-token count, and token count is driven almost entirely by the volume of tool-result strings accumulated over steps, not by any single large message. A window of N=4 keeps enough recent context for the LLM to stay oriented without retaining stale pages.

Alternative considered: a token-count threshold similar to `_compact_messages`. Rejected because token counting requires a tokenizer or another LLM call; character counting is a proxy that obscures the actual per-step accumulation pattern.

**Decision 2: Locate trim in `loop.py` as a module-level function**

The function is small enough to live alongside `_compact_messages` in `loop.py` without introducing a new file. Adding a `history.py` module would be premature abstraction — there is currently one caller and no other module that manages conversation history.

Alternative considered: `task2/agent/history.py` as a dedicated module. Not chosen — the brief says "no abstractions for hypothetical second callers."

**Decision 3: Trim paired assistant messages together with tool results**

When a tool-result message is dropped, its paired assistant message (the one carrying the `tool_calls` list with the matching `tool_call_id`) must also be dropped. Leaving an assistant message with unresolved `tool_call_id` references causes the OpenAI-compatible API to reject the request with a 400.

Implementation: walk `messages` backwards, identify `role="tool"` entries outside the window, collect their `tool_call_id` values, then strip any `role="assistant"` message whose `tool_calls` list references only those IDs.

**Decision 4: Apply trim after appending the current state message, before the LLM call**

This ensures the current step's state observation is always in the context, and the trim window is counted from the most recent tool results backwards.

## Risks / Trade-offs

- [Risk] Trimming too aggressively may cause the LLM to lose track of earlier navigation decisions, increasing `stuck_repeat` or `no_progress` exits on longer tasks. Mitigation: default `keep_steps=4` retains 4 complete action cycles (typically 4 page transitions worth of context); the env-var knob allows tuning upward if regressions appear.
- [Risk] Mixed tool-call/no-tool-call steps complicate the "step window" counting. Mitigation: the trim counts only messages with `role="tool"` (actual dispatched results), not assistant messages that produced no tool calls.
- [Risk] The benchmark verification (acceptance #2: 2-of-3 runs succeed under 120s) is subject to live-web nondeterminism. Mitigation: 3 independent runs with a 2-of-3 pass threshold as specified in ticket #97.
