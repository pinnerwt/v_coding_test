## Context

`scripts/benchmark.py` is the per-branch CI harness that calls `run_suite` once per case and writes `results.json` + `scoreboard.md`. It currently produces only a single run per case, making it impossible to detect flaky behavior. The eval machinery (`run_suite`, `_run_case`) in `scripts/eval.py` is stable and re-entrant; the repeat loop can be placed entirely in `benchmark.py` without modifying `eval.py`.

`scripts/score.py`'s `generate_scoreboard` reads a flat list of case dicts. The scoreboard per-case row currently renders the `status` string verbatim. When `repeats > 1` the row must instead render a fractional pass rate with a pass/fail glyph.

## Goals / Non-Goals

**Goals:**
- Add `--repeats N` (default `1`) to `scripts.benchmark`.
- Run each case N times sequentially and aggregate into one summary per case.
- Aggregated fields: `repeats` (int), `passed_runs` (int), `median_latency_ms` (int), `p95_latency_ms` (int), `stddev_usd` (float), `avg_mechanism_firings` (float).
- Update `results.json` shape: aggregated fields are present when `repeats > 1`; single-run shape is preserved when `repeats == 1`.
- Update `generate_scoreboard`: `Status` column renders `M/N ✓` or `M/N ✗` when `repeats > 1`; binary string otherwise. Backward-compatible: missing fields fall back to binary rendering.
- Two TDD tests: deterministic-mock (3/3) and flaky-stub (fractional rate).

**Non-Goals:**
- Parallel execution of repeats (sequential is sufficient; parallelism adds shared-state risk with the browser).
- Modifying `eval.py`'s `run_suite` or `_run_case` signatures.
- Per-repeat trace storage (only the aggregated summary is stored in results.json).
- Changing any existing single-run behavior when `--repeats 1`.

## Decisions

### Decision: Repeat loop lives in benchmark.py, not eval.py

**Rationale**: `run_suite` is the per-suite driver shared by both `eval.py` and `bench.py`. Introducing repeat awareness there would couple the core runner to a benchmarking concern. The repeat loop is a thin wrapper that calls `_run_case` directly N times per case. This keeps `eval.py` unchanged and keeps responsibilities separated.

**Alternative considered**: Add a `repeats` parameter to `run_suite`. Rejected because it would bleed benchmarking concerns into the shared evaluation path and complicate the results-file contract for `eval.py` callers.

### Decision: AggregatedCaseResult as a new dataclass

Aggregated runs produce a different shape from `CaseResult`. Rather than overloading `CaseResult` with optional aggregation fields (which would weaken the single-run contract), a new `AggregatedCaseResult` dataclass is introduced in `scripts/benchmark.py`. It carries:

```python
RepeatStatus = Literal["all_pass", "partial", "all_fail", "skipped"]
_VALID_REPEAT_STATUSES: frozenset[str] = frozenset(get_args(RepeatStatus))

@dataclass(frozen=True)
class AggregatedCaseResult:
    id: str
    repeat_status: RepeatStatus          # closed set enforced via _VALID_REPEAT_STATUSES
    repeats: int
    passed_runs: int
    median_latency_ms: int
    p95_latency_ms: int
    stddev_usd: float
    avg_mechanism_firings: float
    # representative single-run fields for backward compat in scoreboard
    status: str                          # "succeeded" if all_pass, "failed" otherwise
    steps: int                           # median steps
    usd: float                           # mean usd
    prompt_tokens: int
    completion_tokens: int
    latency_ms_total: int                # alias for median_latency_ms
    escalations: list[dict]
    replans: int
    cache_events: dict
    failure_class: str | None
    skip_reason: str | None
```

**Closed-set field**: `repeat_status` is typed as `Literal["all_pass", "partial", "all_fail", "skipped"]`. The literal is aliased once at module top-level as `RepeatStatus` and the validator set is derived via `frozenset(get_args(RepeatStatus))`. `__post_init__` checks membership and raises `ValueError` on unknown values.

**Alternative considered**: Reusing `CaseResult` with nullable aggregation fields. Rejected because `frozen=True` dataclasses with many optional fields obscure which combination is valid.

