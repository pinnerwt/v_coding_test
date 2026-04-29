## ADDED Requirements

### Requirement: Conversation-history trimming

The loop SHALL expose a module-level function `trim_history(messages: list[dict], keep_steps: int) -> list[dict]` that returns a new message list with stale tool-result entries pruned.

- The function SHALL keep the first message (index 0, the system prompt) unconditionally.
- A "tool-result group" is defined as the set of one or more consecutive `role="tool"` messages that follow a single `role="assistant"` message that contains a `tool_calls` list.
- The function SHALL count tool-result groups from the most recent backwards. Groups within the most recent `keep_steps` groups SHALL be retained. Groups older than `keep_steps` SHALL be dropped, along with their paired `role="assistant"` message.
- If a `role="assistant"` message contains `tool_calls` that are split across the keep/drop boundary (partial drop), the entire assistant message and all its paired tool results SHALL be dropped together.
- `role="user"` state messages (including those prefixed with `STATE_MESSAGE_PREFIX`) SHALL never be dropped by `trim_history`; only `role="tool"` and their paired `role="assistant"` messages are eligible for removal.
- The function SHALL be a pure function: it SHALL NOT mutate the input list or any of its message dicts.
- `keep_steps` SHALL default to the value of the `HISTORY_TRIM_KEEP_STEPS` environment variable parsed as an integer, falling back to `4` if the variable is absent or unparseable.

The loop function SHALL call `trim_history` on the accumulated `messages` list after appending the current step's state message and before passing `messages` to `llm_client.chat()`. This call SHALL occur after `_compact_messages` is applied (trim is the primary reduction; compact is the safety net for extreme cases).

#### Scenario: Tool results outside the window are dropped

- **WHEN** `trim_history` is called with a messages list containing 6 complete tool-result groups and `keep_steps=4`
- **THEN** the returned list SHALL NOT contain any `role="tool"` messages from the 2 oldest groups
- **AND** the returned list SHALL NOT contain the `role="assistant"` messages paired with those 2 oldest groups
- **AND** the returned list SHALL contain all `role="tool"` and `role="assistant"` messages from the 4 most recent groups

#### Scenario: System prompt is always retained

- **WHEN** `trim_history` is called with any messages list where `messages[0]["role"] == "system"` and `keep_steps` is any positive integer
- **THEN** `messages[0]` SHALL appear as the first element of the returned list unchanged

#### Scenario: User state messages are never dropped

- **WHEN** `trim_history` is called with a messages list containing multiple `role="user"` state messages interspersed with tool-result groups
- **THEN** all `role="user"` messages SHALL be present in the returned list regardless of their position relative to `keep_steps`

#### Scenario: Keep window larger than history is a no-op

- **WHEN** `trim_history` is called with `keep_steps` greater than or equal to the total number of tool-result groups in `messages`
- **THEN** the returned list SHALL be equal to the input list (same messages, same order)

#### Scenario: HISTORY_TRIM_KEEP_STEPS env var is respected

- **WHEN** the environment variable `HISTORY_TRIM_KEEP_STEPS` is set to `"2"` and `trim_history` is called without an explicit `keep_steps` override
- **THEN** the function SHALL behave as if `keep_steps=2` was passed
