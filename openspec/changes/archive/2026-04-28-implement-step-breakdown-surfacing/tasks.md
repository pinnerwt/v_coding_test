## 1. Failing Tests (Red phase)

- [x] 1.1 In `task2/tests/test_score.py` (or a new `task2/tests/test_score_detail.py`), add a test `test_detail_flag_emits_step_table_for_failing_case`: build a minimal results dict with one `failed` case whose `step_breakdown` has two entries; call `generate_scoreboard(data, detail=True)` and assert `"| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |"` is in the output and that specific step values appear — confirm the test fails with `TypeError` (unexpected kwarg) or `AssertionError`
- [x] 1.2 Add a test `test_detail_flag_no_table_for_passing_case`: call `generate_scoreboard(data, detail=True)` with a `succeeded` case with non-empty `step_breakdown`; assert `"Prompt Tokens"` does NOT appear in the output — confirm it fails
- [x] 1.3 Add a test `test_default_mode_emits_details_block_for_failing_case`: call `generate_scoreboard(data)` (no `detail` kwarg) with a failing case with 3-entry `step_breakdown`; assert `"<details><summary>step breakdown (3 steps)</summary>"` and `"</details>"` are in the output — confirm it fails
- [x] 1.4 Add a test `test_default_mode_no_details_block_for_passing_case`: call `generate_scoreboard(data)` with a passing case; assert `"<details>"` is NOT in the output — confirm it fails
- [x] 1.5 Add a test `test_render_step_breakdown_empty_returns_empty_string`: call `_render_step_breakdown([])` and assert result equals `""` — confirm it fails with `ImportError`
- [x] 1.6 Add a test `test_render_step_breakdown_single_step_contains_columns`: call `_render_step_breakdown([{"step": 1, "tool_calls": ["goto"], "prompt_tokens": 100, "completion_tokens": 10, "latency_ms": 500}])` and assert the header row and data row are present — confirm it fails
- [x] 1.7 Run `uv run pytest task2/tests/ -k "detail or step_breakdown or render_step" -x` from `task2/` and confirm all new tests fail for the expected reasons

## 2. Implement `_render_step_breakdown` helper

- [x] 2.1 In `task2/scripts/score.py`, add `_render_step_breakdown(steps: list[dict]) -> str` that returns `""` when `steps` is empty, otherwise returns a markdown table string with header `| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |` and `|---|---|---|---|---|` separator, then one row per step entry
- [x] 2.2 In the row, populate `Step` from `step["step"]`, `Tool` from `", ".join(step.get("tool_calls") or []) or "-"`, `Prompt Tokens` from `step.get("prompt_tokens", 0)`, `Completion Tokens` from `step.get("completion_tokens", 0)`, `Latency (ms)` from `step.get("latency_ms", 0)`
- [x] 2.3 Run `uv run pytest task2/tests/ -k "render_step_breakdown" -x` and confirm tests 1.5 and 1.6 now pass

## 3. Update `generate_scoreboard` to accept `detail` kwarg

- [x] 3.1 Add `detail: bool = False` keyword argument to `generate_scoreboard(data: dict, *, detail: bool = False) -> str`
- [x] 3.2 In the per-case loop inside `generate_scoreboard`, after appending each case row to `lines`, determine whether the case is failing: `status not in ("succeeded", "unverified", "skipped")` — use the raw `case.get("status", "unknown")` string (not the rendered display status)
- [x] 3.3 Retrieve `steps_data = case.get("step_breakdown") or []`
- [x] 3.4 When `detail=True` and the case is failing and `steps_data` is non-empty: call `_render_step_breakdown(steps_data)` and append the result to `lines`
- [x] 3.5 When `detail=False` and the case is failing and `steps_data` is non-empty: append `f"<details><summary>step breakdown ({len(steps_data)} steps)</summary>"`, then the result of `_render_step_breakdown(steps_data)`, then `"</details>"` to `lines`
- [x] 3.6 Run `uv run pytest task2/tests/ -k "detail or step_breakdown" -x` and confirm tests 1.1–1.4 now pass

## 4. Wire `--detail` flag in `main()`

- [x] 4.1 In `main()`, add `parser.add_argument("--detail", action="store_true", help="Emit per-step breakdown table for failing cases")` to the argparse setup
- [x] 4.2 Pass `detail=args.detail` to the `generate_scoreboard(data, detail=args.detail)` call in `main()`
- [x] 4.3 Run `uv run pytest task2/tests/ -k "detail" -x` and confirm the forwarding test (1.4) passes

## 5. Golden snapshot update

- [x] 5.1 Run `uv run python -m scripts.score tests/fixtures/results/sample_results.json > tests/fixtures/results/sample_results_scoreboard.md` from `task2/` to regenerate the golden snapshot if `sample_results.json` has any failing cases that now produce `<details>` blocks
- [x] 5.2 Run `uv run pytest task2/tests/ -k "snapshot or golden" -x` to confirm the snapshot test (if it exists) still passes after regeneration
- [x] 5.3 If the snapshot changed, inspect the diff to confirm only `<details>` blocks were added for failing cases and no other scoreboard content changed

## 6. Lint and Full Test Suite

- [x] 6.1 Run `uv run ruff check task2/scripts/score.py` and fix any lint errors
- [x] 6.2 Run `uv run ruff format task2/scripts/score.py`
- [x] 6.3 Run `uv run ruff check .` from `task2/` and confirm clean
- [x] 6.4 Run `uv run pytest task2/tests/ -v` (full suite) and confirm all tests pass with a green bar
