## 1. Tests (Red first)

- [x] 1.1 Create `task2/tests/fixtures/results/master_results.json` — synthetic master baseline with two cases: `fixture-a` (succeeded) and `fixture-b` (failed), non-zero metrics.
- [x] 1.2 Create `task2/tests/fixtures/results/branch_results.json` — branch variant where `fixture-a` is failed (regression), `fixture-b` is succeeded (improvement), `fixture-c` is succeeded (new case).
- [x] 1.3 Write `task2/tests/test_baseline_diff.py` with failing tests covering: regression marker present, improvement marker present, new-case row, no-op branch produces no regression/improvement, aggregate deltas (pass-rate, USD, latency) are correctly signed, missing baseline path in `benchmark.py` write path skips `diff.md` gracefully, master branch write path skips `diff.md`.
- [x] 1.4 Write failing tests in `task2/tests/test_score.py` for the `--diff` flag: combined scoreboard + diff output contains separator and `Δ vs master`; missing path exits with code 1; omitting `--diff` leaves output unchanged.
- [x] 1.5 Run `uv run pytest task2/tests/test_baseline_diff.py task2/tests/test_score.py -x` — confirm all new tests fail for the right reasons (import errors / assertion errors, not syntax errors).

## 2. Core Implementation — baseline_diff.py

- [ ] 2.1 Create `task2/scripts/baseline_diff.py` with `generate_diff_markdown(master: dict, branch: dict) -> str`.
- [ ] 2.2 Implement case-matching by `id`, classify each case into `regression / improvement / unchanged / new / dropped`.
- [ ] 2.3 Emit per-case delta table (columns: `Case`, `Master status`, `Branch status`, `Delta`) with `⚠️ REGRESSION` / `✅ IMPROVEMENT` markers.
- [ ] 2.4 Compute and emit aggregate delta lines: Δ pass-rate (%), Δ total USD ($), Δ p50 latency (ms), Δ p95 latency (ms) — all signed.
- [ ] 2.5 Emit header with `run_at` timestamps from both dicts.
- [ ] 2.6 Run `uv run pytest task2/tests/test_baseline_diff.py -x` — confirm diff unit tests pass.

## 3. Integration — benchmark.py write_diff

- [ ] 3.1 Add `write_diff(branch: str, branch_data: dict, *, benchmark_root: Path) -> None` to `task2/scripts/benchmark.py`.
- [ ] 3.2 Guard: return early if `sanitize_branch(branch) == "master"`.
- [ ] 3.3 Guard: return early (with stderr message) if `benchmark_root / "master" / "results.json"` does not exist.
- [ ] 3.4 Load master data, call `generate_diff_markdown`, write to `benchmark_root / sanitize_branch(branch) / "diff.md"`.
- [ ] 3.5 Call `write_diff` from `write_outputs` (or from `main` immediately after `write_outputs`).
- [ ] 3.6 Run `uv run pytest task2/tests/test_baseline_diff.py -x` — confirm `write_diff` integration tests pass.

## 4. score.py --diff flag

- [ ] 4.1 Add `--diff` optional argument to `scripts/score.py` argparser (metavar `BASELINE_RESULTS_JSON`).
- [ ] 4.2 When `--diff` is provided and file exists: load baseline JSON, call `generate_diff_markdown(baseline, branch_data)`, append `\n---\n` + diff output to scoreboard.
- [ ] 4.3 When `--diff` path does not exist: print error to stderr, exit with code 1.
- [ ] 4.4 Run `uv run pytest task2/tests/test_score.py -x` — confirm `--diff` tests pass.

## 5. CI Workflow — PR comment step

- [ ] 5.1 Add `pull-requests: write` to the workflow permissions block in `.github/workflows/task2-benchmark.yml`.
- [ ] 5.2 Add a new step after `Verify benchmark recorded for branch` that:
  - is conditional on `github.event_name == 'pull_request'`
  - checks if `task2/benchmark/${{ github.head_ref }}/diff.md` exists
  - if absent, prints a notice and exits 0
  - if present, runs `gh pr comment --edit-last --body-file <path> 2>/dev/null || gh pr comment --body-file <path>`
- [ ] 5.3 Verify workflow YAML is valid (`yamllint` or `actionlint` if available, or visual inspection).

## 6. Linting and final green bar

- [ ] 6.1 Run `uv run ruff check task2/scripts/baseline_diff.py task2/scripts/benchmark.py task2/scripts/score.py` — fix any lint errors.
- [ ] 6.2 Run `uv run ruff format task2/scripts/baseline_diff.py task2/scripts/benchmark.py task2/scripts/score.py`.
- [ ] 6.3 Run full test suite `uv run pytest task2/tests/ -x` — confirm all tests pass.
- [ ] 6.4 Verify `task2/benchmark/master/results.json` exists (pre-condition for real diff on any non-master branch).
