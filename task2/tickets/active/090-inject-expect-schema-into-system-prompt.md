---
id: 90
slug: inject-expect-schema-into-system-prompt
status: active
tier: 3
urgency: P0
axes:
  pass_rate: 60
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json
- task2/benchmark/task2-implement-fast-path-ticket-archival/webvoyager/20260429_104152.json
- task2/eval/bench/webvoyager_loader.py
- task2/scripts/eval.py
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: 2026-04-29 — user-driven webvoyager timeout investigation; ticket queue restart
---

90. **Inject `expect.schema` into the agent system prompt so `done.result` matches the validator.** The WebVoyager validator is `answer.nonempty` (`webvoyager_loader.py:6`), which `run_validators` (`scripts/eval.py:83`) implements as `isinstance(result.get("answer"), str) and bool(result["answer"].strip())`. Today `_build_system_prompt` (`agent/loop.py:280`) only tells the LLM to "call the `done` tool with a structured result and evidence" — the expected schema (`{"answer": "str"}`) is *never* shown to the agent, so the LLM packs answers under arbitrary keys (`{"text": ...}`, `{"value": ...}`, `{"summary": ...}`). Consequence: `webvoyager-2` and `webvoyager-3` in both `20260429_122531.json` and `20260429_104152.json` are recorded as `status=succeeded` (the agent did call `done` with valid evidence) but `validators[answer.nonempty].ok=false` — they look like passes in the run loop and like failures in the scoreboard, which is the worst of both worlds. **Fix:** thread the case's `expect` dict through `_run_case` → `loop()` → `_build_system_prompt`. When `expect.schema` is non-empty, append a literal "Your `done.result` MUST be a JSON object matching this schema: `<json.dumps(schema)>`. Required fields: `<sorted keys>`." line to the system prompt. The schema is a small dict (1-3 keys) so the token overhead is negligible. Tests: (1) unit test asserts `_build_system_prompt(task, expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]})` includes the substring `"answer"` and the literal token `MUST`; (2) unit test asserts `_build_system_prompt(task, expect=None)` is byte-identical to today's output (default-path safety); (3) integration test (skip without live Qwen) runs a WebVoyager case with a stub LLM that always emits `{"role": "tool", "tool_calls": [{"name": "done", "arguments": '{"result": {"answer": "X"}, "evidence": {...}}'}]}` once seeded with the schema-aware prompt, and asserts `validators[answer.nonempty].ok is True`. *Why useful:* this is the single highest-leverage `pass_rate` ticket on the board — `webvoyager-2/3` already *succeed*, they just answer in the wrong shape. Land #90 and the WebVoyager pass rate jumps from 0/3 to ~2/3 with no other change. **Estimated impact justifies axes pass_rate +60.** *Trigger:* 2026-04-29 user-driven webvoyager timeout investigation.
