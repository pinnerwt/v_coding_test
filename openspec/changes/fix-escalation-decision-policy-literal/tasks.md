## 1. Write failing test (TDD red)

- [x] 1.1 Add a test to `tests/agent/test_supervisor.py` that imports `EscalationPolicy` from `agent.trace` and asserts `EscalationDecision.policy` is annotated with it — run pytest to confirm it fails (ImportError or AttributeError)
- [x] 1.2 Run `uv run pytest task2/tests/agent/test_supervisor.py -x` and verify the new test fails for the expected reason

## 2. Define EscalationPolicy alias in agent/trace.py

- [x] 2.1 Add `EscalationPolicy = Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]` as a module-level alias in `agent/trace.py` (before the `SupervisorEvent` class)
- [x] 2.2 Replace the inline `Literal[...]` in `SupervisorEvent.policy` with `EscalationPolicy`
- [x] 2.3 Verify `from agent.trace import EscalationPolicy` works in a Python shell (`uv run python -c "from agent.trace import EscalationPolicy; print(EscalationPolicy)"`)

## 3. Narrow EscalationDecision and Supervisor in agent/supervisor.py

- [x] 3.1 Add `from agent.trace import EscalationPolicy` import to `agent/supervisor.py`
- [x] 3.2 Change `EscalationDecision.policy: str` to `EscalationDecision.policy: EscalationPolicy`
- [x] 3.3 Change `Supervisor.last_policy: str | None` to `Supervisor.last_policy: EscalationPolicy | None`

## 4. Remove type: ignore in agent/loop.py

- [x] 4.1 Remove the `# type: ignore[arg-type]` comment from the `policy=decision.policy` line in `_emit_supervisor_event` (loop.py line 312)

## 5. Verify green bar and clean linter

- [x] 5.1 Run `uv run pytest task2/tests/agent/test_supervisor.py -v` — all tests must pass
- [x] 5.2 Run `uv run pytest task2/tests/agent/test_loop.py -v` — all tests must pass
- [x] 5.3 Run `uv run ruff check task2/` — must be clean (zero errors)
- [x] 5.4 Run `uv run ruff format task2/ --check` — must be clean
- [x] 5.5 Confirm `grep -n "type: ignore\[arg-type\]" task2/agent/loop.py` returns no output
