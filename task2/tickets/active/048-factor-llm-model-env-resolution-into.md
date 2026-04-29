---
id: 48
slug: factor-llm-model-env-resolution-into
status: active
tier: 6
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 64
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced by review subagent on PR #64 (iteration 1); deferred as out of
  scope for the alignment fix.'
---

48. **Factor `LLM_MODEL` env-resolution into a shared helper in `agent/llm.py`.** `task2/api/server.py` resolves the `LLM_MODEL` env var via `os.environ.get("LLM_MODEL", _DEFAULT_LLM_MODEL)` in two places — `_build_run` (run record) and `_run_agent` (LLMClient construction). Same expression, two call sites, same fallback constant. Introduce a `resolve_llm_model() -> str` helper in `agent/llm.py` that performs the env lookup with `_DEFAULT_LLM_MODEL` as fallback, and have both `server.py` call sites read from it. `scripts/eval.py::build_clients()` should also adopt the helper for consistency. Tests: with `LLM_MODEL` unset, `resolve_llm_model() == _DEFAULT_LLM_MODEL`; with `LLM_MODEL="other"`, helper returns `"other"`; both `server.py` call sites and `build_clients()` invoke the helper (assert via `monkeypatch.setattr` spy). *Why useful:* removes a duplicated lookup that already drifted once (this PR fixed the eval.py side; the server.py duplication waits for a future re-drift). *Trigger:* surfaced by review subagent on PR #64 (iteration 1); deferred as out of scope for the alignment fix.
