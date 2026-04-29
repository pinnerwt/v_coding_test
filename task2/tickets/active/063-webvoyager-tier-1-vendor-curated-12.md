---
id: 63
slug: webvoyager-tier-1-vendor-curated-12
status: active
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/<branch>/webvoyager/tier1.json
- task2/benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json
related: []
filed_pr: 98
merged_pr: null
archived_at: null
trigger: surfaced from user directive on 2026-04-28 — "select the subset that represents
  the most suitable while at the same time cheap in time for testing/improving and
  iterate fast in early stages." Tier-0 baseline recorded at `task2/benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json`.
---

63. **WebVoyager Tier-1: vendor a curated 12-task subset against stable sites.** The current `--suite webvoyager` runner reads only the 3-task Tier-0 sample at `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json` (Wikipedia / arXiv / GitHub). Tier-0 baseline on 2026-04-28 ran 2/3 (`webvoyager-1` failed at step 0 with `LLMError('http 400')`, likely transient endpoint state; `webvoyager-2` and `webvoyager-3` passed in 9 and 6 steps at $0.1146 and $0.0405). The next iteration step is to expand to ~12 tasks across stable, popup-free, fast-loading domains: Wikipedia (×2), arXiv (×2), GitHub (×2), HuggingFace, BBC News, Cambridge Dictionary, Wolfram Alpha — chosen because they don't require login, captcha, or location-aware widgets. Deliberately exclude WebVoyager's Allrecipes / Apple / Coursera / Google-Search / Booking / Flights / Amazon entries (popups, captchas, login walls). Vendor the curated entries at `task2/eval/bench/data/webvoyager/tier1.json` (preserving the upstream `id`/`web_name`/`ques`/`web` schema so `webvoyager_loader.load_webvoyager` works unchanged), point `WEBVOYAGER_TASKS` env or a new `--tasks` flag at it, and capture Tier-1 baseline under `task2/benchmark/<branch>/webvoyager/tier1.json`. Tests: (a) loader test asserts the vendored file deserializes via `load_webvoyager` without error and yields 12 cases with valid `task`/`domain`/`category` fields; (b) a runner test (mocked LLM, no `--live`) asserts the Tier-1 fixture path is selected when `--tier 1` (or env override) is passed; (c) document the site-selection rationale in the README's "WebVoyager benchmark" section. *Why useful:* Tier-0 (3 tasks) is too small to measure regressions reliably and biases toward the simplest sites; Tier-1 (~12 tasks) is the smallest credible "does the agent generalize to a random task" signal cheap enough to run per-branch. *Trigger:* surfaced from user directive on 2026-04-28 — "select the subset that represents the most suitable while at the same time cheap in time for testing/improving and iterate fast in early stages." Tier-0 baseline recorded at `task2/benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json`.
