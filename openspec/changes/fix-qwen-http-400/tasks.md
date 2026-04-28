## Task 1 — Red: `failure_detail` enrichment for `LLMError`

- [x] 1.1 In `task2/tests/test_eval.py`, add test `test_run_case_failure_detail_includes_llm_error_body`.

  The test shall:
  - Import `LLMError` from `agent.llm`.
  - Mock `agent.loop.loop` to raise `LLMError("http 400", kind="http", status=400, body='{"error":{"type":"exceed_context_size_error","n_prompt_tokens":34074}}')`.
  - Call `_run_case(case, llm_client=ANY, browser=ANY)` with a minimal fixture case dict.
  - Assert `result.failure_detail` contains the substring `"status=400"`.
  - Assert `result.failure_detail` contains the substring `"exceed_context_size_error"` (a slice of the body).
  - Assert `result.failure_class == "tool_error"`.

  Smallest assertion: `assert "status=400" in result.failure_detail`.

  Acceptance: `uv run pytest tests/test_eval.py::test_run_case_failure_detail_includes_llm_error_body -x` (from `task2/`).

- [x] 1.2 Run the test and confirm it fails with `AssertionError` because `repr(exc)` gives `"LLMError('http 400')"` which does not contain `"status=400"`.

## Task 2 — Green: enrich `_run_case` exception handler

- [x] 2.1 In `task2/scripts/eval.py`, in `_run_case`'s `except Exception as exc:` block (currently at lines 256–267), add an `isinstance` branch:
  - `from agent.llm import LLMError` (add the import at the top of the module if not already present).
  - When `isinstance(exc, LLMError)`, build `failure_detail` as:
    `f"LLMError(kind={exc.kind!r}, status={exc.status}, body={(exc.body or '')[:512]!r})"`.
  - When not `isinstance(exc, LLMError)`, keep `failure_detail=repr(exc)` as before.
  - Keep `steps=0` (step count from inside `loop()` is not accessible in the exception path; this is accepted per design Decision 4).

- [x] 2.2 Run `uv run pytest tests/test_eval.py::test_run_case_failure_detail_includes_llm_error_body -x` and confirm it passes.

- [x] 2.3 Run `uv run pytest tests/test_eval.py -x` and confirm no regressions.

## Task 3 — Red: compaction keeps total chars under budget

- [x] 3.1 In `task2/tests/agent/test_loop.py`, add test `test_loop_compacts_message_history_under_token_budget`.

  The test shall:
  - Create a stub `LLMClient` that records every `messages` argument passed to `chat()` and always returns a `ChatResponse` with a `goto` tool call (URL cycling through a fixed list to avoid infinite navigation).
  - Run `loop("dummy task", browser=<stub browser>, llm_client=<stub>, max_steps=25)`.
  - After the loop returns (status `"timeout"`), inspect the stub's last recorded `messages` argument.
  - Assert `sum(len(json.dumps(m)) for m in last_messages) < 80_000` (the default budget).
  - Assert at least one `user`-role message in the history has `content == "Current state: <elided>"` (proving compaction fired).
  - Assert `last_messages[0]["role"] == "system"` (system prompt preserved at index 0).

  Smallest assertion: `assert sum(len(json.dumps(m)) for m in last_messages) < 80_000`.

  Acceptance: `uv run pytest tests/agent/test_loop.py::test_loop_compacts_message_history_under_token_budget -x` (from `task2/`).

- [x] 3.2 Run the test and confirm it fails because no compaction logic exists and the accumulated messages exceed 80 K chars by step 25 with realistic AX-tree-sized observations.

  Note: the stub browser's observation must be sized to trigger compaction. Use a stub that returns `build_observation`-compatible dicts with a long `ax_tree` string of at least 4 KB to simulate Wikipedia-scale pages.

## Task 4 — Green: implement `_compact_messages`

- [x] 4.1 In `task2/agent/loop.py`, add a module-level constant:
  `_DEFAULT_CONTEXT_CHAR_BUDGET: int = 80_000`

