## Context

`TraceWriter` stores events in a SQLite table (`traces_events`) as JSON blobs. The private `_any_event_adapter: TypeAdapter[AnyEvent]` already exists in `agent/trace.py` and is the canonical deserialisation path — it is the same `TypeAdapter` tested by `test_any_event_discriminator`. `_aggregate_diagnostics` in `scripts/eval.py` currently reinvents this by importing `_any_event_adapter` directly and issuing a raw `SELECT` against `writer._require_conn()`, creating a private-symbol dependency and an implementation-level coupling to the storage schema.

The change is a targeted encapsulation: add a thin public method on `TraceWriter` that wraps the existing SQL + adapter call, then swap the one call site in `_aggregate_diagnostics` to use it.

## Goals / Non-Goals

**Goals:**
- Add `TraceWriter.iter_events(run_id: str) -> Iterator[AnyEvent]` as a public method.
- Remove `from agent.trace import _any_event_adapter` from `scripts/eval.py`.
- All existing `_aggregate_diagnostics` tests remain green after the swap.
- New unit tests cover the two empty/non-empty iterator contracts on `iter_events`.

**Non-Goals:**
- Adding a `kind` filter parameter — `_aggregate_diagnostics` iterates all events; filtering is done in the caller with `isinstance`.
- Returning a materialised list — a generator is sufficient and avoids loading arbitrarily large traces into memory; callers that need random access (like the existing index-based lookup in `_aggregate_diagnostics`) can call `list()` themselves. `_aggregate_diagnostics` already builds a `list[AnyEvent]` from the rows, so passing it a generator is a zero-friction drop-in.
- Changing the `traces_events` schema or the SQLite backend.
- Exposing `iter_events` on a closed `TraceWriter` — the method SHALL call `_require_conn()` and raise `sqlite3.ProgrammingError` if the writer is closed, consistent with all other methods.
- Concurrent-write safety beyond what SQLite's default serialised-write model already provides — `iter_events` reads within a single connection and there are no concurrent writers in the eval flow.

## Decisions

### Decision: Generator, not materialised list

`iter_events` yields events lazily. Rationale: traces can be large (many LLM-call events); a generator matches the streaming nature of the data and avoids a memory cliff. The only call site (`_aggregate_diagnostics`) immediately wraps it with `list()` already (it builds `events: list[AnyEvent]`), so the swap is trivial.

Alternative considered: return `list[AnyEvent]` directly. Rejected because it forces a full load for callers that only need to scan once, and a generator is strictly more general.

### Decision: Reuse `_any_event_adapter` inside `iter_events`, keep it private

`iter_events` calls `_any_event_adapter.validate_json(row[0])` for each row — the exact call that `_aggregate_diagnostics` currently makes. `_any_event_adapter` is not added to the module's public surface (`__all__` is not defined, and the leading underscore convention is preserved). The goal is to stop `eval.py` from importing it, not to expose it more widely.

### Decision: `iter_events` does NOT require an open run

The method queries `traces_events` directly and does not check `traces_runs.status`. A closed run can still have its events iterated (useful for post-run analysis). An unknown `run_id` yields an empty iterator rather than raising — this is consistent with how a `SELECT WHERE run_id = ?` with no matching rows naturally returns nothing, and the empty-run test documents this contract.

Alternative considered: raise `LookupError` for an unknown `run_id`. Rejected because it would require an extra `traces_runs` query and would break the empty-run test's "no error" assertion. The ticket text specifies "returns an empty iterator" not an error.

## Risks / Trade-offs

- **Risk**: `iter_events` iterates events for a run that never existed — silently returns nothing. → Accepted: the contract is documented in the spec and the test; callers that care about run existence should use `open_run`/`next_seq` which already raise.
- **Risk**: `_aggregate_diagnostics` depends on `list()` semantics (index access via `events[j]`) — the generator swap works because `_aggregate_diagnostics` will call `list(writer.iter_events(run_id))` or equivalent. → The refactor must materialise the iterator into a list before the `for i, ev in enumerate(events)` loop; the design doc calls this out explicitly.

## Migration Plan

No schema or API migrations. The change is additive (new public method) plus one internal call-site refactor. Deployment is a standard `uv sync` + restart of the Zeabur service. Rollback: revert the two file changes.
