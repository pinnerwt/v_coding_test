---
id: 58
slug: scripts-eval-build-clients-constructs-double
status: archived
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related: []
filed_pr: null
merged_pr: null
archived_at: '2026-04-29'
trigger: 'surfaced by `/opsx:apply` subagent on PR #88 (`fix-fixture-count-intent-parse`)
  on 2026-04-28 while running step 6.1 acceptance check by hand.'
---

58. **`scripts/eval.build_clients()` constructs a double-`/v1` LLM URL.** When the user invokes `cd task2 && uv run python -m scripts.eval --case <name>` directly (no `LLM_BASE_URL` exported), `build_clients()` defaults `LLM_BASE_URL` to `"http://localhost:8090/v1"` while `agent.llm.LLMClient` itself appends `/v1/chat/completions` to whatever base URL it gets. The result is an effective POST to `http://localhost:8090/v1/v1/chat/completions`, which 404s under the local Qwen serving at `localhost:8090`. The `scripts/benchmark` entry point and the `api/server.py` path both pass `LLM_BASE_URL=http://localhost:8090` (no `/v1`) and therefore work; only the bare `scripts.eval` invocation trips this. Fix: drop the `/v1` suffix from the `scripts/eval.py::build_clients()` default, so the same base URL works in all three call sites. Tests: a unit test in `task2/tests/test_eval.py` asserts `build_clients()` returns an `LLMClient` whose `base_url` does NOT end in `/v1` (use `unittest.mock.patch.dict(os.environ, {}, clear=True)` to neutralize the inherited env). *Why useful:* removes a recurring "I tried to repro the bug locally and got 404 instead of the actual failure mode" debugging round when investigating eval failures by hand. *Trigger:* surfaced by `/opsx:apply` subagent on PR #88 (`fix-fixture-count-intent-parse`) on 2026-04-28 while running step 6.1 acceptance check by hand.
