## 1. Red — failing tests for observe.py

- [ ] 1.1 In `test_observe.py`, add `test_last_actions_empty_on_first_step`: call `build_observation(browser, [])` and assert `obs["last_actions"] == []` and `"last_actions" in obs` (will fail because key is still `last_action`).
- [ ] 1.2 In `test_observe.py`, add `test_last_actions_single_entry`: call `build_observation(browser, [{"tool": "goto", "intent": "navigate", "outcome": "ok"}])` and assert `obs["last_actions"][0]["tool"] == "goto"` (will fail).
- [ ] 1.3 In `test_observe.py`, add `test_last_actions_error_entry_preserved`: pass a list with an error-outcome action and assert the `"error"` key survives in `obs["last_actions"][0]` (will fail).
- [ ] 1.4 Run `uv run pytest task2/tests/agent/test_observe.py -k "last_actions"` — confirm all three tests fail.

## 2. Red — failing tests for loop.py multi-tool behavior

- [ ] 2.1 In `test_loop.py`, add `test_multi_tool_last_actions_both_in_observation`: craft a fake LLM that returns a single response with two tool calls (`goto` then `read` with no intent), followed by `done`. Capture the step-2 observation and assert `obs["last_actions"]` has length 2, `[0]["tool"] == "goto"`, `[1]["tool"] == "read"`.
- [ ] 2.2 In `test_loop.py`, add `test_single_tool_last_actions_length_one`: existing single-`goto` step; assert step-2 `obs["last_actions"]` has length 1 (regression guard).
- [ ] 2.3 In `test_loop.py`, add `test_observation_uses_last_actions_key_not_last_action`: assert `"last_actions" in obs_json` and `"last_action" not in obs_json` for any captured observation (covers key rename).
- [ ] 2.4 Run `uv run pytest task2/tests/agent/test_loop.py -k "last_actions"` — confirm new tests fail.

## 3. Red — failing tests for trace.py ObservationEvent

- [ ] 3.1 In `test_trace.py`, add `test_observation_event_last_actions_default_empty`: construct `ObservationEvent` without `last_actions` arg, assert `event.last_actions == []` and JSON contains `"last_actions": []` (will fail because field does not exist yet).
- [ ] 3.2 In `test_trace.py`, add `test_observation_event_last_actions_round_trip`: construct with `last_actions=[{"tool": "goto", "intent": "x", "outcome": "ok"}]`, serialize and deserialize, assert list is preserved (will fail).
- [ ] 3.3 In `test_trace.py`, add `test_observation_event_error_entry_round_trip`: include an error-outcome entry with `"error"` key; assert round-trip preserves it (will fail).
- [ ] 3.4 Run `uv run pytest task2/tests/agent/test_trace.py -k "last_actions"` — confirm all three tests fail.

## 4. Green — implement observe.py changes

- [ ] 4.1 In `task2/agent/observe.py`, rename the `build_observation` parameter from `last_action: dict | None` to `last_actions: list[dict]`.
- [ ] 4.2 In `build_observation`, replace the `"last_action": last_action` key in both return dicts with `"last_actions": last_actions`.
- [ ] 4.3 Run `uv run pytest task2/tests/agent/test_observe.py -k "last_actions"` — confirm the three new tests pass.

## 5. Green — implement loop.py changes

- [ ] 5.1 In `task2/agent/loop.py`, remove `last_action: dict | None = None` initialization and replace with `last_actions: list[dict] = []`.
- [ ] 5.2 Inside the loop body, add `last_actions = []` at the top of each iteration (before `observe.build_observation`) to reset per step.
- [ ] 5.3 Change the `observe.build_observation(browser, last_action)` call to `observe.build_observation(browser, last_actions)`.
- [ ] 5.4 In the dispatch loop, replace the two `last_action = {...}` assignments with `last_actions.append({...})` (one for `"ok"`, one for `"error"`).
- [ ] 5.5 Run `uv run pytest task2/tests/agent/test_loop.py -k "last_actions"` — confirm new tests pass.

## 6. Green — implement trace.py ObservationEvent changes

- [ ] 6.1 In `task2/agent/trace.py`, add `last_actions: list[dict] = []` field to `ObservationEvent` (after `viewport`).
- [ ] 6.2 Run `uv run pytest task2/tests/agent/test_trace.py -k "last_actions"` — confirm new tests pass.

## 7. Migrate existing tests (green maintenance)

- [ ] 7.1 In `test_observe.py`, update `test_last_action_none_first_step` → rename to `test_last_actions_empty_on_first_step` (or remove if covered by task 1.1), and update assertion from `obs["last_action"] is None` to `obs["last_actions"] == []`.
- [ ] 7.2 In `test_observe.py`, update `test_last_action_threaded_second_step`: change parameter to a list `[action]` and assertion to `obs["last_actions"] == [action]`.
- [ ] 7.3 In `test_observe.py`, update `test_build_observation_closed_browser_returns_valid_dict`: change `obs["last_action"] is None` to `obs["last_actions"] == []`.
- [ ] 7.4 In `test_observe.py`, update `test_build_observation_falls_back_when_new_cdp_session_raises`: change `obs["last_action"] is None` to `obs["last_actions"] == []`.
- [ ] 7.5 In `test_loop.py`, update `test_first_step_last_action_null`: assert `obs_json["last_actions"] == []` (was `obs_json["last_action"] is None`).
- [ ] 7.6 In `test_loop.py`, update `test_second_step_last_action_populated`: assert `obs_json["last_actions"]` is a non-empty list and `obs_json["last_actions"][0]["tool"] == "goto"`.
- [ ] 7.7 Run full test suite `uv run pytest task2/` and confirm all existing tests pass.

## 8. Lint and final check

- [ ] 8.1 Run `uv run ruff check . --fix` from `task2/` and resolve any remaining issues.
- [ ] 8.2 Run `uv run ruff format .` from `task2/`.
- [ ] 8.3 Run `uv run pytest task2/` — full green bar required.
