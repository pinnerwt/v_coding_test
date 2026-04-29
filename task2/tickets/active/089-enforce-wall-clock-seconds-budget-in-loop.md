---
id: 89
slug: enforce-wall-clock-seconds-budget-in-loop
status: active
tier: 3
urgency: P1
axes:
  pass_rate: 0
  tokens_pct: -25
  latency_pct: -30
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json
- task2/eval/bench/webvoyager_loader.py
related:
- 88
filed_pr: null
merged_pr: null
archived_at: null
trigger: 2026-04-29 — user-driven webvoyager timeout investigation; ticket queue restart
---

89. **Enforce `case["budget"]["seconds"]` as a wall-clock cutoff in `loop()`.** `eval/bench/webvoyager_loader.py:7` declares `_BUDGET = {"steps": 20, "usd": 0.25, "seconds": 120}` for every WebVoyager case, and `_is_near_budget` (`scripts/eval.py:48`) treats `seconds` as a real budget axis when computing the `near_budget` flag. But `agent/loop.py:789` only enforces `for _ in range(max_steps)` — there is no time check inside the step loop. As a result `webvoyager-1` in `20260429_122531.json` ran 321616 ms of LLM-and-DOM work (~322 s, **2.7× the documented 120 s budget**) before tripping the step ceiling, and the slower `20260429_104152.json` run took 372566 ms (~373 s, 3.1× budget). Every wasted second is also wasted prompt tokens (we re-send a 22k-token prefix on every step that runs past compaction — see #88) and wasted USD on the local Qwen endpoint's downstream metering. **Fix:** thread `budget_seconds: float | None = None` into `loop()`; capture `t_loop = time.monotonic()` once before the loop; at the top of each iteration check `if budget_seconds is not None and (time.monotonic() - t_loop) >= budget_seconds: return RunResult(status="timeout", reason="seconds_budget", ...)`. Wire `_run_case` (`scripts/eval.py:268`) to pass `budget_seconds=case["budget"].get("seconds")`. Tests: (1) unit test constructs a stub `LLMClient` whose `chat` sleeps 1.0 s per call and runs `loop(..., max_steps=100, budget_seconds=2.5)` — asserts the result is `status="timeout"`, `reason="seconds_budget"`, and `steps` is between 2 and 4 (i.e. the loop terminates within ~3 seconds, not at 100 steps); (2) unit test asserts that with `budget_seconds=None` (the default) the loop's behavior is byte-identical to today (no regression on fixture cases); (3) regression test asserts `webvoyager-1` in any future run has `latency_ms_total <= 130_000` (120 s budget plus a ~10 s grace for the final step in flight). *Why useful:* even before #88 lands this caps the worst case at 120 s instead of 6 minutes, which by itself is a ~63% latency reduction on `webvoyager-1` runs and lets the suite finish in time for the per-PR baseline diff to compute aggregates without the runner's 600 s default tripping. *Trigger:* 2026-04-29 user-driven webvoyager timeout investigation.
