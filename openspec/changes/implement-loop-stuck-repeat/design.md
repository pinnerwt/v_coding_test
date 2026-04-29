## Context

`agent/loop.py` is the core observe → decide → act driver. After PR #101 fixed the Qwen HTTP 400 via `_compact_messages`, the webvoyager-1 case stopped crashing but now silently loops to `max_steps=20` because the LLM keeps emitting byte-identical `goto("about:blank")` calls. The loop has no detection for this cycle. The benchmark regression (cost +160%, tokens +164%, latency +170%) is entirely attributable to this one case burning its full step budget.

The relevant symbols in `loop.py`:
- `loop()` — main entry point, `for _ in range(max_steps)` drives each step.
- `response.tool_calls` — the list of `ToolCall` objects emitted by the LLM each step.
- `RunResult` — frozen dataclass returned on all terminal paths; currently no `reason` field.
- Existing early-exit paths: supervisor `policy="halt"` after second replan (returns `RunResult(status="failed")`), `fail()` tool call (returns `RunResult(status="failed")`), `done()` tool call.

`RunResult` lives in `loop.py` (not `trace.py`). `trace.py`'s `RunResult`-equivalent is the `Run` model and `Run.status` literal which already accepts `"failed"` — no changes needed there.

## Goals / Non-Goals

**Goals:**
- Detect when the LLM emits K=3 byte-identical `(tool_name, args)` tuples in a row and exit with `RunResult(status="failed", reason="stuck_repeat")` before exhausting `max_steps`.
- Bound worst-case cost for stuck cases to ~K steps instead of `max_steps`.
- Add `reason: RunResultReason | None = None` to `RunResult` (with `RunResultReason = Literal["stuck_repeat"]`) so the caller can distinguish a stuck exit from a locator-halt exit via a closed Literal set rather than free-text.
- Keep all existing callers unaffected (the new field defaults to `None`).

**Non-Goals:**
- AX-tree digest stuck detection (optional variant from ticket #70 — filed as follow-up).
- Changing `max_steps` defaults.
- Any changes to `task2/agent/trace.py`.

## Decisions

**D1: Buffer placement in `loop()`**

The K-buffer `_stuck_buf: list[str]` is initialized to `[]` at the start of `loop()` alongside `last_actions`. Each time the LLM emits tool calls, each `(tool_call.name, json.dumps(args, sort_keys=True))` tuple is serialized to a single canonical string and appended to `_stuck_buf` **after** `_dispatch` returns successfully. The buffer is then trimmed to the last K entries. The stuck check fires immediately after appending: if `len(_stuck_buf) == K` and `len(set(_stuck_buf)) == 1`, exit early. Placement is after dispatch so D7's supervisor-reset can detect whether the supervisor took ownership of the call (if `supervisor.total_attempts()` increased during the dispatch, the buffer is cleared before appending).

Alternative considered: appending the canonical string pre-dispatch (immediately after the JSON parse succeeds). Rejected because this would pre-empt the supervisor's locator-escalation halt path on identical `read(intent=X)` calls — see D7.

**D2: Canonicalization via `json.dumps(args, sort_keys=True)`**

Dict-key ordering in `tool_call.arguments` can vary across LLM responses even for semantically identical calls. Using `json.dumps(args, sort_keys=True)` as the canonical form collapses key-order variance. The full key for the buffer entry is `f"{tool_call.name}:{canonical_args}`.

Alternative considered: comparing `tool_call.arguments` strings directly (raw JSON). Rejected because Qwen may emit `{"url": "x"}` and `{"url":"x"}` with different whitespace.

**D3: K=3 as a module-level constant**

`_STUCK_REPEAT_K: int = 3` at module scope. Rationale: K=2 would false-positive on any deliberate retry (e.g. `goto` → same URL after a transient error). K=3 still terminates well before `max_steps=20` and the test from the ticket ("K=3 identical calls → exit with `steps == 3`") directly validates this constant.

**D4: `RunResult.reason: RunResultReason | None = None`**

Adding a `reason` field to the frozen dataclass allows callers (eval runner, tests) to distinguish `"stuck_repeat"` exits from other `"failed"` exits without parsing free-text. Per the `Literal`-over-`str` rule for closed value sets, the field is typed `RunResultReason | None` where `RunResultReason = Literal["stuck_repeat"]` — a future failure-mode value is a deliberate one-line addition to the alias rather than a free-text contract loosening. The field defaults to `None` so all current `RunResult(...)` constructions with no `reason` kwarg continue to work.

**D5: Early exit emits `_record_step` before returning**

The stuck-exit path calls `_record_step(...)` so `step_breakdown` and `latency_ms_per_step` remain consistent (length == `steps`). This mirrors the existing supervisor-halt early exit pattern at line ~998 of the current `loop.py`.

**D6: No new trace event for stuck detection**

The existing trace schema has no `StuckEvent` kind. Emitting a `SupervisorEvent(classified_as="stuck_repeat")` would require extending the `classified_as` Literal in `trace.py`. Since the spec does not require it and the `reason` field on `RunResult` already surfaces the information to callers, no trace event is emitted for stuck detection in this ticket.

**D7: Supervisor coexistence — clear `_stuck_buf` when supervisor fires**

Stuck-detection must not pre-empt the supervisor's locator-escalation/halt/replan path. The supervisor is the legitimate handler for "agent keeps emitting the same `read(intent=X)` call" — it escalates L1→L2→L3, then halts on attempt > `max_attempts`, then triggers a one-shot replan. If the stuck-buffer were checked *before* dispatch (as originally implemented), 3 consecutive identical `read` calls would trigger `stuck_repeat` before the supervisor could fire its halt.

Fix applied (Option A): the buffer append and stuck check are moved to *after* `_dispatch`. Before dispatch, `supervisor.total_attempts()` is snapshotted; after dispatch, if that count increased (i.e., `supervisor.handle()` was called during the dispatch), `_stuck_buf` is cleared before appending. This resets the window whenever the supervisor takes ownership of an intent, ensuring stuck-detection only catches planner-level stuck cases that the supervisor does not already handle (e.g. repeated `goto(url=X)`, repeated `click`, repeated `type`).

Implementation note: `read()` calls are supervisor-mediated; the supervisor's own halt/replan path fires before stuck-detection can accumulate K identical entries. Use non-supervisor tools (e.g. `goto`, `click` with a stub that never triggers a locator-miss) to exercise this scenario.

## Risks / Trade-offs

- **False positive on deliberate retry loops** → K=3 makes this unlikely for real tasks; a legitimate agent would not call the exact same tool with byte-identical args three times in a row without any intermediate state change.
- **Buffer not reset across replan** → a stuck agent could burn one replan before K triggers. Acceptable: replan changes the plan context so the next K window starts fresh naturally.
- **`reason` field not surfaced in `Run` trace** → the eval runner reads `RunResult.reason` and can log it; adding it to the `Run.final` dict is a follow-up concern.

## Open Questions

None blocking this ticket.
