## ADDED Requirements

### Requirement: loop calls plan() after first observation and emits PlanEvent before first DecisionEvent

After obtaining the first observation (step 1), the loop SHALL call `agent.plan.plan(task, observation, llm_client)` to produce an initial `Plan`. It SHALL then emit a `PlanEvent(reason="initial", steps=plan.steps, llm_call_id=<planner_llm_call_id>)` before issuing the first `DecisionEvent`. The `PlanEvent` SHALL appear before any `DecisionEvent` in the event sequence for any run.

#### Scenario: PlanEvent emitted before first DecisionEvent on fixture run

- **GIVEN** a loop run on a fixture page where the mock LLM returns a valid plan JSON on the first planner call
- **WHEN** the loop completes
- **THEN** the sequence of emitted events SHALL contain a `PlanEvent(reason="initial")` occurring before the first `DecisionEvent`

#### Scenario: PlanEvent contains the steps from the planner response

- **GIVEN** a mock LLM planner that returns `{"steps": ["step A", "step B"], "expected_end_state": "done"}`
- **WHEN** the loop runs and emits a `PlanEvent`
- **THEN** the `PlanEvent.steps` SHALL equal `["step A", "step B"]`

### Requirement: Plan steps injected into decision prompts from step 1 onwards

From step 1 (after the initial plan is established), each decision-step user message SHALL include a "Plan progress" block immediately before the observation JSON. The block SHALL contain all plan steps as a numbered list. No per-step completion tracking is performed; all steps appear in every message regardless of progress.

The format SHALL be:
```
Plan progress:
1. <step 1>
2. <step 2>
...

Current state: <observation json>
```

#### Scenario: Step 1 decision prompt includes Plan progress block

- **GIVEN** a loop with a mock LLM that captures the messages passed to it on each call
- **AND** the planner returned `{"steps": ["find result", "return it"], "expected_end_state": "done"}`
- **WHEN** the loop makes the decision LLM call for step 1 (the first decision after planning)
- **THEN** the user message content SHALL contain the substring `"Plan progress:"`
- **AND** SHALL contain `"1. find result"`
- **AND** SHALL contain `"2. return it"`

#### Scenario: Plan progress block appears on all subsequent decision steps

- **GIVEN** a multi-step run where the LLM calls `goto` on step 1 and `done` on step 2
- **WHEN** the messages for the step 2 decision call are inspected
- **THEN** the user message for step 2 SHALL also contain `"Plan progress:"`

### Requirement: Supervisor halt triggers one replan before terminal failure

When `_locate_with_supervisor` causes the supervisor to return `policy="halt"` (the locator pipeline is exhausted), the loop SHALL check whether a replan has already been used in this run. If no replan has been used yet, the loop SHALL:

1. Call `agent.plan.replan(task, observation, prior_plan, reason, llm_client)`.
2. Emit `PlanEvent(reason="replan", steps=new_plan.steps, llm_call_id=<replan_llm_call_id>)`.
3. Replace the active plan with the new plan and continue the loop.

If a replan has already been used (i.e., this is the second halt), the loop SHALL treat it as a terminal failure and return `RunResult(status="failed", ...)`.

#### Scenario: First supervisor halt triggers replan and loop continues

- **GIVEN** a mock browser fixture where the locator always misses on step 1 (triggering supervisor halt)
- **AND** the supervisor has not yet used its replan budget
- **AND** the mock LLM returns a valid replan JSON
- **WHEN** the loop processes the halt
- **THEN** a `PlanEvent(reason="replan")` SHALL be emitted
- **AND** the loop SHALL continue to the next step

#### Scenario: Second supervisor halt after replan is terminal failure

- **GIVEN** a run where the first halt triggered a replan
- **WHEN** the supervisor halts again on a subsequent step
- **THEN** the loop SHALL return `RunResult(status="failed", ...)`
- **AND** SHALL NOT emit a second `PlanEvent(reason="replan")`

## MODIFIED Requirements

### Requirement: loop function

The system SHALL provide `agent.loop.loop(task, browser, llm_client, *, max_steps=20)` — a synchronous function that drives the observe → decide → act cycle and returns a `RunResult` with all metric fields populated.

- `steps` SHALL equal the number of completed observe→decide→act iterations.
- `prompt_tokens`, `completion_tokens`, `usd` SHALL be cumulated from each `llm_client.chat()` call, **including the planner LLM call(s)**.
- `latency_ms_per_step` SHALL have one entry per step (wall time for the full observe→decide→dispatch cycle).
- `latency_ms_total` SHALL equal `sum(latency_ms_per_step)`.
- `step_breakdown[i]` SHALL have `step=i+1`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls` (list of tool name strings called in that step).
- The loop SHALL call `agent.plan.plan()` once after the first observation and inject "Plan progress" into every subsequent decision user message.
- On supervisor `policy="halt"`, the loop SHALL trigger at most one `agent.plan.replan()` before returning `RunResult(status="failed")`.

#### Scenario: loop returns RunResult

- **WHEN** `loop(task, browser, llm_client)` is called with a valid `Browser` and `LLMClient`
- **THEN** it SHALL return a `RunResult` instance

#### Scenario: loop is bounded by max_steps

- **WHEN** the LLM never calls `done` or `fail` within `max_steps` iterations
- **THEN** the loop SHALL return `RunResult(status="timeout", result=None, evidence=None)` with `steps == max_steps`

#### Scenario: Metrics are non-zero after a successful 2-step run

- **GIVEN** a mocked `LLMClient` that returns a `goto` tool call on step 1 (usage: 100 prompt, 10 completion, usd 0.00022) and `done` on step 2 (usage: 150 prompt, 20 completion, usd 0.00034)
- **WHEN** the loop completes
- **THEN** `result.steps` SHALL equal `2`
- **AND** `result.prompt_tokens` SHALL equal `250` (plus planner tokens; the fixture mock may return 0 for planner)
- **AND** `result.latency_ms_total` SHALL be positive
