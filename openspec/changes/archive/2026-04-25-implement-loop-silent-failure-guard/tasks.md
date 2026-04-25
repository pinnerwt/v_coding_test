## 1. Red — Failing Tests

- [x] 1.1 Add `test_loop_done_without_evidence` to `task2/tests/agent/test_loop.py`: mock LLM emits `goto(fixture_url)` then `done(result={}, evidence={})`. Assert `result.status == "unverified"` and `result.verifier["ok"] is False` and `result.verifier["reasons"]` is a non-empty list.
- [x] 1.2 Add `test_loop_done_with_valid_evidence` to `task2/tests/agent/test_loop.py` (regression guard): mock LLM emits `goto(fixture_url)` then `done(result={"heading": "Hello, loop"}, evidence={"url": fixture_url, "text_snippet": "Hello, loop"})`. Assert `result.status == "succeeded"` and `result.verifier["ok"] is True` and `result.verifier["reasons"] == []`.
- [x] 1.3 Run `uv run pytest task2/tests/agent/test_loop.py::test_loop_done_without_evidence task2/tests/agent/test_loop.py::test_loop_done_with_valid_evidence -x` from `task2/` and confirm both fail (the guard does not exist yet, so `done` returns `"succeeded"` unconditionally and `RunResult` has no `verifier` field).

## 2. Green — Implement Evidence Guard

- [x] 2.1 In `task2/agent/loop.py`, add `"unverified"` to the `RunStatus` `Literal` type alias: `Literal["succeeded", "unverified", "failed", "timeout"]`.
- [x] 2.2 Add `verifier: dict | None = None` as the last field of the `RunResult` frozen dataclass. Existing call sites that do not pass `verifier` remain valid (default is `None`).
- [x] 2.3 Add a private helper `_check_evidence(evidence: dict | None) -> dict` in `loop.py` that returns `{"ok": bool, "reasons": list[str]}`. It checks: (a) `evidence` is a non-None dict, (b) `url` key exists and is a non-empty string (strip whitespace), (c) `text_snippet` key exists and is a non-empty string (strip whitespace). Each failing check appends a descriptive string to `reasons`. `ok` is `True` iff `reasons` is empty.
- [x] 2.4 In `loop.py`'s `done` handler (inside the `for tool_call in response.tool_calls` dispatch), replace the unconditional `return RunResult(status="succeeded", ...)` with: call `_check_evidence(args.get("evidence"))`, set `status="succeeded"` if `verifier["ok"]` else `"unverified"`, and include `verifier=verifier` in the `RunResult`.
- [x] 2.5 Run `uv run pytest task2/tests/agent/test_loop.py::test_loop_done_without_evidence task2/tests/agent/test_loop.py::test_loop_done_with_valid_evidence -x` and confirm both pass.
- [x] 2.6 Run the full test suite `uv run pytest task2/tests/` and confirm all existing tests still pass (no regression on `test_loop_happy_path`, `test_loop_self_correction`, etc.).

## 3. Lint and Format

- [x] 3.1 Run `uv run ruff check . --fix` from `task2/` and resolve any lint errors.
- [x] 3.2 Run `uv run ruff format .` from `task2/` to auto-format changed files.
- [x] 3.3 Confirm `uv run ruff check .` exits clean (zero errors, zero warnings).

## 4. Refactor Under Green (if needed)

- [x] 4.1 Review `_check_evidence` for clarity — ensure reason strings are human-readable and identify the failing field by name (e.g. `"evidence.url is missing or empty"`). Refactor only if tests remain green. (No refactor needed; strings already match spec exactly.)
- [x] 4.2 Verify that `RunResult` construction in `fail` and `timeout` paths still passes `verifier=None` (explicitly or via default) and that no existing assertion breaks. (fail: explicit None; timeout: default None via dataclass field.)
