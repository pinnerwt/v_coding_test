---
id: 65
slug: source-replay-fixture-system-prompt-via
status: active
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
- 99
filed_pr: null
merged_pr: null
archived_at: null
trigger: Source replay-fixture system prompt via `_build_system_prompt` instead of
  literal duplication.
---

65. **Source replay-fixture system prompt via `_build_system_prompt` instead of literal duplication.** Currently `tests/fixtures/traces/simple_goto_done.jsonl` embeds the verbatim system prompt in two `decide` `LLMCallEvent` lines, which means every prompt edit forces a manual JSONL update (the fail-prompt tightening in PR #99 had to do this by hand). A failing test should construct the expected JSONL by interpolating `_build_system_prompt(...)` and assert `simple_goto_done.jsonl` matches; the green path either (a) regenerates the fixture from the live prompt at test time, or (b) replaces the literal in the JSONL with a sentinel that the replay loader expands. Acceptance: editing `_build_system_prompt` no longer requires a fixture edit to keep the replay test green.
