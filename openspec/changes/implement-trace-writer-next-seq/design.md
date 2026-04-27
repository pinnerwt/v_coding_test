## Context

`TraceWriter.append_event()` already enforces strictly-increasing `seq` via a `MAX(seq)` query before each INSERT. The contract is correct; the problem is that callers must choose a `seq` that satisfies `> MAX(seq)`. Today, `loop.py` does this by keeping `plan_seq` starting at 1 and incrementing it locally. This is safe only while `loop()` is the exclusive writer for a run. Ticket #20 will wire `ObservationEvent`, `DecisionEvent`, and `LLMCallEvent` through the same `TraceWriter` for the same run, meaning there will be multiple independent call-sites each needing a valid next seq. Without a shared authority, any two callers will collide.

The fix is to expose the `MAX(seq)` logic as a public accessor on `TraceWriter` so every emitter asks the writer for the next seq rather than tracking it privately.

## Goals / Non-Goals

**Goals:**
- Add `TraceWriter.next_seq(run_id: str) -> int` that is the single authoritative source of the next seq for a run.
- Remove `plan_seq` from `loop.py` and have `_emit_plan_event` call `next_seq()` at emit time.
- Preserve all existing behavior: in-memory `events` path unchanged, existing `TraceWriter` tests all green.
- TDD: failing tests before implementation.

**Non-Goals:**
- Wiring `ObservationEvent`, `DecisionEvent`, or `LLMCallEvent` through `TraceWriter` (ticket #20).
- Concurrency safety for truly parallel threads (SQLite WAL is sufficient for the single-process use case; no locking primitives needed now).
- Changing any event schema models or the `Run` model.
- Changing `api/server.py` beyond confirming it still works.

## Decisions

### Decision: `next_seq` queries `MAX(seq)` from SQLite rather than maintaining in-memory state

`TraceWriter` already issues a `MAX(seq)` query inside `append_event`. Reusing that same query for `next_seq` means no new state, no divergence between the query in `append_event` and the value returned by `next_seq`, and correct behavior even if multiple emitters interleave writes (each call sees the latest committed row).

Alternative considered: keep an in-memory `dict[run_id, int]` counter inside `TraceWriter`. Rejected because it would be stale if any other connection or call path appended an event between the counter update and the next `next_seq` call. The SQLite query is always authoritative.

### Decision: `next_seq` raises `LookupError` for an unknown or closed `run_id`

This mirrors `append_event`'s existing guard. A caller that passes a wrong `run_id` to `next_seq` and then passes the returned seq to `append_event` would get a `LookupError` from `append_event` anyway; raising early in `next_seq` provides a clearer error message.

Alternative: return `1` unconditionally without checking run state. Rejected because it silently enables writing events to non-existent runs, contradicting the append-only invariant.

### Decision: Remove `seq` parameter from `_emit_plan_event` entirely

The `seq` argument exists only to pass in the pre-incremented `plan_seq`. Once `_emit_plan_event` calls `next_seq()` itself, there is no reason for the caller to compute or pass a seq value. Removing the parameter shrinks the surface area and makes future call-sites simpler.

Alternative: keep `seq` as an optional parameter with a sentinel. Rejected — it introduces a dead parameter path with no caller.

### Decision: In-memory path keeps `seq=0` placeholder

The in-memory `events` path (used only in unit tests that don't pass a `TraceWriter`) writes `PlanEvent` objects with `run_id="loop"`, `seq=0`, and `ts=""`. These are test-only placeholder values; no test asserts a specific seq value on the in-memory path. Changing them would be scope creep.

### Decision: Integration test for two interleaved emitters uses `TraceWriter` directly, not `loop()`

The ticket asks for: emit a `PlanEvent` via `loop()`, then emit a manually-constructed `ObservationEvent` from the test using `next_seq()`, and verify both land with strictly-increasing seq. This does not require Playwright — the test can mock the browser and LLM client (same pattern as existing `test_loop.py` tests that use `FakeLLMClient` and `FakeBrowser`). The `ObservationEvent` is appended directly by the test after `loop()` returns, using the same open `TraceWriter`.

## Risks / Trade-offs

- [Risk] `next_seq` issues a `SELECT` on every call; if `_emit_plan_event` is called N times in a run (initial + replan), that is N queries on top of the N already in `append_event`. Mitigation: negligible for a browser agent where N ≤ 2 in practice and each loop step is already bounded by LLM and browser latency.
- [Risk] If `next_seq` and `append_event` are called from two threads on the same SQLite connection between the SELECT and the INSERT, there is a TOCTOU window. Mitigation: SQLite's `UNIQUE(run_id, seq)` constraint will reject the duplicate with `IntegrityError`; the caller would need to retry. The current codebase is single-threaded within a run; this is documented as a known limitation.
- [Trade-off] `next_seq` reads the latest committed state; a caller that calls `next_seq` twice without an intervening `append_event` will get the same value both times and the second `append_event` will raise `SeqError`. Mitigation: callers must call `next_seq` and `append_event` as an atomic pair (which `_emit_plan_event` does). This is documented in the spec.

## Open Questions

None. Both callers (`loop()` and future ticket-#20 emitters) are identified; the pattern is unambiguous.
