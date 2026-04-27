## ADDED Requirements

### Requirement: Plan dataclass

The system SHALL provide `agent.plan.Plan` — a frozen dataclass with the fields:

- `steps: list[str]` — ordered natural-language steps produced by the planner.
- `expected_end_state: str` — free-form NL description of the expected final state when all steps are complete.

`Plan` SHALL be frozen so callers cannot mutate it after construction.

#### Scenario: Plan is constructible and frozen

- **WHEN** code constructs `Plan(steps=["Step 1", "Step 2"], expected_end_state="done")`
- **THEN** the construction SHALL succeed
- **AND** `steps` SHALL equal `["Step 1", "Step 2"]`
- **AND** attempting to assign to any field SHALL raise `dataclasses.FrozenInstanceError`

### Requirement: plan() function

The system SHALL provide `agent.plan.plan(task: str, observation: dict, llm: LLMClient) -> Plan`.

`plan()` SHALL call `llm.chat()` with a focused system + user message requesting a JSON object `{"steps": [...], "expected_end_state": "..."}`. The `llm_call_id` from the resulting `LLMCallEvent` is the caller's responsibility to emit.

On `json.JSONDecodeError` or missing/invalid keys in the LLM response, `plan()` SHALL return a single-step fallback `Plan(steps=[task], expected_end_state="task complete")` rather than raising.

`plan()` SHALL NOT write comments or docstrings in the production source file. It SHALL be callable without a running browser (it only receives the observation dict).

#### Scenario: plan() returns Plan from well-formed LLM response

- **GIVEN** an `LLMClient` mock that returns a chat response with content `{"steps": ["go to site", "read result"], "expected_end_state": "result found"}`
- **WHEN** `plan(task="find X", observation={}, llm=mock_llm)` is called
- **THEN** it SHALL return a `Plan` with `steps == ["go to site", "read result"]` and `expected_end_state == "result found"`

#### Scenario: plan() returns fallback Plan on malformed JSON

- **GIVEN** an `LLMClient` mock that returns a chat response with content `"not valid json {"`
- **WHEN** `plan(task="find X", observation={}, llm=mock_llm)` is called
- **THEN** it SHALL return a `Plan` with `steps == ["find X"]` and SHALL NOT raise

#### Scenario: plan() returns fallback Plan when steps key is missing

- **GIVEN** an `LLMClient` mock that returns a chat response with content `{"expected_end_state": "done"}`
- **WHEN** `plan(task="find X", observation={}, llm=mock_llm)` is called
- **THEN** it SHALL return a `Plan` with `steps == ["find X"]` and SHALL NOT raise

### Requirement: replan() function

The system SHALL provide `agent.plan.replan(task: str, observation: dict, prior_plan: Plan, reason: str, llm: LLMClient) -> Plan`.

`replan()` SHALL call `llm.chat()` with a prompt that includes the prior plan steps and the reason for replanning, and SHALL request a revised JSON plan. On malformed response or missing keys, it SHALL return a single-step fallback `Plan(steps=[task], expected_end_state="task complete")`.

#### Scenario: replan() returns a revised Plan from well-formed LLM response

- **GIVEN** an `LLMClient` mock returning `{"steps": ["try alternative approach"], "expected_end_state": "task done via alt"}`
- **AND** a prior `Plan(steps=["original step"], expected_end_state="original end")`
- **WHEN** `replan(task="find X", observation={}, prior_plan=prior, reason="locate failed", llm=mock_llm)` is called
- **THEN** it SHALL return a `Plan` with `steps == ["try alternative approach"]` and SHALL NOT raise

#### Scenario: replan() returns fallback Plan on malformed JSON

- **GIVEN** an `LLMClient` mock that returns a chat response with non-JSON content
- **WHEN** `replan(task="find X", observation={}, prior_plan=prior, reason="halt", llm=mock_llm)` is called
- **THEN** it SHALL return a `Plan` with `steps == ["find X"]` and SHALL NOT raise

### Requirement: plan.py has no comments or docstrings

The production file `task2/agent/plan.py` SHALL contain zero module-level, function-level, or inline comments (except single-line `# why` comments for non-obvious constraints). It SHALL contain zero docstrings.

#### Scenario: plan.py source passes the no-docstring constraint

- **WHEN** `task2/agent/plan.py` is inspected
- **THEN** it SHALL contain no `"""` or `'''` docstring literals at the module, class, or function level
- **AND** ruff format and ruff check SHALL both exit 0
