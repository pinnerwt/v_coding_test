## Context

The Task 2 agent stack has two entry points that construct an `LLMClient`:

1. `task2/api/server.py` — the FastAPI server used in production and Zeabur.
2. `task2/scripts/eval.py::build_clients()` — the eval/benchmark runner used for CI smoke tests and local eval runs.

Both read `LLM_MODEL` from the environment but apply different in-process fallbacks when the variable is absent:

| File | Fallback string |
|------|-----------------|
| `api/server.py:22` | `"qwen3-5-27b"` |
| `scripts/eval.py:320` | `"qwen3"` |

The local Qwen3 instance at `http://localhost:8090` only recognises `"qwen3-5-27b"` as its model name. Any eval run against the live endpoint without an explicit `LLM_MODEL` override therefore 404s on the first LLM call — the root cause of the recurring "infra mismatch" deferral noted on tickets #32 and #44.

`agent/llm.py` already holds `_DEFAULT_BASE_URL`. Adding `_DEFAULT_LLM_MODEL` there follows the same pattern and gives one file to update when the Qwen model name changes.

## Goals / Non-Goals

**Goals:**
- Single source of truth for the default LLM model name: `agent/llm.py`.
- Both `api/server.py` and `scripts/eval.py` reference that constant; neither hard-codes a model string locally.
- A unit test asserts both call sites resolve to the same string when `LLM_MODEL` is unset; this test is runnable without a live LLM.

**Non-Goals:**
- Changing the resolution priority (explicit kwarg > env var > default) — that logic stays in `LLMClient.chat()` untouched.
- Altering the `LLM_BASE_URL` or `LLM_API_KEY` defaults.
- Modifying `scripts/benchmark.py` beyond verifying it already delegates to `build_clients()`.
- Updating `bench-integration` or `zeabur-deploy` specs (those reference the env-var mechanism, not the default constant).

## Decisions

### Decision: Place the constant in `agent/llm.py`, not a new `agent/config.py`

`agent/llm.py` already owns `_DEFAULT_BASE_URL` and is imported by both `api/server.py` and `scripts/eval.py` (both already `from agent.llm import LLMClient`). Adding `_DEFAULT_LLM_MODEL` there requires zero new import paths and zero new files. A separate `agent/config.py` would be justified only if multiple unrelated modules needed cross-cutting config; here there are exactly two callers.

**Alternatives considered:**
- `agent/config.py` — introduces a new module with a single constant; over-engineered for the scope.
- Keep two separate constants in-sync by convention — rejected; history shows they diverged immediately.

### Decision: Export `_DEFAULT_LLM_MODEL` as a module-level name (not via a function or property)

A plain string constant is consistent with `_DEFAULT_BASE_URL` in the same file, is trivially importable, and allows `api/server.py` to do `from agent.llm import _DEFAULT_LLM_MODEL` (or use it via `agent.llm._DEFAULT_LLM_MODEL`) with no runtime cost.

### Decision: Do NOT change `LLMClient.chat()` resolution logic

The existing resolution chain (explicit kwarg → `self._model_default` → `LLM_MODEL` env var → raise `LLMError`) remains. The `_DEFAULT_LLM_MODEL` constant is used by the *callers* (`server.py`, `eval.py`) as the fallback they pass to `LLMClient(model=...)`, not by the client itself. This keeps `LLMClient` generic and free of Task-2-specific defaults — consistent with the "configurable base URL" constraint from `CLAUDE.md`.

## Risks / Trade-offs

- [Risk] Future rename of the Qwen model will still require editing `agent/llm.py`, but now only one place instead of two. → Acceptable; the single-source property is the whole point.
- [Risk] `_DEFAULT_LLM_MODEL` is a private name (underscore prefix); callers that import it are technically coupling to an implementation detail. → Acceptable at this scale; the alternative of making it public (`DEFAULT_LLM_MODEL`) is a trivial follow-up if a third caller appears.

## Migration Plan

1. Add `_DEFAULT_LLM_MODEL = "qwen3-5-27b"` to `agent/llm.py` (below `_DEFAULT_BASE_URL`).
2. In `api/server.py`: remove the local `_DEFAULT_LLM_MODEL` definition; update the two usages that reference it (they already use `_DEFAULT_LLM_MODEL` by name, so they will pick up the imported one after the next step).  Import it: `from agent.llm import _DEFAULT_LLM_MODEL` (or reference via `agent.llm._DEFAULT_LLM_MODEL`).
3. In `scripts/eval.py::build_clients()`: replace `"qwen3"` fallback with `_DEFAULT_LLM_MODEL` imported from `agent.llm`.
4. Write `task2/tests/test_llm_model_default.py` with a parameterised test that patches the env to unset `LLM_MODEL` and asserts both resolution paths return `_DEFAULT_LLM_MODEL`.
5. Run `uv run pytest` and `uv run ruff check .` — both must be green before commit.

No deployment steps needed; no rollback risk — this is a constant rename with no external effect when `LLM_MODEL` is set explicitly.

## Open Questions

None — all decisions above are resolved.
