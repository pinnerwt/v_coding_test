## 1. Failing tests first (TDD red)

- [ ] 1.1 Add `tests/agent/test_compact_messages.py` with three failing tests: (a) byte-identity of kept tail (no `<elided>` substring in any returned content), (b) prefix stability across consecutive compactions (R2's overlap region is a contiguous tail of R1), (c) most recent state and system message preserved.
- [ ] 1.2 Update or remove existing tests in `tests/agent/test_loop.py` (or wherever the legacy compaction scenarios live) that assert the presence of `Current state: <elided>` or `<read tool result elided>` substrings — those assertions are incompatible with the new contract. Confirm they fail under the new spec before rewriting.
- [ ] 1.3 Run the full suite (`uv run pytest`) from `task2/` and confirm the new tests in 1.1 fail with the current `_compact_messages` implementation.

## 2. Implementation (TDD green)

- [ ] 2.1 Rewrite `_compact_messages` in `task2/agent/loop.py`: drop oldest non-system, non-most-recent-state messages until total fits budget. Kept messages SHALL be byte-identical references to input messages (no `content` rewriting).
- [ ] 2.2 Remove the `_ELIDED_STATE_CONTENT` and `_ELIDED_TOOL_CONTENT` module-level constants — they are no longer used.
- [ ] 2.3 Run `uv run pytest` from `task2/` — the new tests from 1.1 SHALL pass and no previously-passing test SHALL regress.

## 3. Quality gates

- [ ] 3.1 `uv run ruff check .` from `task2/` SHALL pass.
- [ ] 3.2 Run `/simplify` to remove any dead code introduced or revealed by the rewrite.
- [ ] 3.3 Live smoke: `uv run python -m scripts.bench --suite webvoyager --live` (or a single-case invocation) confirms `webvoyager-1` does NOT exhibit the >2× per-step latency cliff seen in PR #142's benchmark. (May be skipped if Qwen unreachable; document in PR description.)
