## Why

The `_build_system_prompt` function in `agent/loop.py` currently ends with "If you cannot complete the task, call `fail` with a reason." This open-ended phrasing invites the model to emit `fail` the moment it is uncertain, even when actionable tools remain unused. Benchmark analysis on 2026-04-28 shows that every drift/correction failure emits `fail` on step 2 of a 5-step budget, masking real `LocatorMiss` failures and wasting the agent's remaining budget.

## What Changes

- The trailing sentence of `_build_system_prompt` is replaced with tightened phrasing that gates `fail` to irrecoverable conditions only and instructs the model to attempt `click`/`type` first when a target element is visible.
- A string-shape lock-in test is added (path b from ticket #61) asserting that the system prompt contains the "ONLY for" phrasing and the action-first guidance. Path (a) (behavioral retry/nudge test) is out of scope — the structural premature-fail guardrail from #62 (commit 243a545) already provides the runtime backstop.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `agent-loop`: Add a new requirement capturing the required content shape of the system prompt's `fail`-guidance sentence (the existing `_build_system_prompt` function). No existing requirement title covers this content; this is a net-new requirement on the prompt string.

## Impact

- `task2/agent/loop.py` — one-line edit to the string returned by `_build_system_prompt`.
- `task2/tests/agent/` — one new test file (or addition to an existing sibling) asserting the system prompt string shape.
- No API surface changes; no dependency additions.
