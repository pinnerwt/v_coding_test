---
id: 95
slug: propagate-runresult-reason-to-caseresult
status: active
tier: 2
urgency: P1
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/scripts/eval.py
- task2/agent/loop.py
- task2/benchmark/task2-implement-no-progress-stuck-detection/webvoyager/20260429_200118.json
related:
- 89
- 93
filed_pr: null
merged_pr: null
archived_at: null
trigger: "2026-04-29 — /done_pr post-merge analysis on PR #148 found webvoyager-1 case shows status=timeout reason=None despite latency_ms_total=142453 > seconds_budget=120; the seconds_budget reason set by loop() at agent/loop.py:806 was silently dropped because CaseResult has no reason field"
---

95. **Propagate `RunResult.reason` to `CaseResult` and benchmark JSON output.** `agent.loop.loop()` sets `RunResult.reason` to one of `RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat", "seconds_budget", "no_progress"]` on every early-termination exit — but `scripts/eval.py:CaseResult` has **no `reason` field**, so the constructor at `scripts/eval.py:310-329` cannot pass it through, and `asdict(CaseResult)` at `scripts/eval.py:411` writes JSON without it. Confirmed by inspecting `task2/benchmark/task2-implement-no-progress-stuck-detection/webvoyager/20260429_200118.json`: `webvoyager-1` shows `status=timeout latency_ms_total=142453` (i.e. exceeded the `budget["seconds"]=120` ceiling), so `loop()` *must* have hit the `if (time.monotonic() - t_loop) >= budget_seconds` branch at `agent/loop.py:803-817` and set `reason="seconds_budget"` — yet the JSON's case keys show no `reason` field at all (only `failure_class`, `failure_detail`, `skip_reason`). This blinds every post-merge `/done_pr` step 1b/1b' diagnosis: "is webvoyager-1 timing out via wall-clock budget, no-progress detector, max_steps exhaustion, or stuck_repeat?" is currently unanswerable from the artifact, and the question matters for picking the next ticket (a wall-clock timeout argues for prompt/path-length reduction; a max_steps exhaustion argues for a converge-to-done heuristic; a no_progress fp-stagnation argues for fingerprint sensitivity tuning). **Fix:** (1) add `reason: str | None = None` (or `RunResultReason | None = None` if the Literal alias is importable from `agent.loop`) to `CaseResult` in `scripts/eval.py`, immediately after the existing `failure_detail` field; (2) wire `reason=run_result.reason` into the success-path `CaseResult(...)` construction at `scripts/eval.py:310-329`; (3) leave the exception-path `CaseResult(...)` at `scripts/eval.py:287-297` with `reason=None` (no `RunResult` exists on that path). **Tests:** (a) `test_run_case_propagates_reason_seconds_budget` — stub LLM emitting `read({"intent": f"x{i}"})` each step + a `budget_seconds=0.001` so `loop()` exits via the wall-clock branch on step 1; assert `CaseResult.reason == "seconds_budget"`; (b) `test_run_case_propagates_reason_no_progress` — same stubs as `tests/agent/test_no_progress_stuck.py::test_no_progress_bail_after_4_unchanged_fingerprint_steps_no_successful_action` plumbed through `_run_case`; assert `CaseResult.reason == "no_progress"`; (c) `test_run_case_succeeded_has_reason_none` — happy-path stub returning `done` after one step; assert `CaseResult.reason is None`; (d) `test_bench_json_includes_reason_field` — invoke `run_suite` on a tiny in-memory fixture; load the written JSON; assert every `case` dict has a `"reason"` key (value may be `None`). **Done bar:** the next post-merge benchmark JSON has a populated `reason` field on every failed/timeout case; `/done_pr` step 1b' can read it directly when computing per-case regression deltas. *Why useful:* tier 2 measurement correctness — every tier-5 candidate's expected-impact estimate is built on knowing *which* termination path a failing case takes today. Without this, the next iteration's ticket selection on webvoyager-1 cannot distinguish "wall-clock wall hit, prompt-trim helps" from "max_steps exhausted, converge-to-done heuristic helps" — a category mismatch that has burned past iterations (PR #106 ticket #73 picked on a misclassified `tool_calls`-vs-`tools` field; same shape, different cause). *Trigger:* 2026-04-29 — discovered during `/done_pr` post-merge diagnosis on PR #148 (no-progress stuck detection).
