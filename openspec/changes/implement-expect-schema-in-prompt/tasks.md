## Tasks

1. - [x] **Red** — In `task2/tests/test_loop.py` (or a new `test_build_system_prompt.py`), add `test_build_system_prompt_schema_present` asserting that `_build_system_prompt("find the price", expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]})` (a) contains the substring `"MUST"` and (b) contains the substring `"answer"`. Run `uv run pytest -k test_build_system_prompt_schema_present` from `task2/` and confirm it fails with `TypeError` (unexpected kwarg) or `AssertionError`.

2. - [x] **Green** — In `task2/agent/loop.py`, add `expect: dict | None = None` as a keyword-only parameter to `_build_system_prompt(task, *, expect=None)`. When `expect is not None` and `expect.get("schema")`, compute `schema = expect["schema"]`, `keys = ", ".join(sorted(schema))`, and append `f" Your \`done.result\` MUST be a JSON object matching this schema: {json.dumps(schema)}. Required fields: {keys}."` to the returned string. Run the test from task 1 and confirm it passes.

3. - [x] **Red** — Add `test_build_system_prompt_schema_absent` asserting that `_build_system_prompt("find the price")` (no `expect` kwarg) returns a string byte-identical to the current production output (assert known substrings that are present today and confirm the `MUST` substring is absent). Run and confirm the test passes immediately — this is the "default-path safety" regression guard that locks in the current output.

4. - [x] **Red** — Add `test_build_system_prompt_empty_schema_leaves_no_must` asserting that `_build_system_prompt("find the price", expect={"schema": {}, "validators": []})` does NOT contain `"MUST"`. Run and confirm it fails (the implementation from task 2 would inject if `schema` is an empty dict — fix the guard to use `if expect and expect.get("schema")`).

5. - [x] **Green** — Confirm the guard in `_build_system_prompt` uses `if expect and expect.get("schema")` (truthy check), so an empty schema dict does not trigger injection. Run all four tests from tasks 1-4 and confirm they all pass.

6. - [x] **Red** — Add `test_loop_threads_expect_to_system_prompt` in `task2/tests/test_loop.py`. Stub `LLMClient` to capture the messages list from each `chat()` call and immediately return a terminal `done` tool call. Call `loop("find the price", browser, stub_llm, expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]})`. Assert that the first captured message (role=`system`) contains both `"MUST"` and `"answer"`. Run and confirm it fails with `TypeError` (loop does not yet accept `expect`).

7. - [ ] **Green** — In `task2/agent/loop.py`, add `expect: dict | None = None` as a keyword-only parameter to `loop()`. Thread it into the `_build_system_prompt(task, expect=expect)` call on the line that builds the initial system message. Run all tests through task 6 and confirm they pass.

8. - [ ] **Red** — Add `test_run_case_passes_expect_to_loop` in `task2/tests/test_eval.py` (or equivalent). Patch `agent.loop.loop` with a stub that records its kwargs; call `_run_case({"id": "x", "task": "t", "expect": {"schema": {"answer": "str"}, "validators": ["answer.nonempty"]}, "budget": {"steps": 1}}, llm, browser)`. Assert the stub was called with `expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]}`. Run and confirm it fails (current `_run_case` does not pass `expect`).

9. - [ ] **Green** — In `task2/scripts/eval.py`, inside `_run_case`, add `expect=case.get("expect")` to the `loop()` call. Run the full test suite (`uv run pytest task2/tests/` from `task2/`) and confirm the green bar. Run `uv run ruff check --fix . && uv run ruff format . && uv run ruff check .` from `task2/` and confirm zero errors.
