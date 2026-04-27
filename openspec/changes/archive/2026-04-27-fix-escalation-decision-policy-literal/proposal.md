## Why

`EscalationDecision.policy` in `agent/supervisor.py` is typed as plain `str`, while `SupervisorEvent.policy` in `agent/trace.py` is typed as `Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]`. This mismatch means `_emit_supervisor_event` in `loop.py` must silence mypy with a `# type: ignore[arg-type]` comment on the `policy=decision.policy` assignment. Tightening `EscalationDecision.policy` to the same `Literal` enforces the contract end-to-end and removes the suppression.

## What Changes

- Extract a shared type alias `EscalationPolicy = Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]` in `agent/trace.py` (where the Literal is already authoritative via `SupervisorEvent.policy`).
- Re-type `EscalationDecision.policy: str` → `EscalationDecision.policy: EscalationPolicy` in `agent/supervisor.py`, importing the alias from `agent.trace`.
- Re-type `Supervisor.last_policy: str | None` → `Supervisor.last_policy: EscalationPolicy | None` in `agent/supervisor.py`.
- Update `SupervisorEvent.policy` in `agent/trace.py` to use the same alias (no runtime change, just DRY).
- Remove `# type: ignore[arg-type]` from `_emit_supervisor_event` in `agent/loop.py` (line 312).
- Update `tests/agent/test_supervisor.py` annotations / type-checked constructions so they satisfy the narrower type (no logic change needed — tests already use only valid policy strings).

## Capabilities

### New Capabilities

<!-- None -->

### Modified Capabilities

- `supervisor-escalation`: `EscalationDecision.policy` and `Supervisor.last_policy` are narrowed from `str` to the shared `EscalationPolicy` `Literal`; scenarios updated accordingly.
- `supervisor-event-emitter`: `_emit_supervisor_event` no longer requires `# type: ignore[arg-type]`; scenario updated to reflect that the suppression is absent.

## Impact

- **`agent/trace.py`**: adds `EscalationPolicy` alias, uses it in `SupervisorEvent.policy`.
- **`agent/supervisor.py`**: imports `EscalationPolicy` from `agent.trace`; narrows two field types.
- **`agent/loop.py`**: removes the single `# type: ignore[arg-type]` comment.
- **`tests/agent/test_supervisor.py`**: no logic changes needed; existing tests pass as-is.
- No API surface change; frozen dataclass field values (always literal strings) are unchanged at runtime.
