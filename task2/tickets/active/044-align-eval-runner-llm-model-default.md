---
id: 44
slug: align-eval-runner-llm-model-default
status: active
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 32
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

44. **Align eval-runner `LLM_MODEL` default with `api/server.py` (`qwen3-5-27b`).** `scripts/eval.py` (and the wider `scripts/benchmark` entry point) defaults `LLM_MODEL` to `"qwen3"`, while `task2/api/server.py:22` defaults to `"qwen3-5-27b"` — the model name actually served by the local Qwen instance at `http://localhost:8090`. As a result, any eval-runner smoke against the live LLM 404s at step 0, which is exactly why ticket #32's Task 7.1 (run `--case correction-l1-miss-l2-hit` against the local Qwen) had to be deferred. Make the default come from a single source (e.g. share `_DEFAULT_LLM_MODEL` from `agent/llm.py` or a new `agent/config.py`), and have both `api/server.py` and `scripts/eval.py` read it. Tests: a unit test asserts both call sites resolve the same default when `LLM_MODEL` is unset; running `python -m scripts.eval --case <fixture>` against a stubbed Qwen succeeds without setting `LLM_MODEL` explicitly. *Why useful:* unblocks live-Qwen smoke checks in future tickets and removes the recurring "infra mismatch unrelated to this change" deferral.
