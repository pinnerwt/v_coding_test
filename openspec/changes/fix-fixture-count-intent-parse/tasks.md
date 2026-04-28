## 1. Red — unit tests for parse_intent with list/listitem roles

- [x] 1.1 In `task2/tests/test_locate.py`, add a test asserting `parse_intent("list")` returns `("list", None)` and does NOT raise `IntentParseError`
- [x] 1.2 In `task2/tests/test_locate.py`, add a test asserting `parse_intent("listitem")` returns `("listitem", None)` and does NOT raise `IntentParseError`
- [x] 1.3 In `task2/tests/test_locate.py`, add a test asserting `parse_intent("Items listitem")` returns `("listitem", "Items")`
- [x] 1.4 In `task2/tests/test_locate.py`, add a test asserting `parse_intent("items")` still raises `IntentParseError` with `"items"` in the message
- [x] 1.5 Run `cd task2 && uv run pytest tests/test_locate.py -x` — confirm the new tests fail for the expected reason (`IntentParseError`)

## 2. Red — integration test for fixture-count with stubbed LLM

- [x] 2.1 In `task2/tests/test_eval.py`, add an integration test that loads `eval/cases/fixture-count.yaml`, runs `_run_case` (or `run_suite`) against a stubbed LLM that emits a single locate+read step with a `listitem` role intent, and asserts `result.status in {"succeeded", "unverified"}`
- [x] 2.2 Run `cd task2 && uv run pytest tests/test_eval.py -x -k fixture_count` — confirm the test fails due to `IntentParseError` (not a test-setup error)

## 3. Green — extend `_SUPPORTED_ROLES` in `agent/locate.py`

- [ ] 3.1 In `task2/agent/locate.py`, add `"list"` and `"listitem"` to `_SUPPORTED_ROLES` frozenset
- [ ] 3.2 Run `cd task2 && uv run pytest tests/test_locate.py -x` — confirm all locate unit tests pass (including the new list/listitem ones)
- [ ] 3.3 Run `cd task2 && uv run pytest tests/test_eval.py -x -k fixture_count` — confirm the integration test passes

## 4. Green — add canary: true to fixture-count.yaml

- [ ] 4.1 Add `canary: true` to `task2/eval/cases/fixture-count.yaml`
- [ ] 4.2 Run `cd task2 && uv run pytest tests/ -x` — confirm the full test suite remains green

## 5. Lint and format

- [ ] 5.1 Run `cd task2 && uv run ruff check .` — fix any lint errors
- [ ] 5.2 Run `cd task2 && uv run ruff format .` — apply formatting
- [ ] 5.3 Re-run `cd task2 && uv run pytest tests/ -x` — confirm tests still pass after formatting

## 6. Verify eval case end-to-end

- [ ] 6.1 Run `cd task2 && uv run python -m scripts.eval --case fixture-count` and confirm `status` is in `{"succeeded", "unverified"}` (not `"failed"` with `failure_class="tool_error"`)
- [ ] 6.2 Run `cd task2 && uv run python -m scripts.canary_gate --results benchmark/<branch>/results.json` (or a locally generated results file) and confirm the gate exits 0 with three canary cases recognized
