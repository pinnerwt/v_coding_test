## Context

`task2/agent/loop.py` currently runs as a pure reactive loop: observe → decide → act, with no forward model of the task. The `PlanEvent` schema is already defined in `task2/agent/trace.py` and awaits a producer. The supervisor emits `policy="halt"` as a terminal outcome but has no hook to attempt self-correction at the plan level. Ticket #22 requires closing both gaps.

Existing code surface relevant to this change:
- `loop.py` – observe/decide/act cycle; `_build_system_prompt` constructs the system message; user messages are built inline inside the step loop.
- `supervisor.py` – `Supervisor.handle()` returns `EscalationDecision(policy="halt")` on cap or unknown tier; that result is currently only used by `_locate_with_supervisor` in `loop.py`.
- `trace.py` – `PlanEvent(reason, steps, llm_call_id)` is fully defined; no changes needed.
- `llm.py` – `LLMClient.chat()` is the only call surface needed for the planner.
- `observe.py` – `build_observation()` returns a dict; `plan()` receives this dict as its `observation` argument.

## Goals / Non-Goals

**Goals:**
- `plan.py` module with `plan()` and `replan()` functions and a `Plan` dataclass.
- Loop calls `plan()` once after the first observation; emits `PlanEvent(reason="initial")`.
- Every subsequent decision-step user message includes a "Plan progress" block containing all plan steps (no per-step completion tracking; the LLM decides progress from context).
- Supervisor `policy="halt"` triggers `replan()` on the first occurrence; emits `PlanEvent(reason="replan")`; loop continues with the new plan. Second halt is terminal.
- All four new test cases pass (plus plan/replan unit tests).

**Non-Goals:**
- Per-step completion tracking or a "remaining steps" data structure — the block shows all steps every time.
- Multiple replans, partial replans, or hierarchical plans.
- Persisting the plan to the trace SQLite store beyond the `PlanEvent` event (already handled by `TraceWriter`).
- Changes to `LLMCallEvent` `purpose` values — `"plan"` is already in the literal union.

## Decisions

### D1 — Plan dataclass: stdlib `dataclass` (frozen), not Pydantic

The rest of `loop.py` uses stdlib `dataclass` for `RunResult`. Using `dataclass(frozen=True)` for `Plan` is consistent and avoids adding Pydantic as a runtime concern for this module. Fields: `steps: list[str]`, `expected_end_state: str`.

Alternatives considered: `TypedDict` (no enforcement), Pydantic `BaseModel` (heavier, already used only in `trace.py`).

### D2 — "Remaining steps" = all steps, injected verbatim

The loop injects all plan steps into every post-step-0 user message as a plain-text block:

```
Plan progress:
1. <step 1>
2. <step 2>
...
```

No bookkeeping of which steps are complete. The LLM can infer progress from its own prior actions already present in the message history. This avoids a state-tracking bug surface and keeps the loop simpler.

Alternatives considered: marking completed steps with `[x]` (requires the loop to track which step was "last executed", which is ambiguous when the LLM sequences differently than planned).

### D3 — Planner LLM prompt: JSON output, with fallback for malformed responses

`plan()` sends a one-shot system + user message asking the LLM to return a JSON object `{"steps": [...], "expected_end_state": "..."}`. On `json.JSONDecodeError` or missing keys, the function returns a single-step fallback plan rather than raising, so the loop is never blocked by a bad planner response.

Alternatives considered: tool-call schema (ensures structured output but requires all backends to support tool use in non-tool-call mode; JSON-in-content is universally supported).

### D4 — Replan hook location: in `loop.py`, not inside `supervisor.py`

`supervisor.py` stays as a pure classifier/escalator with no knowledge of planning. The replan trigger lives in `loop.py` where it has access to the LLM client, observation, and the existing plan. A `replan_used: bool` flag on the `Supervisor` instance signals whether the one-replan budget has been spent, and `loop.py` checks `decision.policy == "halt"` to branch.

Alternatives considered: returning a new `policy="replan"` from `Supervisor.handle()` (cleaner signal but requires `Supervisor` to know about the replan budget; couples planner state to locator escalation logic).

### D5 — `_locate_with_supervisor` in `loop.py`: halt detection for replan

Currently `_locate_with_supervisor` raises `LocatorMiss` when the supervisor halts. The loop catches this and records it as an error string. To trigger replan, the loop needs to distinguish "halt during locate" from "ordinary error". The simplest approach: check `supervisor.replan_used` after the error string starts with `Error:` and the supervisor's last decision was `halt`. A cleaner approach: add a `last_policy: str` attribute to `Supervisor` that the loop can read after a dispatch. This keeps the supervisor test surface unchanged.

## Risks / Trade-offs

- **Planner call adds latency and tokens per run.** Mitigation: the planner is called at most twice (initial + one replan); it is a short focused prompt. Cost is visible in `LLMCallEvent`.
- **Malformed planner JSON falls back to a single-step plan.** Mitigation: the fallback is logged via the `PlanEvent`; the loop does not crash. Acceptable for a local Qwen3.5 that may not reliably emit JSON.
- **All plan steps are repeated in every user message.** Mitigation: plans are short (ticket says "short bounded plans"). If the plan is 5 steps × 50 chars, the overhead is ~250 tokens per step — tolerable.
- **Supervisor `last_policy` attribute is non-frozen state.** The supervisor is already mutable (`_attempts` dict); adding `last_policy` is consistent.

## Migration Plan

No data migration required. `PlanEvent` rows will begin appearing in existing `traces_events` tables; old readers that enumerate `AnyEvent` via the discriminated union already handle `PlanEvent` (it is already registered). No API changes.

## Open Questions

None blocking implementation. The design above is fully specified.