### Decision: results.json backward compatibility

When `repeats == 1`, `benchmark.py` serializes each case with `asdict(case_result)` exactly as today — the JSON shape is unchanged. When `repeats > 1`, each case entry is `asdict(aggregated_result)`, which adds the new aggregation fields. `generate_scoreboard` detects `repeats > 1` by checking `case.get("repeats", 1) > 1`; absence defaults to `1` (binary path).

### Decision: Statistics via stdlib `statistics` module

`statistics.median`, `statistics.pstdev` (population stddev) from the Python stdlib are sufficient. No new dependency is needed.

### Decision: Scoreboard Status column rendering

When `repeats > 1`: render `{passed_runs}/{repeats} ✓` if `passed_runs == repeats`, else `{passed_runs}/{repeats} ✗`.
When `repeats == 1` (or field absent): render `status` string as before.
The rendering logic is a helper `_render_repeat_status(case: dict) -> str` in `score.py`.

### Decision: Representative-run bias for non-aggregated fields

`escalations`, `cache_events`, and `failure_class` on `AggregatedCaseResult` are pulled from a single representative run (`rep_run`), chosen as the last failing run if any exist, otherwise the last run overall. This means a `partial` case (e.g. 2 passing + 1 failing run) shows escalation and cache stats from the failing run, not aggregated across all N runs. Aggregating these (sum of escalations, union of cache events) would be more honest but is out of scope here — the current scoreboard renders these as a representative sample, not as totals. Tracked behavior: a future ticket may revisit if `escalations` totals across repeats become load-bearing for the canary suite.

Note that `replans` is computed differently: it is the per-run mean (rounded to int), not pulled from `rep_run`. This is a deliberate inconsistency with `escalations` — replans are a numeric count where averaging is well-defined, while escalations carry per-attempt structure (tier, intent, outcome) that does not aggregate cleanly. Within-row mixed semantics (mean replans + rep-run escalations) are tracked as part of #51 if cross-row consistency becomes load-bearing.

Similarly, `derived_status="succeeded"` for an `all_pass` aggregate collapses any per-run `unverified` distinction (which is a member of `_PASS_STATUSES`) into the literal `"succeeded"`. This loses forensic detail vs `--repeats 1` mode, but the per-run trace data still records the original status. A future ticket can promote `derived_status` to `rep_run.status` if the unverified distinction becomes operationally important.

**Alternative considered**: Summing `len(escalations)` across runs and taking a union of `cache_events` keys. Rejected for now to keep the dataclass shape stable and to avoid cache-event union semantics that would silently change scoreboard rows when run counts vary.

### Decision: `partial` repeats collapse to `derived_status="failed"`

When `repeat_status == "partial"` (1+ pass and 1+ fail), the derived `status` is `"failed"` and `compute_exit_code` returns non-zero. This treats any flake as a hard CI failure rather than as a soft warning. The motivation in the proposal is "make flakiness *visible*" via the `M/N` rendering — but visibility plus advisory-only would defeat the canary suite's role as a merge gate. A future `near_budget`-style soft annotation (ticket #40) could revisit if "advisory flake" becomes useful, but for now `partial` is treated identically to `all_fail` for exit-code purposes, while the scoreboard still distinguishes them visually via `M/N ✗`.

## Risks / Trade-offs

- [Risk] Sequential N runs multiply wall-clock time N×. → Mitigated by keeping default `--repeats 1`; CI only uses 3 for canary/drift suites.
- [Risk] `AggregatedCaseResult` in `benchmark.py` and `CaseResult` in `eval.py` diverge over time. → Mitigated by having `AggregatedCaseResult` hold a `representative` single-run reference (not duplicating computation logic).
- [Risk] `score.py` becomes coupled to the `repeats` field shape. → Mitigated by the `case.get("repeats", 1)` fallback; old results files continue to render correctly.

## Open Questions

None blocking implementation. The choice to store only the aggregated row (not all N raw runs) in results.json is intentional — raw per-repeat traces are not needed for the scoreboard or canary use cases.
