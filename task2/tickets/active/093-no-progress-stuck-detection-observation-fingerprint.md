---
id: 93
slug: no-progress-stuck-detection-observation-fingerprint
status: active
tier: 5
urgency: P2
axes:
  pass_rate: 10
  tokens_pct: -20
  latency_pct: -25
dependencies:
- 91
pre_flight_gates: []
evidence:
- task2/benchmark/task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json
- task2/agent/loop.py
- task2/agent/observe.py
related:
- 88
filed_pr: null
merged_pr: null
archived_at: null
trigger: 2026-04-29 — user-driven webvoyager timeout investigation; ticket queue restart
---

93. **No-progress stuck detection: bail when N consecutive steps share the same `ax_fingerprint` and emit no successful action.** `webvoyager-1` in `20260429_122531.json` steps 13-20 calls `read / click / click / read / read / goto / read / read` — 8 steps, 8 different tool names with varying intents — and makes zero forward progress; the run still ends `status=timeout` at step 20 with no answer. Today's `_stuck_buf` (`agent/loop.py:982`) only fires when **the same tool name with byte-identical JSON args** is called `_STUCK_REPEAT_K=3` times in a row. That guard is correctly *not* tripping here because the args differ each step, but the human-readable signal — "the AX-tree fingerprint is unchanged and no `click`/`type` succeeded" — is screaming. **Fix:** add a parallel buffer keyed on `(ax_fingerprint_post_step, any_action_succeeded_this_step)` where `any_action_succeeded_this_step` is true iff a `click`/`type` returned `outcome="ok"` or `outcome="nav"` in the dispatched tool calls. When the buffer's last `_NO_PROGRESS_K=4` entries all carry the same fingerprint AND `any_action_succeeded=False`, return `RunResult(status="failed", reason="no_progress")` — same shape as the existing `stuck_repeat` exit but a distinct reason. Use post-dispatch fingerprint (re-call `build_observation` *only* to read the cheap `ax_fingerprint` after dispatch — observation already runs at the *start* of next step, so consider caching it instead of recomputing; once #91 lands the cost is visible). Tests: (1) unit test with stub LLM that emits `read({"intent": f"x{i}"})` 5× in a row, all returning successfully but against a stub browser whose `ax_fingerprint` is constant — asserts loop exits at step 4 with `reason="no_progress"`, not at `max_steps`; (2) negative test: same setup but every other step the fingerprint flips — asserts loop runs to `max_steps` (the parallel buffer never fills with same-fingerprint entries); (3) negative test: stuck fingerprint but `click` returned `ok` — asserts no early bail, since that step counts as progress even if the page didn't move. *Why useful:* the dominant cost driver on `webvoyager-1` is the 8 wasted "thrash" steps after step 12 (~240 s, ~180k prompt tokens, $0.18 of the $0.32 case cost). Detecting this at step 16 instead of step 20 saves four steps; combined with #88 which also keeps those four steps cheap, the case finishes faster *and* uses the saved step budget for an actual recovery via #89's wall-clock cutoff or a future replan. **Estimated impact justifies axes pass_rate +10 / tokens -20 / latency -25.** *Trigger:* 2026-04-29 user-driven webvoyager timeout investigation — surfaced from inspecting the 8-step thrash tail of `webvoyager-1`.
