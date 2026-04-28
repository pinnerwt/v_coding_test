## Context

The agent benchmarking pipeline already supports `--suite webvoyager` via `scripts/bench.py`, which reads a task JSON via `load_webvoyager` and dispatches cases through `run_suite`. The only task source today is the 3-task Tier-0 sample at `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json`. That file was chosen for fast CI smoke-testing, not statistical validity.

Tier-1 adds 12 curated tasks across stable, popup-free domains. The `load_webvoyager` loader is already schema-agnostic (it reads any JSON array conforming to the upstream `id`/`web_name`/`ques`/`web` shape), so the dataset extension requires no loader changes — only a new data file and runner plumbing to select it.

## Goals / Non-Goals

**Goals:**
- Vendor a 12-task Tier-1 dataset at `task2/eval/bench/data/webvoyager/tier1.json`.
- Add `--tier {0,1}` to `scripts/bench.py`; default `0` keeps existing behaviour unchanged.
- `WEBVOYAGER_TASKS` env var continues to override the resolved path at any tier.
- Tests: loader asserts Tier-1 file deserialises to 12 valid cases; runner test asserts `--tier 1` selects the correct path (mocked LLM, no `--live`).
- README documents site-selection rationale.
- Baseline capture: `task2/benchmark/<branch>/webvoyager/tier1.json` (run manually, not committed).

**Non-Goals:**
- Modifying `load_webvoyager` — contract is stable and tested.
- Automating baseline capture in CI — this is a manual one-off per branch.
- Vendoring more than 12 tasks or adding Tier-2.
- Changing the Tier-0 fixture or its tests.

## Decisions

### Decision 1: `--tier` flag on `scripts/bench.py`, not a separate script

Alternatives considered:
- A second script `bench_tier1.py` — duplicates all runner wiring for no gain.
- An env var only — less ergonomic for ad-hoc runs; `--tier` is more discoverable.

Chosen: extend the existing `bench.py` with `--tier {0,1}` (argparse `int`, choices `[0,1]`, default `0`). As-built, `_DEFAULT_TASK_PATHS` is a two-level dict (`{suite: {tier: path}}`) — equivalent semantically to `(suite, tier)` keying but cleaner to extend per-suite. This keeps a single runner entry point and preserves the existing env-var override path.

### Decision 2: Tier-1 dataset location — `task2/eval/bench/data/webvoyager/tier1.json`

The proposal says `task2/eval/bench/data/webvoyager/tier1.json`. The Tier-0 sample lives under `task2/tests/fixtures/` because it was originally a test fixture. Tier-1 is production benchmark data, so it belongs under `eval/bench/data/` — separate from test fixtures and closer to the loader that consumes it.

### Decision 3: Curated 12-task site selection

Sites chosen: Wikipedia (×2), arXiv (×2), GitHub (×2), HuggingFace (×2), BBC News (×2), Cambridge Dictionary (×1), Wolfram Alpha (×1). All are stable, popup-free, no login required, no CAPTCHA, no location-aware widgets.

Excluded: Allrecipes (cookie consent modal), Apple (geo-redirect), Coursera (login wall), Google-Search (CAPTCHA risk), Booking.com (geo-pricing), Google-Flights (dynamic widgets), Amazon (login walls + CAPTCHA).

Task diversity within each site: tasks target different navigation patterns (search → read, deep-link, table lookup) so the suite exercises more of the locator pipeline per run.

### Decision 4: New `webvoyager-bench` capability spec, plus a delta to `bench-integration`

`bench-integration` already specifies the loader and runner. The `--tier` flag is a runner behaviour change — it belongs as an ADDED requirement in the `bench-integration` delta spec. The Tier-1 dataset itself (schema, content, count) and its tests are new enough to warrant a new `webvoyager-bench` capability spec.

## Risks / Trade-offs

- [Site instability] BBC News or Cambridge Dictionary may change layout between runs, producing false negatives. Mitigation: tasks are chosen to hit well-established, structurally stable pages (e.g. article pages, dictionary entries) rather than live feeds or search result pages.
- [Cost] 12 tasks at ~$0.08 avg = ~$0.96/run at current token prices. This is acceptable for a per-branch gate; monitor and trim if costs rise.
- [--tier 0 regression] Adding `--tier` with default `0` must not change the resolved task path for existing callers. Test coverage explicitly asserts the Tier-0 default path remains `tasks_sample.json`.

## Open Questions

- Should the `--tier` flag eventually accept `--tier 2` for a larger set, or should that be a separate command? Decision deferred — spec only covers 0 and 1 for now.
- Wolfram Alpha blocks headless browsers on some query types. If it proves flaky after Tier-1 baseline, replace with another stable site (e.g. MDN Web Docs). Flag for review after first baseline run.
