# Design

## Goal

Surface a soft-budget warning so a case that consumed ≥80% of any of its declared `budget.{steps,usd,seconds}` is visually distinguishable in the scoreboard from a case that comfortably succeeded at <80%. The warning gives early notice of regressions before they tip a case over the cliff into `timeout`/`blocked`.

## Decisions

- **Threshold = 0.80, not configurable.** Ticket #40 explicitly asks for an "≥80%" trip. Adding a knob would expand scope; if the threshold proves wrong in practice it can be tuned in a follow-up. The constant `_NEAR_BUDGET_THRESHOLD` is module-level so it is greppable from a future tuning ticket.
- **Suppress on non-passing statuses.** A `failed`/`timeout`/`blocked` case that happens to land at 90% of its step budget is *already* failing — the warning glyph adds no signal there and would visually compete with the existing failure-classification rendering. The flag is therefore only set when `status ∈ {succeeded, unverified}`. Skipped cases also remain `False`.
- **Compute in `_run_case`, not at scoreboard render time.** The flag belongs in the results JSON because (a) downstream consumers (`baseline_diff.py`, trend SVGs) may want to graph "% of cases at near_budget" later, and (b) the scoreboard renderer should not need to re-derive the flag from `steps`/`usd`/`latency_ms_total` against `budget` — that's a separable concern from rendering.
- **Single helper `_is_near_budget`.** Pulling the threshold logic out of `_run_case` makes it directly unit-testable across the three axes without having to construct full `RunResult` + browser stubs each time. `_run_case` also gets a one-line call site, which keeps the success-path return readable.
- **Axis-omission tolerance.** The eval-runner spec already defines `budget.{steps,usd,seconds}` as required at the case-YAML level, but `_run_case` reads `case.get("budget", {})` defensively in `_open_trace_run`. The helper mirrors that defensiveness — `_is_near_budget` returns `False` on any axis whose budget key is missing or non-positive — so a future change that loosens the `budget` schema (e.g. dropping `seconds` for fixture-only cases) does not crash the warning computation.
- **Ratio convention.** Latency comes in as `latency_ms_total` (milliseconds, integer); the budget axis is `seconds`. The helper divides by 1000 inside the ratio calculation rather than asking the caller to convert, so the call site at `_run_case` reads naturally: `_is_near_budget(run_result.steps, run_result.usd, run_result.latency_ms_total, case.get("budget", {}))`.
- **Render as suffix, not column.** Adding a separate "⚠️" column to the per-case table would widen the table and break existing snapshot tests in `task2/tests/test_score*`. Suffixing the existing Status cell is non-disruptive: snapshots that pinned `succeeded` still match against `succeeded` substring (the `_render_case_status` tests use `in` containment, not equality, so the suffix passes through). The single space before the glyph is intentional — markdown table cells render the joined string verbatim.

## Why this is not over-engineered

- No new file is created; both edits land in existing modules (`scripts/eval.py`, `scripts/score.py`).
- No backwards-compat shim is needed — the new field defaults to `False` and is consumed only by `_render_case_status`'s `case.get(...)` lookup, so old results JSONs still render cleanly.
- No abstraction for "warning glyphs" in general — there is exactly one warning today, and the second hypothetical user is the regression-onset report (#55), which can read the boolean directly when it lands.

## Open trade-offs (deferred to future tickets)

- The trends SVGs (`scripts/trends.py`) and the auto-diff (`scripts/baseline_diff.py`) do not yet consume the `near_budget` flag. A `Δ near_budget cases` line in the auto-diff would be a useful follow-up but is out of scope here — the immediate ask is the scoreboard warning.
- The threshold is hard-coded at 0.80; a future ticket could expose it via env var or per-suite override if the WebVoyager Tier-1 suite (#63) wants a tighter or looser bar than the fixture suite. Not blocking.
