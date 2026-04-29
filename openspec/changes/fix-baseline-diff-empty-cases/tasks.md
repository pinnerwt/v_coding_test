## 1. Red — failing tests

- [x] 1.1 In `task2/tests/test_baseline_diff.py`, add `test_empty_master_emits_na_pass_rate` — assert `generate_diff_markdown({"run_at": "...", "cases": []}, branch_non_empty)` contains `Δ pass-rate: n/a (master had 0 ran cases)`.
- [x] 1.2 Add `test_empty_master_emits_na_usd` — assert same call contains `Δ total USD: n/a (master had 0 ran cases)`.
- [x] 1.3 Add `test_empty_master_emits_na_latency` — assert same call contains `Δ p50 latency: n/a (master had 0 ran cases)` and `Δ p95 latency: n/a (master had 0 ran cases)`.
- [x] 1.4 Add `test_empty_master_does_not_emit_plus_zero_pct` — assert output does NOT contain `Δ pass-rate: +0%`.
- [x] 1.5 Add `test_empty_branch_emits_na` — assert `generate_diff_markdown(master_non_empty, {"run_at": "...", "cases": []})` contains `Δ pass-rate: n/a (branch had 0 ran cases)`, `Δ total USD: n/a (branch had 0 ran cases)`, `Δ p50 latency: n/a (branch had 0 ran cases)`, `Δ p95 latency: n/a (branch had 0 ran cases)`.
- [x] 1.6 Add `test_both_empty_emits_na_both_sides` — assert `generate_diff_markdown({"run_at": "...", "cases": []}, {"run_at": "...", "cases": []})` contains `Δ pass-rate: n/a (both sides had 0 ran cases)` and likewise for USD and latency lines.
- [x] 1.7 Run `uv run pytest task2/tests/test_baseline_diff.py -x` from `task2/` and confirm the new tests fail with `AssertionError` (current code emits `+0%` / `+$0.0000`).

## 2. Green — minimal implementation

- [ ] 2.1 In `task2/scripts/baseline_diff.py::generate_diff_markdown`, after computing `m_ran` and `b_ran`, derive an `_empty_reason` string: `"master had 0 ran cases"` if only `m_ran == 0`, `"branch had 0 ran cases"` if only `b_ran == 0`, `"both sides had 0 ran cases"` if both are zero, and `None` otherwise.
- [ ] 2.2 When `_empty_reason` is not `None`, replace the four aggregate lines (`Δ pass-rate`, `Δ total USD`, `Δ p50 latency`, `Δ p95 latency`) with `n/a (<_empty_reason>)` variants; still emit the `Cases:` annotation line using the existing logic.
- [ ] 2.3 Run `uv run pytest task2/tests/test_baseline_diff.py -x` from `task2/` and confirm all tests pass (new and existing).

## 3. Full suite

- [ ] 3.1 Run `uv run pytest task2/tests/` from `task2/` and confirm no regressions in the broader test suite.

## 4. Clean — lint and format

- [ ] 4.1 `uv run ruff check --fix .` from `task2/`.
- [ ] 4.2 `uv run ruff format .` from `task2/`.
- [ ] 4.3 `uv run ruff check .` from `task2/` — confirm zero errors, zero warnings.
- [ ] 4.4 `uv run pytest` from `task2/` — confirm green bar after formatting.
