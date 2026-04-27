## Context

The agent has three live self-correction mechanisms:

1. **Escalation ladder** (`agent/locate.py:466-487`, `agent/loop.py:188-198`, `agent/supervisor.py`): L1 miss → L2 via `Supervisor.handle()`.
2. **Supervisor halt → one-shot replan** (`agent/loop.py:433-451`): when `supervisor.last_policy == "halt"` and `replan_used is False`, `plan_module.replan()` is called and a `PlanEvent(reason="replan")` is emitted.
3. **AX-fingerprint cache invalidation** (`agent/locate.py:454-463`, `agent/locator_cache.py:166-170`): when the cached selector still resolves but the AX fingerprint of the live element differs from the stored one, `cache.invalidate()` is called and the L1–L4 ladder runs fresh.

All three fire in production. The trace records them: `SupervisorEvent` for escalations, `PlanEvent(reason="replan")` for replans, `LocateEvent(cache_action="invalidate")` for cache invalidations. But `_run_case` in `scripts/eval.py` never reads the trace, so `CaseResult` has no evidence of them. The eval never asserts they fire, meaning the brief's "substance" criterion is unverifiable.

This change closes the gap by:

(a) passing a per-case `TraceWriter` (in-memory SQLite) to `loop()` inside `_run_case`, then reading the trace after the run to populate three new diagnostic fields on `CaseResult`;

(b) authoring three new fixture cases whose only success path requires a specific mechanism;

(c) adding per-case assertions in `test_eval.py` that the diagnostic fields are non-zero for those cases;

(d) extending `score.py` to surface the new columns;

(e) adding a README subsection with honest gaps.

## Goals / Non-Goals

**Goals:**

- `CaseResult` gains `escalations: list[dict]`, `replans: int`, `cache_events: dict` with zero/empty defaults; these are populated from trace rows when a `TraceWriter` is available.
- `_run_case` creates an in-memory `TraceWriter` and a `run_id` per case, passes both to `loop()`, reads trace rows after `loop()` returns, aggregates them into the new fields.
- Three new YAML cases exercise L1→L2 escalation, halt→replan, and cache invalidation end-to-end. Each has `fixture: true`. Their supporting HTML fixtures are minimal static pages.
- Assertions in `test_eval.py` for the three cases fail if the mechanism is disabled in code.
- `generate_scoreboard()` in `score.py` emits mechanism columns without breaking the existing format.
- README subsection is added listing the three diagnostic cases and honest gaps.
- TDD: failing test first for every behavioral change.

**Non-Goals:**

- Changing the trace schema (`LocateEvent`, `SupervisorEvent`, `PlanEvent` already carry the fields we need).
- Adding L2→L3 or L3→L4 escalation (out of scope; the escalation table in `supervisor.py` covers only L1→L2).
- Transient-failure retries, post-action assertions, or multi-replan budgets — these are documented as honest gaps in README.
- Vision tier (`L4_vision`) cache entries — vision results are intentionally not cached (`locate()` invalidates L4 cache entries on probe).
- Changing the replan budget (it stays at 1 per `supervisor.replan_used`).

## Decisions

### D1: In-memory `TraceWriter` per case run — no file I/O in CI

**Decision**: `_run_case` constructs `TraceWriter(path=":memory:")` and a fresh `uuid4()` `run_id` before calling `loop()`. After `loop()` returns, it reads events from the in-memory SQLite to aggregate the new fields, then discards the writer. The trace is not persisted to disk.

**Rationale**: The trace-reader needs event rows to aggregate from; the existing `loop()` signature already accepts `trace_writer` and `run_id`. In-memory is sufficient for the aggregation use case and avoids file-path coordination across parallel runs.

**Alternative**: Read events from a file-backed trace database. Rejected — adds path-management complexity without benefit; the aggregation is local to the case run.

**Alternative**: Add counters directly to `RunResult` instead of reading the trace. Rejected — `RunResult` is already well-scoped to loop-level metrics; diagnostic mechanism fields are eval-layer concerns (they aggregate across event kinds), and ticket #20's design explicitly deferred them.

### D2: Trace aggregation in a single helper function `_aggregate_diagnostics(writer, run_id)`

**Decision**: After `loop()` returns, `_run_case` calls a module-level function `_aggregate_diagnostics(writer: TraceWriter, run_id: str) -> tuple[list[dict], int, dict]` that:

- Queries `traces_events WHERE run_id = ?` ordered by `seq`, deserialises each payload with `AnyEvent` / `TypeAdapter`.
- Collects `SupervisorEvent` rows → `escalations` list (each entry: `{intent: ..., from_tier: ..., to_tier: ..., reason: ...}`). `from_tier` is the `classified_as` field's implicit tier context (derived from the preceding `LocateEvent` in sequence); `to_tier` is read from... see Decision D3.
- Counts `PlanEvent(reason="replan")` rows → `replans`.
- Counts `LocateEvent(cache_action=...)` rows → `cache_events = {hits, invalidations, misses}`.

