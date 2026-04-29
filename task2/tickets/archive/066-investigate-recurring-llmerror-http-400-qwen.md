---
id: 66
slug: investigate-recurring-llmerror-http-400-qwen
status: archived
tier: 1
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json
- task2/benchmark/task2-implement-fail-prompt-tightening/webvoyager/20260428_223350.json
related: []
filed_pr: 101
merged_pr: null
archived_at: '2026-04-29'
trigger: user-flagged on 2026-04-28 in `/done_pr` for `implement-fail-prompt-tightening`
  — second consecutive run of the same case with the same 400.
---

66. **Investigate recurring `LLMError('http 400')` from the Qwen endpoint at step 0 of WebVoyager runs.** Across at least two WebVoyager Tier-0 baselines (`task2/benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json` on 2026-04-28 and `task2/benchmark/task2-implement-fail-prompt-tightening/webvoyager/20260428_223350.json` later the same day), `webvoyager-1` (Wikipedia "List the latest version of Python") fails at step 0 with `failure_class="tool_error"` and `failure_detail="LLMError('http 400')"` — zero steps completed, $0.0000 spent. The same case has not been observed to succeed in the WebVoyager suite. Either (a) the request our agent issues on the very first step has a malformed shape that this Qwen build rejects (e.g. tool-call schema or message-role drift between our `LLMClient.chat` and what `localhost:8090` accepts), (b) the Qwen endpoint is rate-limiting or short-circuiting on a specific domain header / referer, or (c) the prompt + observation produces a payload that exceeds a context limit only on this case. Concrete steps: (1) reproduce the failure with `LLM_BASE_URL=http://localhost:8090 LLM_MODEL=qwen3.5-27b uv run python -m scripts.bench --suite webvoyager --live --case-id webvoyager-1` (add a `--case-id` filter to `scripts/bench.py` if needed); (2) capture the exact request body sent to `http://localhost:8090/v1/chat/completions` on the failing call (e.g. via a debug-logging wrapper in `agent/llm.py:LLMClient.chat` or a `mitmproxy` tap) and the verbatim 400 response body; (3) bisect the request — strip the AX-tree digest, strip the planner step, replace the model name — to identify which input element triggers the 400; (4) cross-check whether `webvoyager-2` (arXiv) and `webvoyager-3` (GitHub) issue meaningfully different first-step requests and if so, what differs. Tests: a unit test in `task2/tests/test_llm.py` (or new `tests/test_bench_http_400.py`) that records a known-bad request payload (anonymized to a fixture) and asserts our `LLMClient.chat` does NOT regress to that payload shape — i.e. a TDD-shaped guard that whatever change we make fixes a captured-real-world payload, not a synthetic one. *Why useful:* `webvoyager-1` has been a persistent loss across the WebVoyager suite; until we know whether it's our request shape or the endpoint's behavior, every Tier-0 run loses 33% of its signal to the same flake. *Trigger:* user-flagged on 2026-04-28 in `/done_pr` for `implement-fail-prompt-tightening` — second consecutive run of the same case with the same 400.
