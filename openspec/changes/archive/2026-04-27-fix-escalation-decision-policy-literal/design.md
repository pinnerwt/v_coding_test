## Context

`agent/trace.py` defines `SupervisorEvent.policy` as:

```python
policy: Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]
```

`agent/supervisor.py` defines `EscalationDecision.policy` and `Supervisor.last_policy` as plain `str`. When `_emit_supervisor_event` in `loop.py` passes `policy=decision.policy` to the `SupervisorEvent` constructor, mypy rejects it (str is not assignable to the Literal) and the code silences it with `# type: ignore[arg-type]`. The fix is to give both sides the same narrow type, sourced from a single definition.

## Goals / Non-Goals

**Goals:**
- Define one canonical `EscalationPolicy` `Literal` alias reachable from both `agent.trace` and `agent.supervisor`.
- Narrow `EscalationDecision.policy` and `Supervisor.last_policy` to `EscalationPolicy`.
- Remove the `# type: ignore[arg-type]` comment in `_emit_supervisor_event`.
- All existing tests continue to pass without modification to their logic.

**Non-Goals:**
- Adding new policy values (e.g. `"rerank"`, `"sweep_overlay"`, `"replan"` are already in the `Literal` but not yet produced by `Supervisor.handle`; this change does not make them reachable, just type-correct).
- Changing runtime behaviour of any module.
- Modifying tests other than annotation or import changes if required.

## Decisions

### Where to place the shared alias

**Decision**: define `EscalationPolicy` in `agent/trace.py` and import it into `agent/supervisor.py`.

**Rationale**: `agent/trace.py` is already the authoritative home of `SupervisorEvent.policy`'s `Literal`. Defining the alias there and re-using it in `SupervisorEvent` keeps the single-source-of-truth in trace (the schema module). `agent/supervisor.py` already imports from `agent.locate`, so a new import from `agent.trace` introduces no circular dependency (`trace` imports nothing from `supervisor` or `loop`).

**Alternative considered**: define the alias in `agent/supervisor.py` and import it into `agent/trace.py`. Rejected because `trace.py` is a schema/data module; importing from a behaviour module (`supervisor`) would invert the natural dependency direction.

**Alternative considered**: define the alias in a new shared `agent/types.py`. Rejected as over-engineering — the alias is two lines and already naturally belongs in `trace.py`.

### Scope of changes to `SupervisorEvent`

`SupervisorEvent.policy` is changed from the inline `Literal[...]` to `EscalationPolicy` — this is an alias substitution with zero runtime effect and no behaviour change.

### Test changes

Existing tests in `tests/agent/test_supervisor.py` construct `EscalationDecision` with `policy="next_tier"` and `policy="halt"` — both are valid members of the new `Literal`, so no test logic changes are needed. The tests are expected to pass without modification.

## Risks / Trade-offs

- **Import cycle risk** → Mitigated: `agent/trace.py` currently imports only from the standard library and pydantic; adding `EscalationPolicy` to its public API adds no new imports to `trace.py` itself. `agent/supervisor.py` already imports from `agent.locate`; adding `agent.trace` is safe.
- **Future policy values** → If a new policy label is added (e.g., `"replan"`), it must be added to `EscalationPolicy` in `trace.py` before use. This is intentional: the type check will catch omissions at static analysis time rather than at runtime.

## Migration Plan

1. Add `EscalationPolicy` alias to `agent/trace.py`; update `SupervisorEvent.policy` to use it.
2. Import `EscalationPolicy` in `agent/supervisor.py`; narrow `EscalationDecision.policy` and `Supervisor.last_policy`.
3. Remove `# type: ignore[arg-type]` from `loop.py` line 312.
4. Run `uv run pytest task2/tests/agent/test_supervisor.py` — must be green.
5. Run `uv run ruff check task2/` — must be clean.
6. Optionally run mypy to confirm the suppression is gone.

No rollback complexity: all changes are type-annotation only; reverting is a one-commit revert.

## Open Questions

None. The canonical home for the alias (`agent/trace.py`) and the import direction are unambiguous.
