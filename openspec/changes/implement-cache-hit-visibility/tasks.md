## 1. Red — failing tests

- [ ] 1.1 In `task2/tests/test_score.py`, add `test_cache_hits_misses_columns_in_header` asserting that `generate_scoreboard(data)` output contains `Cache Hits` and `Cache Misses` in the per-case table header, and that both appear left of `Cache Inv.`
- [ ] 1.2 Add `test_cache_hits_misses_populated_from_cache_events` asserting that a case with `cache_events: {hits: 1, misses: 1, invalidations: 0}` renders `1` in the `Cache Hits` column and `1` in the `Cache Misses` column
- [ ] 1.3 Add `test_cache_hits_misses_default_zero_when_absent` asserting that a case missing the `cache_events` key renders `0` for both `Cache Hits` and `Cache Misses` with no exception
- [ ] 1.4 Run `uv run pytest tests/test_score.py -k "cache_hits_misses" -x` from `task2/` and confirm the three new tests fail (red bar)

## 2. Green — minimal implementation

- [ ] 2.1 In `task2/scripts/score.py`, update the header string in `generate_scoreboard` to add `Cache Hits` and `Cache Misses` immediately left of `Cache Inv.`: change `"| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |"` to include the two new columns
- [ ] 2.2 Update the separator row `"|---|---|---|---|---|---|---|---|---|---|"` to add two more `|---|` segments
- [ ] 2.3 In the per-case row formatter, read `cache_hits = case.get("cache_events", {}).get("hits", 0)` and `cache_misses = case.get("cache_events", {}).get("misses", 0)` alongside the existing `cache_inv`, and insert them into the f-string
- [ ] 2.4 Run `uv run pytest tests/test_score.py -k "cache_hits_misses" -x` and confirm all three new tests pass (green bar)
- [ ] 2.5 Run the full test suite `uv run pytest tests/test_score.py` and confirm no pre-existing tests regressed

## 3. Golden snapshot update

- [ ] 3.1 Regenerate the golden snapshot by running `uv run python -m scripts.score tests/fixtures/results/sample_results.json > tests/fixtures/results/sample_results_scoreboard.md` from `task2/`
- [ ] 3.2 Run `uv run pytest tests/test_score.py::test_score_golden_snapshot_matches` and confirm it passes

## 4. Full test suite and lint

- [ ] 4.1 Run `uv run pytest tests/test_score.py tests/test_eval.py` and confirm all pass
- [ ] 4.2 Run `uv run ruff check . && uv run ruff format --check .` from `task2/` and confirm clean
