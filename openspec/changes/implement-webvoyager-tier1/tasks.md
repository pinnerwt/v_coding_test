## 1. Red — failing tests first (TDD)

- [x] 1.1 In `task2/tests/test_bench.py`, add a test `test_tier1_fixture_exists` that asserts `task2/eval/bench/data/webvoyager/tier1.json` exists. Run `uv run pytest tests/test_bench.py::test_tier1_fixture_exists -x` from `task2/` and confirm it fails with `AssertionError` (file not found).
- [x] 1.2 In `task2/tests/test_bench.py`, add a test `test_tier1_loader_returns_12_cases` that calls `load_webvoyager` on the Tier-1 path and asserts the result length is 12 and each case has `task`, `domain`, `category`, `id` keys. Run and confirm failure (file not found).
- [x] 1.3 In `task2/tests/test_bench.py`, add a test `test_tier1_no_excluded_domains` that asserts none of `["Allrecipes", "Apple", "Coursera", "Google", "Booking", "Amazon"]` appear in any `category` field of the 12 cases. Run and confirm failure.
- [x] 1.4 In `task2/tests/test_bench.py`, add a test `test_bench_tier_flag_default_selects_tier0` that patches the loader and calls `main(["--suite", "webvoyager"])`, asserting the loader was called with a path ending in `tasks_sample.json`. Run and confirm failure (`unrecognized arguments: --tier` not yet the error — more likely `SystemExit` or `AttributeError`).
- [x] 1.5 In `task2/tests/test_bench.py`, add a test `test_bench_tier1_flag_selects_tier1_path` that patches the loader and calls `main(["--suite", "webvoyager", "--tier", "1"])`, asserting the loader was called with a path ending in `tier1.json`. Run and confirm failure.
- [x] 1.6 In `task2/tests/test_bench.py`, add a test `test_bench_webvoyager_tasks_env_overrides_tier1` that sets `WEBVOYAGER_TASKS` to a custom path and calls `main(["--suite", "webvoyager", "--tier", "1"])`, asserting the loader is called with the env-var path. Run and confirm failure.

## 2. Green — Tier-1 dataset

- [x] 2.1 Create directory `task2/eval/bench/data/webvoyager/` (add `__init__.py` if needed for Python packaging — check if `eval/bench/data/` needs it).
- [x] 2.2 Author `task2/eval/bench/data/webvoyager/tier1.json` with exactly 12 entries across the approved domains: Wikipedia (×2), arXiv (×2), GitHub (×2), HuggingFace (×2), BBC News (×2), Cambridge Dictionary (×1), Wolfram Alpha (×1). Each entry must have `id`, `web_name`, `ques`, `web` fields. Use unique string `id` values `"101"`–`"112"` (to avoid collision with Tier-0 IDs `"1"`–`"3"`).
- [x] 2.3 Run `uv run pytest tests/test_bench.py::test_tier1_fixture_exists tests/test_bench.py::test_tier1_loader_returns_12_cases tests/test_bench.py::test_tier1_no_excluded_domains -x` from `task2/` and confirm all three pass.

## 3. Green — --tier flag in bench runner

- [x] 3.1 In `task2/scripts/bench.py`, add `--tier` argument: `parser.add_argument("--tier", type=int, choices=[0, 1], default=0)`. Extend `_DEFAULT_TASK_PATHS` to a nested dict keyed by `(suite, tier)` — or use a two-level dict — mapping `("webvoyager", 0)` to the existing Tier-0 path and `("webvoyager", 1)` to `eval/bench/data/webvoyager/tier1.json`. Update the path-resolution line to use `args.tier`. The `WEBVOYAGER_TASKS` env-var override must still take precedence.
- [x] 3.2 Run `uv run pytest tests/test_bench.py::test_bench_tier_flag_default_selects_tier0 tests/test_bench.py::test_bench_tier1_flag_selects_tier1_path tests/test_bench.py::test_bench_webvoyager_tasks_env_overrides_tier1 -x` from `task2/` and confirm all three pass.
- [x] 3.3 Run the full test suite `uv run pytest tests/test_bench.py -x` and confirm no regressions.

## 4. Lint and format

- [x] 4.1 Run `uv run ruff check --fix task2/scripts/bench.py task2/tests/test_bench.py` from repo root and resolve any issues.
- [x] 4.2 Run `uv run ruff format task2/scripts/bench.py task2/tests/test_bench.py` and confirm no diff.

## 5. README documentation

- [x] 5.1 Add a "WebVoyager benchmark" section to `task2/README.md` covering: Tier-0 vs Tier-1 distinction, site-inclusion criteria, excluded domains with reasons, Tier-0 baseline results (2026-04-28: 2/3 passed, webvoyager-2 9 steps $0.1146, webvoyager-3 6 steps $0.0405, webvoyager-1 failed HTTP 400).
- [x] 5.2 Verify the README section satisfies the spec scenarios: contains "WebVoyager", "Tier-0"/"Tier-1", and at least one excluded domain name.

## 6. Baseline capture (manual, not committed)

- [ ] 6.1 After implementation is merged, run `uv run python -m scripts.bench --suite webvoyager --tier 1 --live` from `task2/` with the local Qwen endpoint available. Copy the resulting `eval/results/<ts>.json` to `task2/benchmark/<branch>/webvoyager/tier1.json` and commit it as the Tier-1 baseline. (Deferred: manual post-merge step, per spec "not committed here".)

## 7. Final verification

- [x] 7.1 Run `uv run pytest task2/ -x` from repo root and confirm the full task2 test suite is green.
- [x] 7.2 Run `git status --porcelain` and confirm only expected files are modified (no accidental changes outside `task2/`).
- [x] 7.3 Run `openspec validate implement-webvoyager-tier1 --strict` and confirm it exits 0.