- [x] 4.2 Add a private function `_compact_messages(messages: list[dict], budget_chars: int) -> list[dict]`:
  - Compute `total = sum(len(json.dumps(m)) for m in messages)`.
  - If `total <= budget_chars`, return `messages` unchanged.
  - Walk forward from `messages[1]` (skip system prompt at index 0). For each message:
    - If `role == "user"` and `content` starts with `"Current state: "` and it is NOT the last such `user` message in the list, replace its `content` with `"Current state: <elided>"`.
    - If `role == "tool"` and it is NOT part of the most recent turn (defined as: not reachable by scanning backwards from the end until hitting the last user-role `"Current state: "` message), replace its `content` with `"<read tool result elided>"`.
  - Recompute total; if still over budget, repeat (iterative elision until under budget or no more elisions possible).
  - Return the modified list. `messages[0]` (system prompt) is never modified.

- [x] 4.3 In `loop()`, read the budget from environment: `_budget = int(os.environ.get("LLM_CONTEXT_CHAR_BUDGET", _DEFAULT_CONTEXT_CHAR_BUDGET))`. Call `messages = _compact_messages(messages, _budget)` immediately before `response = llm_client.chat(messages, tools=TOOLS)`.

- [x] 4.4 Run `uv run pytest tests/agent/test_loop.py::test_loop_compacts_message_history_under_token_budget -x` and confirm it passes.

## Task 5 — Red: most-recent turn preserved after compaction

- [x] 5.1 In `task2/tests/agent/test_loop.py`, add test `test_loop_preserves_most_recent_observation_after_compaction`.

  The test shall:
  - Use the same stub setup as Task 3 but inspect `last_messages` for the content of the last `user`-role message that starts with `"Current state: "`.
  - Assert its `content` is NOT `"Current state: <elided>"` (i.e. the most recent observation is kept verbatim).
  - Assert `last_messages[0]["role"] == "system"` and `last_messages[0]["content"]` equals `_build_system_prompt("dummy task")`.

  Smallest assertion: `assert last_user_state_msg["content"] != "Current state: <elided>"`.

  Acceptance: `uv run pytest tests/agent/test_loop.py::test_loop_preserves_most_recent_observation_after_compaction -x` (from `task2/`).

- [x] 5.2 Run the test and confirm it fails before the compaction implementation is in place (or passes immediately if Task 4 already satisfies this invariant — in that case, record the green result and move on without additional code changes).

## Task 6 — Red: end-to-end regression

- [x] 6.1 Create `task2/tests/scripts/__init__.py` if it does not exist.

- [x] 6.2 Create `task2/tests/scripts/test_bench_qwen_400_regression.py` with test `test_no_llm_error_after_25_steps`.

  The test shall:
  - Define a stub `LLMClient` that records each `messages` argument and always returns a `ChatResponse` with a `goto` tool call (without using real `httpx`).
  - Define a stub `Browser` with a minimal `current_url`, `title`, `get_ax_tree` returning a large string (≥ 4 KB) to simulate Wikipedia-scale pages.
  - Construct a minimal case dict: `{"id": "reg-001", "domain": "fixture", "category": "test", "task": "dummy", "expect": {}, "budget": {"steps": 25, "usd": 1.0, "seconds": 300}}`.
  - Call `loop("dummy task", browser=<stub>, llm_client=<stub>, max_steps=25)` directly (not `_run_case`, to avoid needing a full eval harness).
  - Assert the call completes without raising `LLMError`.
  - Assert the stub's last recorded `messages` total character count is `< 80_000`.

  Acceptance: `uv run pytest tests/scripts/test_bench_qwen_400_regression.py::test_no_llm_error_after_25_steps -x` (from `task2/`).

- [x] 6.3 Run the test and confirm it fails before Task 4 is implemented (or passes if Task 4 is already done — in that case record the green result).

## Task 7 — Lint and full green bar

- [x] 7.1 Run `uv run ruff format .` from `task2/` and confirm no diff.
- [x] 7.2 Run `uv run ruff check .` from `task2/` and fix any lint errors.
- [x] 7.3 Run `uv run pytest` from `task2/` and confirm the full suite passes.

---

## Mandatory pre-commit gates

Before committing, run all three commands from `task2/`:

```
uv run ruff format .
uv run ruff check .
uv run pytest
```

All must exit 0. Do not use `--no-verify`. Do not add comments or docstrings to production code under `task2/` (rely on names; `/simplify` strips them). Flip task checkboxes inline as each task is satisfied — not in a separate bookkeeping commit.
