## Why

The current `--suite webvoyager` runner uses only the 3-task Tier-0 sample (`tasks_sample.json`), which is too small to detect regressions and biases toward the simplest sites. Tier-1 (12 curated tasks) is the smallest credible "does the agent generalise to a random task" signal cheap enough to run per branch.

## What Changes

- Vendor a curated 12-task Tier-1 dataset at `task2/eval/bench/data/webvoyager/tier1.json`, preserving the upstream `id`/`web_name`/`ques`/`web` schema so `load_webvoyager` works unchanged.
- Add a `--tier` CLI flag to `scripts/bench.py` (values `0` and `1`; default `0`) that selects between the Tier-0 sample and the Tier-1 dataset. The selected path can also be overridden via the existing `WEBVOYAGER_TASKS` env var.
- Capture a Tier-1 baseline result under `task2/benchmark/<branch>/webvoyager/tier1.json`.
- Document the site-selection rationale in `task2/README.md` under a "WebVoyager benchmark" section.
- Add tests: (a) loader test asserting the vendored Tier-1 file deserialises via `load_webvoyager` and yields 12 cases with `task`, `domain`, `category`, and `id` keys populated; (b) runner test (mocked LLM, no `--live`) asserting `--tier 1` selects the Tier-1 fixture path.

Excluded from Tier-1 intentionally: Allrecipes, Apple, Coursera, Google-Search, Booking, Flights, Amazon — each requires login, CAPTCHA, or location-aware widgets that make results non-deterministic.

## Capabilities

### New Capabilities

- `webvoyager-bench`: Tier-1 curated task dataset, `--tier` CLI flag selection, and associated tests and baseline capture. The `load_webvoyager` loader contract (in `bench-integration`) is reused unchanged.

### Modified Capabilities

- `bench-integration`: Extend the bench runner requirement to cover the `--tier` flag and Tier-1 fixture path selection via flag or env override.

## Impact

- `task2/scripts/bench.py` — adds `--tier` argument.
- `task2/eval/bench/data/webvoyager/tier1.json` — new vendored dataset.
- `task2/tests/test_bench.py` — new test cases for Tier-1 loader and runner.
- `task2/README.md` — new "WebVoyager benchmark" section.
- `task2/benchmark/<branch>/webvoyager/tier1.json` — new baseline capture (not committed to source control; captured at run time).
