## 1. Red — write failing string-shape test

- [x] 1.1 In `task2/tests/agent/test_loop.py` (or a new sibling `test_system_prompt.py` if the file is already large), add three test functions that import `_build_system_prompt` from `agent.loop` and assert: (a) the returned string contains `"ONLY for irrecoverable conditions"`, (b) the returned string contains `"attempt \`click\`/\`type\`"`, (c) the returned string does NOT contain `"If you cannot complete the task, call"`.
- [x] 1.2 Run `uv run pytest task2/tests/agent/test_loop.py -k "system_prompt" -x` (adjust path if using a new file) and confirm all three tests fail for the expected reason (old phrasing present / new phrasing absent).

## 2. Green — tighten the prompt phrasing

- [x] 2.1 In `task2/agent/loop.py`, replace the trailing sentence of `_build_system_prompt` (currently `"If you cannot complete the task, call \`fail\` with a reason."`) with: `"Call \`fail\` ONLY for irrecoverable conditions — login walls, captchas, pages that don't exist, or required information genuinely absent from the page. If a target element exists on the page but you don't know how to act on it, attempt \`click\`/\`type\` with a natural-language \`intent\` first; the locator pipeline will resolve it."`
- [x] 2.2 Run the three new tests and confirm they all pass.
- [x] 2.3 Run the full agent test suite (`uv run pytest task2/tests/agent/ -x`) and confirm no regressions (replay tests that embed the old system prompt string will need their fixtures updated if they hard-code the prompt text — check `test_replay.py` and update any affected fixtures or helper calls to `_build_system_prompt`).

## 3. Clean — lint and verify

- [x] 3.1 Run `uv run ruff check task2/agent/loop.py task2/tests/` and fix any lint errors.
- [x] 3.2 Run `uv run ruff format task2/agent/loop.py task2/tests/` and confirm no diff.
- [x] 3.3 Run the full test suite one final time (`uv run pytest task2/tests/ -x`) to confirm the green bar holds.
