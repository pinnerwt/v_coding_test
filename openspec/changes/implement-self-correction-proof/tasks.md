## 1. Red tests — CaseResult diagnostic fields

- [ ] 1.1 Write a failing test in `tests/test_eval.py` that constructs `CaseResult` with default values and asserts `escalations == []`, `replans == 0`, `cache_events == {}` (will fail until the fields are added).
- [ ] 1.2 Write a failing test that calls `_aggregate_diagnostics` on a `TraceWriter` with synthetic `SupervisorEvent` + flanking `LocateEvent` rows and asserts the returned escalations list has the expected `from_tier`/`to_tier` entry.
- [ ] 1.3 Write a failing test that calls `_aggregate_diagnostics` on a `TraceWriter` with a `PlanEvent(reason="replan")` row and asserts `replan_count == 1`.
- [ ] 1.4 Write a failing test that calls `_aggregate_diagnostics` on a `TraceWriter` with `LocateEvent(cache_action="invalidate")` and asserts `cache_events["invalidations"] == 1`.

## 2. Red tests — three new eval case assertions

- [ ] 2.1 Write a failing test for `correction-l1-miss-l2-hit` case: mock `loop()` to emit appropriate trace events via the `trace_writer` kwarg; assert `CaseResult.escalations` has an entry with `from_tier="L1_ax"` and `to_tier="L2_dom"`.
- [ ] 2.2 Write a failing test for `correction-replan` case: mock `loop()` to emit a `PlanEvent(reason="replan")` to the trace writer; assert `CaseResult.replans == 1` and `CaseResult.status == "succeeded"`.
- [ ] 2.3 Write a failing test for `maintenance-drift-rename` v2: simulate shared cache across v1/v2 sub-runs; assert `CaseResult.cache_events["invalidations"] >= 1` and `CaseResult.status == "succeeded"`.

## 3. Red tests — score.py mechanism columns

- [ ] 3.1 Write a failing test that calls `generate_scoreboard()` with a results dict containing `escalations`, `replans`, and `cache_events` fields and asserts the output contains `"Escalations"`, `"Replans"`, `"Cache Inv."` in the header and correct counts in the row.
- [ ] 3.2 Write a failing test that asserts `generate_scoreboard()` contains a `"Mechanism firing rates"` block with the three mechanism rows.
- [ ] 3.3 Update the golden snapshot fixture at `tests/fixtures/results/sample_results.json` and `sample_results_scoreboard.md` to include the new columns (update both to maintain consistency; the scoreboard golden test must stay red until `generate_scoreboard` is updated).

## 4. Green — CaseResult fields and _aggregate_diagnostics

- [ ] 4.1 Add `escalations`, `replans`, `cache_events` fields to `CaseResult` dataclass in `scripts/eval.py` with zero/empty defaults.
- [ ] 4.2 Implement `_aggregate_diagnostics(writer: TraceWriter, run_id: str) -> tuple[list[dict], int, dict]` in `scripts/eval.py` that reads trace rows and aggregates the three diagnostic groups.
- [ ] 4.3 Update `_run_case` to construct an in-memory `TraceWriter` and `uuid4()` `run_id`, pass them to `loop()`, call `_aggregate_diagnostics` after, and populate the new `CaseResult` fields.
- [ ] 4.4 Update `_skipped_result` to include the new fields with zero/empty defaults.
- [ ] 4.5 Run `uv run ruff check . && uv run ruff format .` — clean.
- [ ] 4.6 Run `uv run pytest tests/test_eval.py -x` — tests 1.1–1.4 now green.

## 5. Green — three new eval case YAML files and HTML fixtures

- [ ] 5.1 Create `task2/tests/fixtures/correction_l1_miss.html` — `<div class="btn">Submit</div>` with no ARIA role or accessible name.
- [ ] 5.2 Create `task2/eval/cases/correction-l1-miss-l2-hit.yaml` with `fixture: true`, `category: correction`, appropriate task string and budget.
- [ ] 5.3 Create `task2/tests/fixtures/correction_replan_deadend.html` — heading "Dead end", no buttons, no textboxes.
- [ ] 5.4 Create `task2/eval/cases/correction-replan.yaml` with `fixture: true`, `category: correction`, appropriate task string and budget.
- [ ] 5.5 Create `task2/tests/fixtures/drift/rename/v1/index.html` — `<button>Submit</button>`.
- [ ] 5.6 Create `task2/tests/fixtures/drift/rename/v2/index.html` — `<button>Send</button>`.
- [ ] 5.7 Create `task2/eval/cases/maintenance-drift-rename.yaml` with `fixture: true`, `category: drift`, `variants: [v1, v2]`, `shared_cache: true`.

## 6. Green — shared_cache variant expansion in eval runner

- [ ] 6.1 Extend `run_suite` in `scripts/eval.py` to detect `shared_cache: true` in a case dict, construct a single `LocatorCache(path=":memory:")` per parent case, and pass it to each variant's `_run_case` call.
- [ ] 6.2 Update `_run_case` signature to accept an optional `cache` argument forwarded to `loop()`.
- [ ] 6.3 Run `uv run pytest tests/test_eval.py -x` — tests 2.1–2.3 now green.

## 7. Green — score.py mechanism columns

- [ ] 7.1 Update `generate_scoreboard()` in `scripts/score.py` to add `Escalations`, `Replans`, `Cache Inv.` columns to the per-case table header and each row.
- [ ] 7.2 Add the "Mechanism firing rates" block after the tier table.
- [ ] 7.3 Update `tests/fixtures/results/sample_results_scoreboard.md` golden snapshot to match the new output (or regenerate via `score.py`).
- [ ] 7.4 Run `uv run pytest tests/test_score.py -x` — tests 3.1–3.3 now green.
- [ ] 7.5 Run `uv run ruff check . && uv run ruff format .` — clean.

## 8. Green — eval-runner category schema validation

- [ ] 8.1 Add `"correction"` to the allowed `category` values in `load_cases` validation (if the runner validates category); otherwise confirm `load_cases` accepts it without error via existing tests.

## 9. Green — README subsection

- [ ] 9.1 Add a "Self-correction & self-maintenance — measured" subsection to `task2/README.md` that names the three diagnostic cases (`correction-l1-miss-l2-hit`, `correction-replan`, `maintenance-drift-rename`), links to the latest scoreboard sentinel block, and lists the honest gaps (single replan budget, adjacency heuristic for from/to_tier, replan test uses partial mock, vision tier uncached, no transient-failure retry, no post-action assertion, coarse AX fingerprint).

## 10. Verification

- [ ] 10.1 Run the full test suite: `uv run pytest` — all green.
- [ ] 10.2 Verify that temporarily forcing `supervisor.replan_used = True` before the halt check in `loop.py` causes the `correction-replan` case assertion to fail (i.e. `CaseResult.replans == 0`), then revert.
- [ ] 10.3 Run `uv run python scripts/eval.py` (fixture cases only) — all three new cases appear with non-zero diagnostic fields.
- [ ] 10.4 Run `uv run python scripts/score.py` — scoreboard markdown contains the three mechanism columns and the firing rates block.
- [ ] 10.5 Run `uv run ruff check .` — clean.
