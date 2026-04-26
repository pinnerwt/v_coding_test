## Why

The agent loop currently navigates without a forward plan, relying entirely on reactive step-by-step decisions. Adding an explicit plan lets the LLM reason about multi-step sequencing upfront, gives each decision step a shared context of what remains, and enables structured self-correction (replan on supervisor halt) rather than silent retry — directly addressing the "self-correction" non-negotiable from the brief.

## What Changes

- New module `task2/agent/plan.py` exporting `plan(task, observation, llm) -> Plan` and `replan(task, observation, prior_plan, reason, llm) -> Plan`, plus the `Plan` dataclass (`steps: list[str]`, `expected_end_state: str`).
- `task2/agent/loop.py` calls `plan()` once after the first `ObservationEvent`, emits `PlanEvent(reason="initial")` before the first `DecisionEvent`, and injects a "Plan progress" block (all plan steps, no per-step completion tracking) into every subsequent decision prompt user message.
- `task2/agent/supervisor.py` gains a `replan_used: bool` flag. When `policy="halt"` fires and `replan_used` is `False`, the supervisor signals a replan instead of a final halt; after one replan the next halt is terminal.
- `task2/tests/agent/test_plan.py` — new test file covering the five TDD cases from the ticket.

## Capabilities

### New Capabilities

- `plan-replan`: Planning module (`plan.py`) and its integration into the agent loop and supervisor, including the `Plan` dataclass, initial plan emission, plan-progress context injection, halt→replan→continue flow, and the second-halt terminal-fail guard.

### Modified Capabilities

- `agent-loop`: Loop now calls `plan()` after the first observation, threads plan steps into subsequent user messages, and routes supervisor halt through replan before failing.
- `supervisor-escalation`: Supervisor gains a single-replan guard (`replan_used`) so the halt→replan path fires at most once per run.

## Impact

- `task2/agent/plan.py` — new file.
- `task2/agent/loop.py` — planner call, `PlanEvent` emission, plan-progress injection, halt→replan routing.
- `task2/agent/supervisor.py` — `replan_used` flag, updated `handle()` return contract for the halt→replan branch.
- `task2/tests/agent/test_plan.py` — new test file (five cases).
- No changes to `task2/agent/trace.py` (`PlanEvent` schema already correct), `observe.py`, `llm.py`, or `browser.py`.
- No new Python dependencies required.