**Rationale**: Keeping aggregation in one function makes it testable in isolation and keeps `_run_case` readable.

### D3: `escalations` entry shape — `from_tier` and `to_tier` from adjacent `LocateEvent` rows

**Decision**: Each `SupervisorEvent` is immediately preceded in sequence by the `LocateEvent` that triggered it (same `step_id`, lower `seq`). `from_tier` = `preceding_locate_event.tier`; `to_tier` = the tier of the next `LocateEvent` in the same step that has `outcome="hit"` (or the first locate event in the next batch if none in the same step). If no following hit exists in the trace (e.g. the escalation led to `halt`), `to_tier` = `None`.

**Alternative**: Derive `to_tier` from the `SupervisorEvent.policy` field mapping. Rejected — `policy="next_tier"` gives the escalation intent but not the concrete tier that was actually tried. Adjacent `LocateEvent` rows are ground truth.

**Caveat/simplification**: For the three new cases, the event sequence is deterministic and short. If the adjacency heuristic proves fragile for longer traces, a follow-up can add an explicit `to_tier` field to `SupervisorEvent`. This is recorded as an honest gap in the README.

### D4: New fixture case `correction-replan.yaml` — how to force a halt that triggers replan

**Decision**: The fixture HTML at `tests/fixtures/correction_replan_deadend.html` is a page with a heading "Dead end" and no actionable elements. The agent's LLM is mocked in the eval test to first call `read` with an intent that misses both L1 and L2 (causing the supervisor to `halt`), then (after replan) call `done` to succeed. The eval test for this case mocks `loop()` partially: it patches `agent.supervisor.Supervisor.handle` to return `policy="halt"` on the first call, and patches `agent.plan.replan` to return a plan whose single step is "call done". The LLM itself is stubbed at the `LLMClient.chat` level.

**Alternative**: Use a fully live (Playwright) run with a real fixture page. Rejected for the eval-assertion tests — the goal is a fast, deterministic CI fixture; Playwright-backed tier tests are already covered by `test_drift.py`. The eval assertions need to be reliable without a running browser.

**Alternative**: Trigger the halt via `max_attempts` exceeded in `Supervisor`. This is the actual code path in production; in tests we patch `handle` directly to avoid depending on the exact number of locate attempts the LLM would make.

### D5: `maintenance-drift-rename.yaml` — shared cache across variants

**Decision**: The new `maintenance-drift-rename.yaml` case uses `variants: [v1, v2]` with a new optional field `shared_cache: true`. When `_run_case` sees `shared_cache: true`, it reuses a single `LocatorCache` instance across all sub-runs of the same parent case, passing it to each `loop()` call. The `_expand_variants` path in `run_suite` is extended to group variant sub-runs by parent case ID and share the cache object within each group.

**Rationale**: To demonstrate cache invalidation, the cache must be warm on v1 data when v2 runs. In-process sharing via a single `LocatorCache(path=":memory:")` instance is the simplest mechanism.

**Alternative**: A file-backed shared cache at a temp path. Rejected — in-memory is sufficient and avoids temp-file cleanup.

**Alternative**: Run v1 and v2 sequentially without a shared cache and assert zero cache hits for v2. Rejected — that doesn't prove invalidation fired; it only proves the cache was empty, which is trivially true.

### D6: `score.py` mechanism columns — appended after existing per-case table columns

**Decision**: The per-case table gains three new columns: `Escalations`, `Replans`, `Cache Inv.` appended to the right of the existing `Tokens (P+C)` column. The summary block gains a "Mechanism firing rates" sub-block after the tier table:

```
| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | N/M |
| Replan | N/M |
| Cache invalidation | N/M |
```

**Alternative**: Separate second table. Using the same per-case table is more compact and reviewers can see per-case values alongside other metrics.

## Risks / Trade-offs

- **Adjacency heuristic for `from_tier`/`to_tier` in `_aggregate_diagnostics`** → Mitigation: the three new cases have short deterministic traces; document as a known limitation in README.
- **Mocked replan test may not catch loop.py regressions** → Mitigation: the README subsection lists "replan path exercised via partial mock" as an honest gap; full end-to-end coverage requires a live LLM call.
- **`shared_cache: true` complicates `_expand_variants`** → Mitigation: the logic is localised to `run_suite`; `_expand_variants` itself is unchanged (it only expands IDs). The shared cache is managed at the `run_suite` level where iteration over variant sub-runs happens.
- **Ruff compliance** → All new production code must pass `uv run ruff check .` and `uv run ruff format .` before the change is considered done.
