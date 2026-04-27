## Context

`CaseResult` today has `status` (one of `succeeded / unverified / failed / blocked / timeout / skipped`) but no structured reason when that status is `failed`. `_run_case` already materialises the full event trace via `_aggregate_diagnostics`; the raw ingredients for classification (event kinds, validator outcomes, last `SupervisorEvent`) are already in hand after that call. The gap is purely the classification step and the field to hold its result.

`scripts/score.py` renders a Markdown scoreboard table; the failure class must surface there to be useful to a human reader.

## Goals / Non-Goals

**Goals:**
- Add `failure_class` and `failure_detail` to `CaseResult` with `None` defaults for backward compatibility.
- Add `_classify_failure(events, validators, status)` that maps trace + validator signals to a `failure_class` literal.
- Call `_classify_failure` from `_run_case` after `_aggregate_diagnostics`, populate `CaseResult`.
- Surface `failure_class` in the `score.py` scoreboard table (one column, value or `-`).
- Cover all 8 `failure_class` values plus the None path with synthetic-trace tests.

**Non-Goals:**
- Changing the `Run.final.failure` shape stored by the agent in the trace DB — the classification lives only in the eval layer.
- Surfacing `failure_detail` in the scoreboard (too verbose for a table; `failure_class` is sufficient).
- Classifying `blocked`, `timeout`, or `skipped` cases — those statuses are self-explanatory; the literal maps directly.
- ML-based failure classification; pure heuristics from the event sequence.

## Decisions

### Decision: Priority ordering of classification rules

Multiple signals can fire at once (e.g. a case can exceed budget AND have a failed validator). We need a deterministic winner. Proposed priority (highest to lowest):

1. `supervisor_halt` — a `SupervisorEvent(policy="halt")` is present. Supervisor explicitly gave up; this is richer than a generic tool error.
2. `locator_miss` — a `SupervisorEvent(policy="next_tier")` with no successful subsequent tier (i.e. `to_tier=None` in escalations). Means the locator pipeline exhausted all tiers without resolving.
3. `tool_error` — an `ActEvent(outcome="error")` is present. Generic browser-level error.
4. `validator_fail` — at least one validator returned `ok=False` AND `status in {"failed", "unverified"}`. Separate from the above because the agent reached `done` but the output was wrong.
5. `schema_error` — a `DoneEvent` is present but `verifier.ok=False`. The agent called `done` but the schema/evidence check failed.
6. `no_done_emitted` — no `DoneEvent` in the trace at all and `status == "failed"`. Agent ran out of strategy without calling `done`.
7. `other` — catch-all for any `failed` status that doesn't match the above.

For non-`failed` statuses the function returns `None` immediately (no classification needed for `succeeded`, `unverified`, `skipped`, `blocked`, `timeout` — those are self-describing).

Alternative considered: classify `blocked` and `timeout` too. Rejected: they are already unambiguous; adding classification noise for them would dilute the column's signal for the cases that actually need it.

### Decision: `_classify_failure` takes `events: list[AnyEvent]`, `validators: list[dict]`, `status: str`

Avoids coupling to `TraceWriter` internals — `_run_case` already has `events` from `_aggregate_diagnostics` materialising them via `list(writer.iter_events(run_id))`. Passing the materialized list as a positional arg keeps the function pure and trivially unit-testable with synthetic event lists.

Alternative considered: pass `writer` and `run_id` directly and call `iter_events` inside. Rejected: that couples the classifier to I/O and makes unit tests require a real `TraceWriter` with a SQLite in-memory session.

### Decision: `failure_class` is `str | None` in the dataclass, validated by a `Literal` type alias

Using `Literal[...]` as a type annotation in the `@dataclass` field with a `None` default keeps the JSON serialisation trivial (`asdict` just emits the string or `null`) and avoids a dependency on Pydantic or an `Enum`. The Literal annotation is documentation + type-checker-checked, not runtime-enforced (dataclasses don't validate on `__init__`). This is consistent with how `status` is typed in the existing `CaseResult`.

## Risks / Trade-offs

- **Risk**: Priority ordering disagrees with what a human would call the "real" cause for edge cases (e.g. supervisor halted because of a tool error — which class wins?). → Accepted: the detail string captures the nuance; the class is for grouping/filtering, not a complete explanation.
- **Risk**: `DoneEvent` absence heuristic mis-classifies a case where the loop was interrupted mid-run by an exception path. → Mitigation: exception path in `_run_case` sets `status="failed"` and `validators=[{"name": "exception", ...}]`; `_classify_failure` will see `no_done_emitted` (correct) or `tool_error` (also reasonable); either is more signal than blank.
- **Risk**: New fields break existing code that constructs `CaseResult` positionally. → Mitigation: fields are appended with `None` defaults; `@dataclass(frozen=True)` already requires keyword args for non-default fields; the new fields follow the existing pattern of all-default trailing fields.

## Migration Plan

Additive changes only. No schema or DB migrations. Existing results JSON files from prior runs will simply lack `failure_class` / `failure_detail` keys; `score.py` SHALL default to `-` for missing keys. Zeabur deployment: standard `uv sync` + restart.
