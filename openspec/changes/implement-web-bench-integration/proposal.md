## Why

The eval suite only covers hand-authored cases, giving no external signal of how the agent fares on independently-defined browser tasks. Integrating an established public benchmark provides a reproducible, community-validated measurement point and surfaces failure modes outside our own test-case biases.

## What Changes

- New research brief `prompts/task2/web-benchmarks.md` covering seven public web-agent benchmarks (WebArena, Mind2Web / Online-Mind2Web, BrowserGym, WebVoyager, MiniWoB++, WebShop, GAIA web subset), with per-benchmark: license, scope, hosting cost, task format, headline metric, and a concrete recommendation.
- New benchmark loader `task2/eval/bench/webvoyager_loader.py` that parses the WebVoyager task JSON format into our `Case` schema.
- Vendored fixture `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json` (3–5 entries from the upstream task file).
- New runner entry `task2/scripts/bench.py` invoked as `uv run python -m scripts.bench --suite webvoyager`, which runs the benchmark cases through the existing `run_suite` machinery and writes `eval/results/<ts>.json` with the existing shape.
- New test module `task2/tests/test_bench.py` covering: (a) loader parses the vendored fixture into `Case`-compatible dicts; (b) runner smoke test executes one benchmark case against a stubbed browser and stubbed LLM, asserts the result JSON shape matches the existing `CaseResult` schema; (c) brief file exists at the expected path and lists the selected benchmark.

## Capabilities

### New Capabilities

- `bench-integration`: Benchmark loader + runner entry (`scripts/bench.py`) that ingests an upstream benchmark's task format (WebVoyager JSON) into our `Case` schema and produces a `eval/results/<ts>.json` with the existing shape. Covers the loader, vendored fixture, and the `--suite` CLI entry point.
- `bench-research-brief`: Research document at `prompts/task2/web-benchmarks.md` covering the surveyed benchmarks and making a concrete integration recommendation.

### Modified Capabilities

- `eval-runner`: No requirement changes to `run_suite` itself. The bench runner delegates to `run_suite`, so this spec is consumed but not changed.

## Impact

- **New files**: `prompts/task2/web-benchmarks.md`, `task2/eval/bench/__init__.py`, `task2/eval/bench/webvoyager_loader.py`, `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json`, `task2/scripts/bench.py`, `task2/tests/test_bench.py`.
- **Modified files**: none.
- **Dependencies**: no new Python packages required (WebVoyager task list is plain JSON; `json` is stdlib).
- **Env vars**: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` unchanged. `EVAL_RESULTS_DIR` honored as in `eval.py`.
- **Existing modules**: `scripts/eval.py` is consumed (imports `run_suite`, `load_cases`-style logic) but not structurally modified.
