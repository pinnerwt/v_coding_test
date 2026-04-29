---
id: 68
slug: strip-dangling-tool-calls-references-when
status: archived
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 66
filed_pr: null
merged_pr: null
archived_at: '2026-04-29'
trigger: 'surfaced by review subagent on PR #101 iteration 1; deferred to keep #66''s
  scope tight.'
---

68. **Strip dangling `tool_calls` references when `_compact_messages` elides a tool reply.** When `_compact_messages` replaces a `tool`-role message's `content` with `"<read tool result elided>"`, the preceding `assistant` message still references the original `tool_call_id`, so a strict OpenAI-compatible endpoint can in principle reject the conversation as malformed (assistant claims it called `read` with id=tc-7, but the matching tool reply is "<elided>"). Qwen llama.cpp tolerates this in practice (PR #101 shipped without endpoint complaints) but the contract is loose. Concrete steps: when eliding tool content at index `i`, locate the most recent prior `assistant` message with a `tool_calls` array containing that `tool_call_id` and either (a) drop the matching entry from `tool_calls` (re-serializing if the assistant message has no other content), or (b) replace the assistant content with a sentinel like `"<elided turn>"` and clear its `tool_calls`. Tests: a unit test with a 4-turn message history (assistant tool_calls → tool reply → assistant tool_calls → tool reply) where compaction elides the first tool reply asserts the matching `tool_calls` entry is also stripped from the matching assistant message; round-trip the resulting `messages` through `LLMClient.chat`'s payload-building path against a stub OpenAI-strict endpoint that returns 400 on dangling tool_call ids — assert no 400. *Why useful:* future-proofs `_compact_messages` for endpoints stricter than llama.cpp. *Trigger:* surfaced by review subagent on PR #101 iteration 1; deferred to keep #66's scope tight.
