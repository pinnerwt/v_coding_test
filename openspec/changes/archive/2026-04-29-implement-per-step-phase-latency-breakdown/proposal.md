## Why

When `webvoyager-1` step latency cliffs from ~7 s to ~30 s after step 12, the single `latency_ms` number in `step_breakdown` cannot distinguish whether the spike is in observation building (AX-tree CDP traversal), the LLM round-trip, or tool dispatch. The suspected cause is LLM-side prefix-cache invalidation (ticket #88), but it cannot be confirmed from the current JSON output. Splitting the monolithic timing into three labelled phases gives the diagnostic signal needed to confirm or falsify that hypothesis in a single benchmark run.

## What Changes

- `_record_step` in `task2/agent/loop.py` gains a new `latency_breakdown: dict` parameter and writes it as `latency_breakdown_ms` into each `step_breakdown` entry.
- `loop()` in `task2/agent/loop.py` captures three monotonic timestamps — `t_obs_start` (before `build_observation`), `t_llm_start` (before `llm_client.chat`), and `t_dispatch_start` (before the tool-dispatch for-loop) — and computes `observation_ms`, `llm_ms`, and `dispatch_ms` deltas, then passes them into every `_record_step` call site.
- New unit tests (3 scenarios) cover phase-range assertions, the sum invariant, and JSON-schema completeness of all result files.

## Capabilities

### New Capabilities

*(none — this change adds a new requirement to an existing capability)*

### Modified Capabilities

- `agent-loop`: The `loop function` requirement gains a bullet about `latency_breakdown_ms` in `step_breakdown`. A new `Per-step phase latency breakdown` requirement specifying the three-phase timing capture, dict shape, sum invariant, and test scenarios is added.

## Impact

- `task2/agent/loop.py` — `_record_step` signature and all call sites in `loop()`.
- `task2/tests/` — new test file for per-step phase latency breakdown (3 test scenarios).
- `eval/results/*.json` — every result file produced after this change will have `latency_breakdown_ms` populated in each `step_breakdown` entry.
- No external API changes; `RunResult` fields are unchanged.
