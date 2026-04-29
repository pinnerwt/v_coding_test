## 1. Red — write failing unit tests

- [ ] 1.1 Create `task2/tests/test_phase_latency_breakdown.py` with a stub LLM that sleeps 0.4 s and a stub browser whose `build_observation` sleeps 0.1 s; assert `latency_breakdown_ms.llm_ms` in `[350, 600]` and `observation_ms` in `[80, 200]` (Scenario: Phase ranges match stub sleep durations)
- [ ] 1.2 Add a 5-step run test that asserts `abs((obs + llm + dispatch) - latency_ms) <= 5` for every `step_breakdown` entry (Scenario: Sum invariant holds across all steps in a 5-step run)
- [ ] 1.3 Add a test with a stub LLM that returns no tool calls for two steps then `done` on step 3; assert every `step_breakdown` entry has `latency_breakdown_ms` with all three integer keys, none `None` (Scenario: latency_breakdown_ms present on all entries including no-tool-call steps)
- [ ] 1.4 Run `uv run pytest task2/tests/test_phase_latency_breakdown.py` from `task2/`; confirm all three tests fail with `KeyError` or `AssertionError` (red bar confirmed)

## 2. Green — minimal production change

- [ ] 2.1 Update `_record_step` signature in `task2/agent/loop.py` to accept `latency_breakdown: dict` and write it as `"latency_breakdown_ms": latency_breakdown` in the `breakdown.append(...)` dict
- [ ] 2.2 In `loop()`, capture `t_obs_start = time.monotonic()` immediately before `observe.build_observation(...)` call
- [ ] 2.3 In `loop()`, capture `t_llm_start = time.monotonic()` immediately before `llm_client.chat(...)` call
- [ ] 2.4 In `loop()`, capture `t_dispatch_start = time.monotonic()` immediately before the `if not response.tool_calls:` guard (covers both the no-tool-call path and the dispatch path)
- [ ] 2.5 Compute the three phase deltas and pass `{"observation_ms": ..., "llm_ms": ..., "dispatch_ms": ...}` into every `_record_step` call site in `loop()` (approximately 7 sites: no-tool-call, done, fail-irrecoverable, stuck_repeat, replan-exhaustion, normal end-of-for-loop, max-steps fallback)
- [ ] 2.6 Run `uv run pytest task2/tests/test_phase_latency_breakdown.py` from `task2/`; confirm all three tests pass (green bar)

## 3. Verify existing tests still pass

- [ ] 3.1 Run `uv run pytest task2/tests/` from `task2/` and confirm no regressions; fix any call-site failures caused by the new required `latency_breakdown` parameter (existing test stubs may need a dummy dict passed)
- [ ] 3.2 Run `uv run ruff check task2/agent/loop.py task2/tests/test_phase_latency_breakdown.py` and fix any lint errors
- [ ] 3.3 Run `uv run ruff format task2/agent/loop.py task2/tests/test_phase_latency_breakdown.py`

## 4. Refactor under green

- [ ] 4.1 If `_record_step` now has more than 7 positional parameters, consider converting `latency_breakdown` to a keyword-only arg to improve call-site readability — re-run full test suite after
- [ ] 4.2 Confirm the step-1 plan-call latency attribution quirk (plan LLM call attributed to `observation_ms` on step 1) is acceptable by inspecting a sample benchmark JSON; no code change needed, but note it in a comment only if strictly necessary per CLAUDE.md conventions

## 5. JSON-schema completeness (eval results)

- [ ] 5.1 Run a smoke eval (`uv run python -m agent` or the eval harness against one WebVoyager case) and verify the output `eval/results/*.json` contains `latency_breakdown_ms` with all three keys on every `step_breakdown` entry — including 0-step exception paths if any
