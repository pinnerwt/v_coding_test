## 1. Red — Write the failing unit test

- [ ] 1.1 Create `task2/tests/test_llm_model_default.py` with a test that asserts `agent.llm._DEFAULT_LLM_MODEL == "qwen3-5-27b"` (import-only check, no LLM call needed).
- [ ] 1.2 Add a test that patches `os.environ` to remove `LLM_MODEL`, calls `scripts.eval.build_clients()` (with `LLMClient` and `Browser` patched to avoid network/browser), and asserts the resolved model equals `agent.llm._DEFAULT_LLM_MODEL`.
- [ ] 1.3 Add a test that asserts `os.environ.get("LLM_MODEL", agent.llm._DEFAULT_LLM_MODEL)` (the pattern used in `api/server.py`) resolves to `"qwen3-5-27b"` when `LLM_MODEL` is unset.
- [ ] 1.4 Run `uv run pytest task2/tests/test_llm_model_default.py` and confirm it fails (because `_DEFAULT_LLM_MODEL` does not yet exist in `agent/llm.py` and `build_clients()` still uses `"qwen3"`).

## 2. Green — Implement the shared constant and update call sites

- [ ] 2.1 In `task2/agent/llm.py`, add `_DEFAULT_LLM_MODEL = "qwen3-5-27b"` immediately below `_DEFAULT_BASE_URL`.
- [ ] 2.2 In `task2/api/server.py`, remove the local `_DEFAULT_LLM_MODEL = "qwen3-5-27b"` definition (line 22) and add `from agent.llm import _DEFAULT_LLM_MODEL` (or reference it via the already-imported module). Confirm the two usages of `_DEFAULT_LLM_MODEL` in `server.py` still resolve correctly.
- [ ] 2.3 In `task2/scripts/eval.py::build_clients()`, replace the hard-coded string `"qwen3"` (line 320) with `_DEFAULT_LLM_MODEL` imported from `agent.llm`.
- [ ] 2.4 Run `uv run pytest task2/tests/test_llm_model_default.py` and confirm all tests pass.

## 3. Full test suite and lint

- [ ] 3.1 Run `uv run pytest task2/` (full suite) and confirm no regressions.
- [ ] 3.2 Run `uv run ruff check task2/` and `uv run ruff format --check task2/`; fix any issues.
