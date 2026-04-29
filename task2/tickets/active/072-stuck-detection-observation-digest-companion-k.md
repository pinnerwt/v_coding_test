---
id: 72
slug: stuck-detection-observation-digest-companion-k
status: active
tier: 5
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 104
- 70
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'deferred from PR #104 / ticket #70 on 2026-04-29 — the spec explicitly listed
  this as optional follow-up; PR notes called it out for the next iteration.'
---

72. **Stuck-detection observation-digest companion to the K=3 (tool_name, args) buffer in `agent.loop`.** PR #104 (ticket #70) shipped `_stuck_buf` tracking the last `_STUCK_REPEAT_K=3` `f"{tool_call.name}:{json.dumps(args, sort_keys=True)}"` strings; when all K are byte-identical, `loop()` exits with `RunResult(reason="stuck_repeat")`. The original ticket #70 spec listed an *optional* second mode that PR #104 deliberately deferred: the agent emits *different* tool calls but the underlying observation digest does not change, indicating thrashing without state progress. Concrete fix: also track the last `_STUCK_REPEAT_K` `axt_digest` strings (the same value already produced by `agent/observe.py:build_observation` and emitted as `ObservationEvent.ax_tree_digest`); after each step's observation, append the digest to a parallel `_stuck_obs_buf` and trim to K. If `len(_stuck_obs_buf) == _STUCK_REPEAT_K` and `len(set(_stuck_obs_buf)) == 1` AND no `PlanEvent(reason="replan")` fired in the same window (i.e. the planner has not advanced its `Plan progress` step), exit with `RunResult(status="failed", reason="stuck_no_observation_change")`. Reset on `SupervisorEvent` the same way `_stuck_buf` already does (D7 in `implement-loop-stuck-repeat/design.md`). Tests: a stub `LLMClient` returns `goto(url=A)`, `click(intent=B)`, `read(intent=C)` against a stub browser whose `build_observation` returns a fixed observation across all calls — assert `loop()` exits with `reason="stuck_no_observation_change"` and `steps == 3`; a healthy run where the observation digest changes between steps (different `_LARGE_OBSERVATION` per step) does not trigger; the existing `(tool_name, args)` K=3 detection still fires when both buffers would qualify (whichever path is checked first wins, document the order). *Why useful:* the K=3 `(tool_name, args)` heuristic only catches the most pathological stuck case; a thrashing planner that varies its tool calls but produces no state change still burns budget today (this is in fact what `webvoyager-1`'s 20-step trace looks like — alternating `goto/click/read` with no convergence). Pair with #70's existing capping on the same case to push the cost ceiling further down. *Trigger:* deferred from PR #104 / ticket #70 on 2026-04-29 — the spec explicitly listed this as optional follow-up; PR notes called it out for the next iteration.
