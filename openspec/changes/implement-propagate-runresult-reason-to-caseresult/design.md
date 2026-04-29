# Design

## Context

`agent.loop.loop()` already sets `RunResult.reason` correctly on every early-termination path:

- `stuck_repeat` — K identical (tool_name, args) calls in a row (`agent/loop.py` `_stuck_buf` check).
- `no_tool_call_repeat` — K consecutive responses with empty tool_calls.
- `seconds_budget` — `(time.monotonic() - t_loop) >= budget_seconds` (line 803-817).
- `no_progress` — N consecutive same-fp + no-successful-action steps (added in PR #148).
- `None` — for `done`, `fail`, `max_steps`-exhausted `timeout`, supervisor halt.

The `RunResult` dataclass and the `RunResultReason` Literal already exist (`task2/agent/loop.py:32-45`). The unit tests under `task2/tests/agent/test_*.py` already cover that `loop()` sets the right value on the right path.

The bug is downstream of `loop()`: `task2/scripts/eval.py:_run_case` invokes `loop()`, captures `run_result: RunResult`, and constructs a `CaseResult` from its fields. But `CaseResult` (lines 102-122) has fields `status, steps, usd, l_tier_counts, validators, prompt_tokens, completion_tokens, latency_ms_total, latency_ms_per_step, step_breakdown, escalations, replans, cache_events, failure_class, failure_detail, skip_reason, canary, near_budget` — there is no `reason` field. So the value is silently dropped before `asdict(r)` serializes the result to JSON.

## Decision 1: typing for the new field

Use `reason: str | None = None`, not `RunResultReason | None = None`.

Rationale: importing the `RunResultReason` Literal alias from `agent.loop` into `scripts.eval` would couple the eval harness to the agent loop's internal type alias. The serialized form is a string anyway (asdict reduces Literal to str), and the validator-style enforcement that already exists for `skip_reason` (constructor-time `ValueError` on unrecognized values) is intentionally NOT mirrored here because the set of valid reasons is owned by `agent.loop`, not by `scripts.eval`. Keeping `reason: str | None` lets future `RunResultReason` extensions land in `agent.loop` without requiring a parallel edit in `scripts.eval`.

## Decision 2: where in the dataclass to add the field

Place `reason: str | None = None` immediately after `failure_detail`. Two reasons:

1. Semantic adjacency — `failure_class` and `failure_detail` already describe the failure shape; `reason` is the loop's own structured reason for the same termination event. Grouping them keeps related fields together in `asdict` output.
2. Default value — placing it after another field that already has a default keeps the dataclass field-default ordering valid (no non-default-after-default error).

## Decision 3: which call site(s) wire `run_result.reason`

Only the success-path constructor at `scripts/eval.py:310-329` (the path after `loop()` returns) wires `reason=run_result.reason`.

The exception-path constructor at `scripts/eval.py:287-297` leaves `reason=None` (or relies on the field default by omitting it). On that path `loop()` never returned a `RunResult` — the run crashed mid-loop, and the `failure_class="tool_error"` + `failure_detail=<exception>` already carry the diagnostic information. Synthesizing a `reason` value on this path would be wrong (no `RunResult` was ever constructed) and forcing the type to be non-None would conflict with the `str | None` typing.

The `skipped`-path constructor (when `run_suite` skips a case for `live_disabled` etc.) similarly leaves `reason=None`; the `skip_reason` field already covers that path.

## Decision 4: test-only stubbing strategy

For the propagation tests, stub the `loop` function inside `scripts.eval` rather than the LLM client — the unit under test is `_run_case`'s wiring, not `loop()`'s reason-setting (which is already covered upstream). Concretely:

- Use `monkeypatch.setattr("scripts.eval.loop", fake_loop)` where `fake_loop` returns a hand-constructed `RunResult(status=..., reason=..., ...)`.
- Build the minimal `Case` and `Budget` arguments needed to reach the success-path constructor.

This keeps the tests fast, deterministic, and focused on the wiring.

For the JSON-shape test, use `run_suite` with a tiny in-memory case list and assert that every case dict in the loaded JSON has a `"reason"` key (value may be `None`).

## Decision 5: backward compatibility of the JSON shape

Adding a new `"reason"` field to the case dicts is **additive** — existing readers that don't know about `reason` will continue to work (they ignore unknown keys). The `score` script, `trends` SVG renderer, `baseline_diff`, and `regression-onset-report` all read named fields and don't validate against an enumerated schema. No downstream reader change is required for this PR. Future readers (e.g. the `/done_pr` step 1b' regression analysis) can opt-in to read `reason` when present.

## Out of scope

- Changing the exception-path constructor at `scripts/eval.py:287-297` to synthesize a `reason` (no `RunResult` exists on that path; the right tool there is `failure_class`/`failure_detail`).
- Adding constructor-time validation that `status="failed"` implies `reason != None` (the `max_steps`-exhausted timeout path legitimately has `reason=None`, and so does `fail` from the planner emitting an explicit `done(success=False)`).
- Adding a `RunResultReason`-typed enum check in `scripts.eval` (covered in Decision 1).
- Updating `score.py`, `trends.py`, `baseline_diff.py` to consume `reason`. Those are follow-ups; this ticket lands the data, downstream consumption is a separate PR.
