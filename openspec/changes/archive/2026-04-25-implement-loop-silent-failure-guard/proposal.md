## Why

The agent loop's `done` tool currently accepts any call as a success, even when the LLM provides no evidence that it actually completed the task — it simply returns `status="succeeded"` unconditionally. This creates a silent-failure mode: an agent that hallucinates completion (calls `done` with an empty `evidence` dict or with required fields missing) is indistinguishable from one that genuinely verified its result. Ticket #11 closes this gap: `done` without valid evidence must produce `status="unverified"`, not `status="succeeded"`.

## What Changes

- `agent/loop.py`: The `done` handler is extended with an evidence guard that checks whether the evidence dict contains the required minimum fields (`url` and `text_snippet`). If either is absent or is not a non-empty string, the run is marked `status="unverified"` rather than `"succeeded"`. A `verifier` sub-dict (shape: `{ok: bool, reasons: list[str]}`) is attached to the `RunResult` reflecting the check outcome. Valid evidence keeps the existing `"succeeded"` path.
- `RunResult` dataclass: gains an optional `verifier: dict | None` field to carry the `{ok, reasons}` verdict. The field is `None` for non-`done` exits (timeout, fail). The dataclass remains frozen.
- `task2/tests/agent/test_loop.py`: two new test functions:
  - `test_loop_done_without_evidence` — LLM calls `done` with `evidence={}` → `status="unverified"`.
  - `test_loop_done_with_valid_evidence` — regression guard confirming the existing happy path still returns `"succeeded"` with a well-formed `verifier={ok: True, reasons: []}`.
- No new fixtures are required; existing `loop_happy_path.html` is sufficient for both tests.
- Schema-validation and screenshot-diff features (the other two silent-failure prevention items from `plan.md`) are **deferred** to separate future tickets.

## Capabilities

### New Capabilities

(none — this adds a guard inside an existing capability, not a new spec-level capability)

### Modified Capabilities

- `agent-loop`: The `done` tool handler gains a new evidence-validation requirement. `Run.status` gains `"unverified"` as a valid value for the terminal `done` path. `RunResult` gains a `verifier` field.

## Impact

- **Code**: `task2/agent/loop.py` (done handler + RunResult dataclass); `task2/tests/agent/test_loop.py` (two new tests).
- **Dependencies**: none new.
- **Existing modules**: `agent/locate.py`, `agent/supervisor.py`, `agent/browser.py`, `agent/llm.py`, `agent/locator_cache.py` unchanged.
- **Spec**: `openspec/specs/agent-loop/spec.md` gains a delta section covering the evidence-guard requirement and the `"unverified"` status value.
