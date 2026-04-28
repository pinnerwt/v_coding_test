## ADDED Requirements

### Requirement: Message history compaction

The system SHALL provide a private function `_compact_messages(messages: list[dict], budget_chars: int) -> list[dict]` in `agent/loop.py` that reduces the serialized size of the `messages` list to stay under `budget_chars` characters (measured as `sum(len(json.dumps(m)) for m in messages)`).

Rules:
1. `messages[0]` (the system prompt, `role == "system"`) SHALL never be modified or removed.
2. The most recent turn SHALL be kept verbatim. The "most recent turn" is defined as: all messages from (and including) the last `user`-role message whose `content` starts with `"Current state: "` to the end of the list.
3. For older `user`-role messages whose `content` starts with `"Current state: "`, the `content` SHALL be replaced with the literal string `"Current state: <elided>"`.
4. For `tool`-role messages that are NOT part of the most recent turn, the `content` SHALL be replaced with the literal string `"<read tool result elided>"`.
5. If, after one pass of elisions, `total > budget_chars` still holds, the function SHALL continue eliding until `total <= budget_chars` or no further elisions are possible.
6. When `total <= budget_chars` on entry, the function SHALL return `messages` unchanged (no mutation).

The loop function (`agent.loop.loop`) SHALL call `_compact_messages(messages, _budget)` immediately before every `llm_client.chat(messages, tools=TOOLS)` call, where `_budget` is read from the environment variable `LLM_CONTEXT_CHAR_BUDGET` (parsed as `int`) or falls back to the module-level constant `_DEFAULT_CONTEXT_CHAR_BUDGET = 80_000`.

#### Scenario: compaction fires when messages exceed budget

- **GIVEN** a stub `LLMClient` that always returns a `goto` tool call
- **AND** a stub browser that returns ≥ 4 KB AX-tree JSON observations per step
- **WHEN** `loop("task", browser, llm_client, max_steps=25)` runs to timeout
- **THEN** the `messages` argument passed to the stub's last `chat()` call SHALL have `sum(len(json.dumps(m)) for m in messages) < 80_000`
- **AND** at least one `user`-role message in the history SHALL have `content == "Current state: <elided>"`
- **AND** `messages[0]["role"]` SHALL equal `"system"`

#### Scenario: most recent observation is never elided

- **GIVEN** the same stub setup as above
- **WHEN** the loop runs to timeout with compaction active
- **THEN** the last `user`-role message in `messages` whose `content` starts with `"Current state: "` SHALL NOT have `content == "Current state: <elided>"`
- **AND** `messages[0]["content"]` SHALL equal `_build_system_prompt("task")` verbatim

#### Scenario: compaction is a no-op when under budget

- **GIVEN** a `messages` list whose `sum(len(json.dumps(m)) ...)` is less than `budget_chars`
- **WHEN** `_compact_messages(messages, budget_chars)` is called
- **THEN** the returned list SHALL be identical to the input (no mutations)
