---
id: 19
slug: web-use-benchmark-research-integration
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
trigger: Web-use benchmark research + integration
---

19. **Web-use benchmark research + integration** — survey existing public web-agent benchmarks (at minimum: WebArena, Mind2Web / Online-Mind2Web, BrowserGym, WebVoyager, MiniWoB++, WebShop, GAIA web subset). Output a research brief at `prompts/task2/web-benchmarks.md` covering, per benchmark: license, scope (live web vs. snapshot vs. simulated), hosting cost (self-hosted Docker, cloud infra, none), task format, headline metric, and a recommendation with reasoning. Integrate at least **one** selected benchmark as an additional eval source under `task2/eval/`: a loader that parses the upstream task format into our `Case` schema (or a thin adapter at the runner boundary) plus a runner entry such as `uv run python -m scripts.bench --suite <name>` that produces a `eval/results/<ts>.json` with the existing shape. Tests: loader parses a vendored fixture sample of the chosen benchmark's task format; runner-level smoke test executes one case end-to-end against a stubbed browser/LLM and asserts the result JSON shape matches our schema; brief exists at the expected path and lists the selected benchmark.
