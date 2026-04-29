---
id: 100
slug: webvoyager-2-fast-fail-to-slow-timeout-regression
status: active
tier: 5
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: -30
  latency_pct: -25
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-surface-tool-error-exception-detail/webvoyager/20260429_232832.json
- task2/benchmark/task2-fix-trim-history-preserve-first-group/webvoyager/20260429_225802.json
related:
- 99
- 98
filed_pr: null
merged_pr: null
archived_at: null
trigger: "2026-04-29 — /done_pr aggregate-axes regression check on PR #156 (surface-tool-error-exception-detail). webvoyager-2 status flipped from `failed/tool_error/steps=5/$0.0419` to `timeout/None/steps=11/$0.1375`; aggregate axes regressed +52.7% cost, +53.3% tokens, +36.9% latency vs the prior `task2-fix-trim-history-preserve-first-group` baseline (pass_rate unchanged at 1/3)"
---

100. **Add an early-termination heuristic for webvoyager-2's slow-timeout pattern — case now exhausts the wall-clock budget at 11 steps instead of fast-failing at 5 with `tool_error`.** The fix landed in PR #156 (#99 acceptance gate) replaces the literal `failure_detail='unknown error'` string with the underlying exception class+message, so the LLM now receives actionable error text in the tool result. With a real error message in hand the planner takes a different path each step (so the `K=3 byte-identical tool calls` detector never fires) and the loop runs to wall-clock timeout instead of the prior fast-fail at step 5. Net effect: pass_rate is unchanged (1/3) but webvoyager-2 alone added +6 wasted steps × ~$0.013/step, driving the cost/tokens/latency regression. **Goal:** install a stuck-state detector that catches "K consecutive tool errors with monotonically growing observation_size and no successful action" — the canonical fast-fail-after-real-error shape — so the case classifies as `failed/stuck_repeat` (or similar) at ≤6 steps instead of running to wall-clock timeout. **Tests (TDD):**
- *Red:* extend `task2/tests/agent/test_loop.py` with a test that drives the loop with K=3 consecutive `ActEvent` outcomes in `{"timeout","error"}` (each with a populated `diff["error"]`) where no `outcome="ok"` or `"nav"` is interleaved. Assert that the loop terminates at iteration 4 (or whatever K boundary is chosen) with `RunResult.reason` starting with `"stuck_repeat"` (or similarly named) and the run does NOT proceed to wall-clock timeout.
- *Green:* add a counter in `agent/loop.py` that increments on each `outcome in {"timeout","error"}`, resets on `outcome in {"ok","nav"}`, and triggers early termination when the counter reaches K (suggested K=3 to match the existing identical-tool-call detector). The counter SHALL be independent of tool-call identity — the K=3 byte-identical detector handles the "same call repeated" pattern; this detector targets the "different calls, all failing" pattern.
- *Benchmark gate (manual, post-merge in `/done_pr`):* webvoyager-2 SHALL either (i) succeed (pass_rate recovers to 2/3), OR (ii) fail with `status=failed/stuck_repeat` (or equivalent) at ≤6 steps with cost ≤$0.06 — bringing aggregate cost/tokens/latency back within ±10% of the `task2-fix-trim-history-preserve-first-group` baseline.

**Done bar:** unit tests green; smoke test pass; post-merge benchmark capture shows webvoyager-2 either recovers to succeeded OR fails fast at ≤6 steps with a concrete `failure_class != "tool_error"`. *Why useful:* tier 5 axes-regression follow-up — PR #156 satisfied #99's acceptance gate (no more `'unknown error'` literal) but inadvertently traded a fast-fail for a slow-timeout, costing +52.7% on the run total. The detector is small (~10 lines in `agent/loop.py` plus a regression test) and unblocks future iterations from re-litigating webvoyager-2's per-case cost. *Trigger:* /done_pr's aggregate-regression check on PR #156, which observed the three-axis regression without a pass-rate movement, with per-case localization isolating wv-2 as the sole driver.
