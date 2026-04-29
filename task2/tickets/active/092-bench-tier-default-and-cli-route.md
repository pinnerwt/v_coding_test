---
id: 92
slug: bench-tier-default-and-cli-route
status: active
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies:
- 88
- 89
- 90
- 93
pre_flight_gates: []
evidence:
- task2/scripts/bench.py
- task2/eval/bench/data/webvoyager/tier1.json
- task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: 2026-04-29 — user-driven webvoyager timeout investigation; ticket queue restart
---

92. **Stop running tier=0 (the 3-case smoke sample) as the default WebVoyager benchmark; route per-PR runs through tier=1 (12 cases).** Every `task2/benchmark/*/webvoyager/*.json` artifact dating back to PR #69 contains the same three case ids — `webvoyager-1`, `webvoyager-2`, `webvoyager-3`. These come from `tests/fixtures/benchmarks/webvoyager/tasks_sample.json` (`scripts/bench.py:15`, `_DEFAULT_TASK_PATHS["webvoyager"][0]`). Tier 1 — `eval/bench/data/webvoyager/tier1.json` with `webvoyager-101..112` covering Wikipedia, arXiv, GitHub, HuggingFace, BBC News, Cambridge Dictionary, and Wolfram Alpha — *exists* but has never been run as a benchmark. The `--tier` flag in `scripts/bench.py:26` defaults to `0` and nothing in CI / `scripts/score.py` / the `/done_pr` baseline-diff workflow passes `--tier=1`. We are optimizing against an N=3 oracle, three of whose tasks share the *same* page (Wikipedia for #1, arXiv for #2, GitHub for #3) and never exercise paginated search results, login walls, JS-heavy SPA pages, or numeric extraction. **Fix:** (1) flip the `--tier` default in `scripts/bench.py:26` from `0` to `1`; (2) document tier=0 as "smoke" in the bench script's help text; (3) update the shell wrapper / Makefile / CI runner that actually invokes bench (grep for `python -m scripts.bench` and `--suite webvoyager`) to use the new default; (4) add a `WEBVOYAGER_TIER` env var read in `scripts/bench.py` so CI can override without code change. Tests: (1) unit test asserts `parser.parse_args(["--suite", "webvoyager"]).tier == 1`; (2) unit test asserts `WEBVOYAGER_TIER=0 python -m scripts.bench --suite webvoyager` resolves to the sample path; (3) integration smoke that loads `tier1.json` via `load_webvoyager` and asserts 12 cases come back with stable `id` ordering. **Dependency note (do not land before timeouts are fixed):** holds on the full timeout-fix bundle — #88 (cache-preserving compaction), #89 (wall-clock budget), #90 (schema-aware prompt), and #93 (no-progress stuck detection). User direction 2026-04-29: solve the `webvoyager-1` timeout on the existing N=3 corpus first; only widen to N=12 once a tier=0 baseline shows ≥1/3 passing and `webvoyager-1` no longer hits `status=timeout`. Running tier=1 before that point would multiply the timeout cost by 4× per PR and drown the baseline-diff signal in noise. *Why useful:* the eval loop is currently sampling a corpus too small to detect regressions in 9 of the 7 task domains the brief expects — every PR's "WebVoyager 0/3" is the same three cases, so `/done_pr` baseline-diff sees no signal. Going to N=12 multiplies signal density by 4× without adding new infra. *Trigger:* 2026-04-29 user-driven webvoyager timeout investigation — discovered while grepping the benchmark archive for `webvoyager-` ids.
