## MODIFIED Requirements

### Requirement: loop observation uses AX-tree digest

The loop SHALL call `observe.build_observation(browser, last_actions)` at the start of each step instead of constructing the observation inline. The returned dict (with keys `url`, `title`, `ax_tree_digest`, `ax_fingerprint`, `last_actions`) SHALL be serialized to JSON and appended to the LLM message thread as a user message prefixed by `STATE_MESSAGE_PREFIX`. The loop SHALL accumulate `last_actions` across all tool dispatches within a single step: at the start of each iteration the loop SHALL call `build_observation(browser, last_actions)` with the list accumulated during the **previous** iteration's dispatches; immediately after that call `last_actions` SHALL be reset to `[]` before any new dispatches in the current iteration; after each non-terminal tool dispatch it SHALL append `{tool: <name>, intent: <string summary of args>, outcome: <"ok"|"error">, error?: <message>}`.

#### Scenario: First step has last_actions empty list in observation

- **WHEN** the loop calls `observe.build_observation(browser, last_actions)` for the first time (step 1)
- **THEN** `last_actions` SHALL be `[]`
- **AND** the serialized user message SHALL contain `"last_actions": []`

#### Scenario: Second step threads previous last_actions

- **GIVEN** a loop where step 1 dispatched a `goto` tool call that succeeded
- **WHEN** the loop calls `observe.build_observation(browser, last_actions)` at the start of step 2
- **THEN** `last_actions` SHALL be a list of length 1 containing a dict with at least keys `tool` (value `"goto"`) and `outcome` (value `"ok"`)
- **AND** the serialized user message SHALL contain the `last_actions` list

#### Scenario: Multi-tool step produces last_actions with all actions in order

- **GIVEN** a single LLM response that contains two tool calls: first `goto(url=<fixture_url>)` then `read()`
- **WHEN** both tool calls are dispatched in that step and the loop reaches the next observation
- **THEN** `last_actions` SHALL be a list of length 2
- **AND** `last_actions[0]["tool"]` SHALL equal `"goto"`
- **AND** `last_actions[1]["tool"]` SHALL equal `"read"`
- **AND** both entries SHALL have an `"outcome"` key

#### Scenario: Error outcome is preserved per action in last_actions

- **GIVEN** a single LLM response with two tool calls where the first succeeds and the second returns an error
- **WHEN** both are dispatched in that step and the loop reaches the next observation
- **THEN** `last_actions[0]["outcome"]` SHALL equal `"ok"`
- **AND** `last_actions[1]["outcome"]` SHALL equal `"error"`
- **AND** `last_actions[1]` SHALL contain an `"error"` key with the error message string

#### Scenario: Single-tool-call step produces length-1 last_actions (no regression)

- **GIVEN** a single LLM response that contains exactly one tool call (`goto`)
- **WHEN** the tool call is dispatched and the loop reaches the next observation
- **THEN** `last_actions` SHALL be a list of length 1
- **AND** `last_actions[0]["tool"]` SHALL equal `"goto"`

#### Scenario: Observation message contains last_actions key (not last_action)

- **GIVEN** a loop step where `observe.build_observation` returns a dict with `last_actions`
- **WHEN** the loop appends the observation to the LLM message thread
- **THEN** the serialized JSON SHALL contain the key `"last_actions"`
- **AND** SHALL NOT contain the legacy key `"last_action"` (singular)
