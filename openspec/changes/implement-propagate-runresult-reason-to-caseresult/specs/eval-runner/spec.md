## ADDED Requirements

### Requirement: CaseResult carries the run_result.reason for terminations that produced a RunResult

`scripts.eval.CaseResult` SHALL include a field `reason: str | None = None`, placed in the dataclass immediately after the `failure_detail` field. The field SHALL default to `None` so all existing construction sites that do not pass `reason` continue to compile and run without modification, and so the serialized JSON shape remains backward-compatible (additive only).

When `_run_case` reaches the success-path `CaseResult(...)` constructor (the path executed after `agent.loop.loop()` returns a `RunResult`), it SHALL pass `reason=run_result.reason`. This propagates the four established `RunResultReason` values (`"stuck_repeat"`, `"no_tool_call_repeat"`, `"seconds_budget"`, `"no_progress"`) — and `None` for terminations that do not set a reason (e.g. `done`, planner-emitted `fail`, `max_steps`-exhausted `timeout`, supervisor halt) — into the serialized benchmark JSON.

When `_run_case` reaches the exception-path `CaseResult(...)` constructor (the path executed when `loop()` raised before returning), it SHALL leave `reason` at its default `None`. No `RunResult` exists on that path; the diagnostic information is already carried by `failure_class="tool_error"` and `failure_detail=<exception repr>`.

The `skipped`-path constructor (when `run_suite` skips a case for `live_disabled` etc.) SHALL leave `reason` at its default `None`; the `skip_reason` field already covers that path.

The serialized JSON written by `asdict(CaseResult)` SHALL include a `"reason"` key on every case entry. For cases where the loop terminated with no reason set, or where the case was skipped or crashed, the value SHALL be `null`.

#### Scenario: succeeded case has reason None in CaseResult

- **GIVEN** `_run_case` is invoked with a stubbed `loop` returning `RunResult(status="succeeded", reason=None, result={}, evidence={"url": "http://x", "text_snippet": "x"}, steps=1, prompt_tokens=10, completion_tokens=5, usd=0.001, latency_ms_total=100, latency_ms_per_step=[100], step_breakdown=[])`
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.reason` SHALL be `None`

#### Scenario: seconds_budget timeout propagates reason to CaseResult

- **GIVEN** `_run_case` is invoked with a stubbed `loop` returning `RunResult(status="timeout", reason="seconds_budget", result=None, evidence=None, steps=15, prompt_tokens=100, completion_tokens=50, usd=0.05, latency_ms_total=120000, latency_ms_per_step=[8000]*15, step_breakdown=[])`
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.reason` SHALL equal `"seconds_budget"`

#### Scenario: no_progress termination propagates reason to CaseResult

- **GIVEN** `_run_case` is invoked with a stubbed `loop` returning `RunResult(status="failed", reason="no_progress", result=None, evidence=None, steps=4, prompt_tokens=100, completion_tokens=50, usd=0.005, latency_ms_total=2000, latency_ms_per_step=[500]*4, step_breakdown=[])`
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.reason` SHALL equal `"no_progress"`

#### Scenario: stuck_repeat termination propagates reason to CaseResult

- **GIVEN** `_run_case` is invoked with a stubbed `loop` returning `RunResult(status="failed", reason="stuck_repeat", result=None, evidence=None, steps=3, prompt_tokens=100, completion_tokens=50, usd=0.005, latency_ms_total=1500, latency_ms_per_step=[500]*3, step_breakdown=[])`
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.reason` SHALL equal `"stuck_repeat"`

#### Scenario: serialized benchmark JSON includes reason key on every case

- **GIVEN** `run_suite` is invoked on a tiny in-memory fixture-only case list with a stubbed `loop`
- **WHEN** the run completes and writes the results JSON
- **THEN** every entry under the JSON's case-list (whatever the top-level container key is) SHALL have a `"reason"` key whose value is either `null` or one of the recognized `RunResultReason` strings

#### Scenario: exception-path CaseResult has reason None

- **GIVEN** `_run_case` is invoked and the call to `loop()` raises an exception (e.g. an LLM transport error) before returning a `RunResult`
- **WHEN** the exception-path `CaseResult` is constructed with `failure_class="tool_error"` and `failure_detail=<exception repr>`
- **THEN** the returned `CaseResult.reason` SHALL be `None`
