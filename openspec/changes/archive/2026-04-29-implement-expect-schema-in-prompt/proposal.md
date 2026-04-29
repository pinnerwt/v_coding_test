## Why

The WebVoyager benchmark cases declare `expect.schema = {"answer": "str"}`, meaning the agent must return `{"answer": "<text>"}` in `done.result` for the `answer.nonempty` validator to pass. Today `_build_system_prompt` never shows the LLM this schema, so the model packs answers under arbitrary keys (`"text"`, `"value"`, `"summary"`). The consequence is that `webvoyager-2` and `webvoyager-3` already call `done` (status=`succeeded`) but record `validators[answer.nonempty].ok=false` — phantom successes that suppress retries while still failing the scoreboard. Landing this change is expected to raise the WebVoyager pass rate from 0/3 to ~2/3 with no other fix.

## What Changes

- `task2/agent/loop.py` — `_build_system_prompt(task, expect=None)` gains a new keyword-only parameter `expect: dict | None = None`. When `expect` is not `None` and `expect.get("schema")` is non-empty, a single line is appended to the prompt: `Your done.result MUST be a JSON object matching this schema: <json>. Required fields: <sorted keys>.`
- `task2/agent/loop.py` — `loop()` gains `expect: dict | None = None` as a new keyword-only parameter. It is forwarded directly to `_build_system_prompt` when building the initial system message.
- `task2/scripts/eval.py` — `_run_case` passes `expect=case.get("expect")` into `loop()`.
- `task2/tests/` — new unit tests covering both the schema-present and schema-absent paths for `_build_system_prompt`, and a stub test asserting `loop()` threads `expect` correctly.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-loop`: `_build_system_prompt` and `loop()` gain the `expect` parameter; schema injection appended to system prompt when non-empty.

## Impact

- `task2/agent/loop.py`: two signatures change; all existing call sites work unchanged (new kwarg defaults to `None`).
- `task2/scripts/eval.py`: `_run_case` passes one new kwarg to `loop()`; no other change.
- `task2/api/server.py`: `_run_agent` does not yet plumb `expect_schema` into `loop()` — that wiring is noted as an optional follow-up task (task 9) in `tasks.md`; the API path is out of scope for this ticket.
- No new dependencies; token overhead is 20-40 tokens per run.
- No breaking changes for existing callers (`api/server.py`, tests not updated in this ticket).
