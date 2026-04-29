## MODIFIED Requirements

### Requirement: Message history compaction

The system SHALL provide a private function `_compact_messages(messages: list[dict], budget_chars: int) -> list[dict]` in `agent/loop.py` that reduces the serialized size of the `messages` list to stay under `budget_chars` characters (measured as `sum(len(json.dumps(m)) for m in messages)`) by **dropping** the oldest non-system, non-most-recent-state messages. The kept messages SHALL be byte-identical to the input messages — the function SHALL NOT mutate any message's `content`, `role`, or any other field.

Rules:
1. `messages[0]` (the system prompt, `role == "system"`) SHALL never be modified or removed.
2. The most recent state turn SHALL be kept verbatim. The "most recent state" is defined as the last `user`-role message whose `content` contains the substring `"Current state: "`. This message and any messages after it (e.g. the most recent `tool` results corresponding to the upcoming decision) SHALL never be dropped.
3. To bring `total <= budget_chars`, the function SHALL drop messages from index `1` upward (i.e. oldest first), advancing past `last_state_idx` is forbidden.
4. The function SHALL drop *whole messages*; it SHALL NOT mutate any kept message's content. A kept message in the result SHALL satisfy `kept_message is input_message_at_some_index_j` for some `j` in the original list.
5. When `total <= budget_chars` on entry, the function SHALL return `messages` unchanged.
6. When even `[messages[0], messages[last_state_idx:]]` exceeds `budget_chars`, the function SHALL return that minimum-keep set rather than dropping the system or last-state messages. The LLM client is responsible for handling the oversize prompt in that pathological case.

The loop function (`agent.loop.loop`) SHALL call `_compact_messages(messages, _budget)` immediately before every `llm_client.chat(messages, tools=TOOLS)` call, where `_budget` is read from the environment variable `LLM_CONTEXT_CHAR_BUDGET` (parsed as `int`) or falls back to the module-level constant `_DEFAULT_CONTEXT_CHAR_BUDGET = 80_000`.

The constants `_ELIDED_STATE_CONTENT` and `_ELIDED_TOOL_CONTENT` SHALL NOT exist in `agent/loop.py` — they are dead code under the drop-based contract.

#### Scenario: compaction fires by dropping when messages exceed budget

- **GIVEN** a stub `LLMClient` that always returns a `goto` tool call
- **AND** a stub browser that returns ≥ 4 KB AX-tree JSON observations per step
- **WHEN** `loop("task", browser, llm_client, max_steps=25)` runs to timeout
- **THEN** the `messages` argument passed to the stub's last `chat()` call SHALL have `sum(len(json.dumps(m)) for m in messages) < 80_000`
- **AND** no `user`-role message in the result SHALL have `content == "Current state: <elided>"`
- **AND** no `tool`-role message in the result SHALL have `content == "<read tool result elided>"`
- **AND** `messages[0]["role"]` SHALL equal `"system"`

#### Scenario: most recent observation is never dropped

- **GIVEN** the same stub setup as above
- **WHEN** the loop runs to timeout with compaction active
- **THEN** the last `user`-role message in the original (pre-compaction) list whose `content` contains the substring `"Current state: "` SHALL be present byte-identically in the post-compaction list
- **AND** `messages[0]["content"]` SHALL equal `_build_system_prompt("task")` verbatim

#### Scenario: compaction is a no-op when under budget

- **GIVEN** a `messages` list whose `sum(len(json.dumps(m)) ...)` is less than `budget_chars`
- **WHEN** `_compact_messages(messages, budget_chars)` is called
- **THEN** the returned list SHALL be identical to the input (no mutations)

#### Scenario: kept messages are byte-identical to inputs

- **GIVEN** an oversized `messages` list
- **WHEN** `_compact_messages(messages, budget_chars)` is called and returns a list `result`
- **THEN** for every `m` in `result`, there SHALL exist an index `j` such that `m == messages[j]` field-for-field (no `content` rewriting)
- **AND** the substring `"<elided>"` SHALL NOT appear in any `result[i]["content"]` value

#### Scenario: prefix stability across consecutive compactions

- **GIVEN** a list `L1` that exceeds `budget_chars`, compacted to `R1 = _compact_messages(L1, budget_chars)`
- **AND** a list `L2 = L1 + [new_state_msg, new_tool_msg]` (new turn appended) that also exceeds `budget_chars`, compacted to `R2 = _compact_messages(L2, budget_chars)`
- **THEN** the kept overlap region of `R2` (i.e. messages in `R2` that originated from `L1`) SHALL be a contiguous tail of `R1` — formally, there SHALL exist indices `k, m` such that `R2[1:m] == R1[k:]` field-for-field
- **AND** this property SHALL hold even when more messages were dropped on the second pass than on the first
