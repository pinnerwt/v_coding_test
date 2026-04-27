## 1. Red: Write failing tests (TDD — tests first, no production code yet)

- [x] 1.1 Create `task2/tests/agent/test_plan.py` — test `Plan` dataclass is frozen with correct fields
- [x] 1.2 Add test: `plan()` returns `Plan` from a mock LLM response with well-formed JSON (`{"steps": [...], "expected_end_state": "..."}`)
- [x] 1.3 Add test: `plan()` returns single-step fallback `Plan` on malformed JSON (no raise)
- [x] 1.4 Add test: `plan()` returns single-step fallback `Plan` when `steps` key is missing from LLM response
- [x] 1.5 Add test: `replan()` returns revised `Plan` from well-formed LLM response
- [x] 1.6 Add test: `replan()` returns fallback `Plan` on malformed JSON (no raise)
- [x] 1.7 In `task2/tests/agent/test_loop.py` — add test: loop on fixture emits `PlanEvent(reason="initial")` before any `DecisionEvent` (event ordering test; requires an event-capturing helper or mock trace writer)
- [x] 1.8 Add loop test: from step 1 onwards the decision LLM call receives a user message containing `"Plan progress:"` and the plan steps
- [x] 1.9 Add loop test: supervisor halt on step 1 → `PlanEvent(reason="replan")` emitted, loop continues to next step
- [x] 1.10 Add loop test: supervisor halt on step 1 → replan → supervisor halt again on step 2 → `RunResult(status="failed")` (no second replan)
- [x] 1.11 In `task2/tests/agent/test_supervisor.py` — add test: `supervisor.last_policy` is `None` on construction
- [x] 1.12 Add supervisor test: `supervisor.last_policy` is `"next_tier"` after `handle()` returns that policy
- [x] 1.13 Add supervisor test: `supervisor.last_policy` is `"halt"` after `handle()` returns halt
- [x] 1.14 Add supervisor test: `supervisor.replan_used` is `False` on construction
- [x] 1.15 Run `uv run pytest task2/tests/agent/test_plan.py task2/tests/agent/test_supervisor.py` from `task2/` — all new tests must be RED (ImportError or AttributeError expected)

## 2. Green: Implement `task2/agent/plan.py`

- [x] 2.1 Create `task2/agent/plan.py` with `Plan` frozen dataclass (`steps: list[str]`, `expected_end_state: str`) — no docstrings, no comments except non-obvious constraint notes
- [x] 2.2 Implement `plan(task, observation, llm) -> Plan`: build system + user message, call `llm.chat()`, parse JSON response; on any parse/key error return `Plan(steps=[task], expected_end_state="task complete")`
- [x] 2.3 Implement `replan(task, observation, prior_plan, reason, llm) -> Plan`: include prior plan steps and reason in prompt, call `llm.chat()`, parse JSON response; same fallback as `plan()`
- [x] 2.4 Run `uv run pytest task2/tests/agent/test_plan.py` from `task2/` — all plan unit tests must be GREEN
- [x] 2.5 Run `uv run ruff check . && uv run ruff format --check .` from `task2/` — must exit 0

## 3. Green: Update `task2/agent/supervisor.py`

- [x] 3.1 Add `last_policy: str | None = None` instance attribute to `Supervisor.__init__`
- [x] 3.2 Add `replan_used: bool = False` instance attribute to `Supervisor.__init__`
- [x] 3.3 Update `Supervisor.handle()` to set `self.last_policy = decision.policy` before returning each `EscalationDecision`
- [x] 3.4 Run `uv run pytest task2/tests/agent/test_supervisor.py` from `task2/` — all supervisor tests (old + new) must be GREEN
- [x] 3.5 Run `uv run ruff check . && uv run ruff format --check .` from `task2/` — must exit 0

## 4. Green: Integrate planning into `task2/agent/loop.py`

- [x] 4.1 After the first `observe.build_observation()` call (step 1), call `plan.plan(task, observation, llm_client)` and store the result as `active_plan`
- [x] 4.2 Emit `PlanEvent(reason="initial", steps=active_plan.steps, llm_call_id=<planner_call_id>)` via the event-capture mechanism (pass events list or trace writer as needed by the test harness)
- [x] 4.3 Modify the user message construction: from step 1 onwards, prepend the "Plan progress" block (numbered list of `active_plan.steps`) before `Current state: <json>` in the user message
- [x] 4.4 In `_locate_with_supervisor` or the dispatch path: after supervisor returns `policy="halt"`, check `supervisor.replan_used`. If `False`, call `plan.replan(...)`, emit `PlanEvent(reason="replan", ...)`, set `supervisor.replan_used = True`, update `active_plan`, and continue the loop iteration. If `True`, return `RunResult(status="failed", ...)`.
- [x] 4.5 Run `uv run pytest task2/tests/agent/test_loop.py` from `task2/` — all loop tests (old + new) must be GREEN
- [x] 4.6 Run `uv run pytest task2/tests/` from `task2/` — full test suite must be GREEN (no regressions in supervisor, trace, or other tests)
- [x] 4.7 Run `uv run ruff check . && uv run ruff format --check .` from `task2/` — must exit 0

## 5. Verify no regressions and clean up

- [x] 5.1 Run the full test suite: `uv run pytest task2/tests/` from `task2/` with verbose output — confirm zero failures
- [x] 5.2 Confirm `task2/agent/plan.py` contains zero docstrings (`"""` / `'''`) using `grep -n '"""' task2/agent/plan.py` — output must be empty
- [x] 5.3 Run `uv run ruff check . && uv run ruff format --check .` from `task2/` — final clean check
- [x] 5.4 Confirm `task2/agent/loop.py` and `task2/agent/supervisor.py` also pass `ruff check` with zero new violations
