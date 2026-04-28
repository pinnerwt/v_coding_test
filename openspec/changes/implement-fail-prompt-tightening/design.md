## Context

`_build_system_prompt` in `task2/agent/loop.py` (lines 223-231) returns a single string that is placed as the system message for every loop invocation. Its current closing sentence — "If you cannot complete the task, call `fail` with a reason." — is unconstrained: the model treats any uncertainty as sufficient cause to emit `fail`. Benchmark data from 2026-04-28 shows this pattern fires on step 2 of a 5-step budget across multiple drift/correction cases, burning the remaining budget without attempting available tools.

Ticket #62 (commit 243a545) already provides a structural runtime gate (`premature_fail` SupervisorEvent) that intercepts `fail` on step ≤ 1 with no prior interaction. This ticket tightens the prompt phrasing so the model learns the correct policy upfront rather than relying solely on the gate.

## Goals / Non-Goals

**Goals:**
- Replace the current `fail` guidance sentence with explicit phrasing that names the irrecoverable conditions allowed and requires an action-first attempt otherwise.
- Add a string-shape lock-in test asserting the new phrasing is present in the prompt returned by `_build_system_prompt`.

**Non-Goals:**
- Implementing a behavioral retry/nudge test (path (a) from ticket #61) — that is already covered by #62's test suite.
- Changing any logic in the agent loop beyond the string edit.
- Modifying the `_IRRECOVERABLE_REASONS` frozenset or the pre-flight gate logic (owned by the `fail pre-flight validation gate` requirement).

## Decisions

**Decision 1 — path (b) string-shape test, not path (a) behavioral test.**
Because #62 already owns the behavioral nudge/retry coverage, adding another behavioral test here would duplicate that surface. A lightweight string-shape test is cheaper, deterministic (no LLM stub needed), and directly verifies the only output this ticket produces.

**Decision 2 — edit `_build_system_prompt` in-place, no new abstraction.**
The function is the sole builder of the system prompt; extracting a separate `_fail_guidance` constant would be an abstraction with no second caller. A one-line replacement inside the existing f-string keeps the diff minimal.

**Decision 3 — exact replacement phrasing from ticket #61.**
The ticket specifies the target wording verbatim: "Call `fail` ONLY for irrecoverable conditions — login walls, captchas, pages that don't exist, or required information genuinely absent from the page. If a target element exists on the page but you don't know how to act on it, attempt `click`/`type` with a natural-language `intent` first; the locator pipeline will resolve it." This wording is used as-is to lock in the test anchor.

## Risks / Trade-offs

[Risk: future prompt refactoring silently reverts the wording] → Mitigation: the string-shape test (`assert "ONLY for irrecoverable" in prompt`) will immediately catch any reversion.

[Risk: the new phrasing is longer and slightly increases token count] → Acceptable; the sentence is < 60 tokens and the system prompt is sent once per run.

## Open Questions

None. The target phrasing is specified in the ticket; the test approach (path b) is confirmed by the context note that #62 has already landed.
