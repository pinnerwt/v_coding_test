## Context

`task2/agent/loop.py` has a single `_record_step` helper that captures one `step_ms = (time.monotonic() - t0) * 1000` measurement covering the entire observe→decide→dispatch cycle. The call sites for `_record_step` span multiple early-exit paths inside `loop()` (no-tool-call branch, `done`, `fail`, `stuck_repeat`, replan-exhaustion, end-of-loop). The relevant code is:

- `t0 = time.monotonic()` at the top of each loop iteration (line ~806)
- `observation = observe.build_observation(browser, last_actions)` immediately after
- `response = llm_client.chat(messages, tools=TOOLS)` for the LLM round-trip
- `for tool_call in response.tool_calls:` / `_dispatch(...)` for tool execution

Current `_record_step` signature: `(step_num, t0, response, tool_names, per_step, breakdown) -> int`.

## Goals / Non-Goals

**Goals:**
- Capture `observation_ms`, `llm_ms`, and `dispatch_ms` per step with monotonic timestamps.
- Write them under `step_breakdown[].latency_breakdown_ms` as a dict with all three keys.
- Maintain a sum invariant: `observation_ms + llm_ms + dispatch_ms ≈ latency_ms` (±5 ms bookkeeping tolerance).
- Populate `latency_breakdown_ms` on every `_record_step` call site, including the no-tool-call early exit and all terminal branches, so no step entry ever lacks the key.
- Ship three new unit test scenarios covering phase-range assertions, sum invariant, and JSON-schema completeness.

**Non-Goals:**
- Sub-phase breakdown of dispatch (per-tool-call timing is already in `ActEvent` trace events).
- Changes to `RunResult` fields — only `step_breakdown` dict contents change.
- Altering any caller outside `loop.py`.

## Decisions

### Decision 1: Add a `latency_breakdown` parameter to `_record_step`

`_record_step` is the single write site for `step_breakdown`. Passing the dict in as a parameter keeps all serialisation in one place and avoids duplicating the `breakdown.append(...)` logic across call sites.

Alternative: compute the timestamps inside `_record_step` using `t0` plus two more timestamps passed in — equivalent, but adding a dedicated `latency_breakdown: dict` arg is clearer at call sites since each phase's start time is captured at a different scope.

### Decision 2: Capture timestamps in `loop()`, not in helpers

`t_obs_start`, `t_llm_start`, and `t_dispatch_start` are captured inline in the main `loop()` body immediately before the corresponding calls, not inside `build_observation`, `llm_client.chat`, or `_dispatch`. This keeps the timing logic co-located with the loop and avoids threading extra arguments through unrelated function signatures.

### Decision 3: `dispatch_ms` ends at the `_record_step` call, not at the last tool-call boundary

For the no-tool-call branch (where `dispatch_ms` is trivially 0 ms), `t_dispatch_start` is set immediately before the `if not response.tool_calls:` check so that `dispatch_ms` equals zero (no dispatch actually happens). For the normal path, `t_dispatch_start` is set immediately before the `for tool_call in response.tool_calls:` loop and `_record_step` is called after the loop, so `dispatch_ms` covers all tool calls in the step.

### Decision 4: `t_obs_start` replaces `t0` as the "start of step" anchor only for observation

`t0` continues to be used as the step-total anchor (`step_ms = (time.monotonic() - t0) * 1000`) ensuring `latency_ms` is unchanged. `t_obs_start = time.monotonic()` is captured just before `build_observation`, and since `t_obs_start` is set immediately after `t0`, the two differ by at most a few microseconds of bookkeeping — within the ±5 ms invariant tolerance.

## Risks / Trade-offs

- [Bookkeeping overhead] The three extra `time.monotonic()` calls add ~1–3 µs per step — well within the ±5 ms tolerance. → No mitigation needed.
- [no-tool-call path dispatch_ms] When the LLM emits no tool calls, `t_dispatch_start` is set before the `if not response.tool_calls:` guard, so `dispatch_ms = int((time.monotonic() - t_dispatch_start) * 1000)` will be 0–1 ms. This is correct. → Document in test.
- [Multiple `_record_step` call sites] There are ~7 call sites in `loop()`. All must receive the `latency_breakdown` dict; missing one would leave a step entry without the key. → The unit test's JSON-schema scenario will catch any omission.
- [Step 1 plan call overhead] `plan_module.plan()` is called inside the step 1 iteration between `t_obs_start` and `t_llm_start`; its latency is therefore attributed to `observation_ms` for step 1. This is acceptable — plan() is semantically part of "building the initial observation context" and tracking it separately would require a fourth phase. Document as a known quirk.
