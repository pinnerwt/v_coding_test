## ADDED Requirements

### Requirement: _run_case failure_detail for LLMError

When `_run_case`'s `except Exception as exc:` handler catches an exception that is an instance of `agent.llm.LLMError`, it SHALL produce a `failure_detail` string that includes both the HTTP status code and a truncated body snippet, rather than the opaque `repr(exc)` form.

The required format is:
`f"LLMError(kind={exc.kind!r}, status={exc.status}, body={(exc.body or '')[:512]!r})"`

For any other exception type, `failure_detail` SHALL remain `repr(exc)` (no behavior change for non-`LLMError` exceptions).

`failure_class` SHALL remain `"tool_error"` for all exceptions caught by this handler.

`steps` SHALL remain `0` in the exception path (the true step count inside `loop()` is not accessible to `_run_case` when `loop()` raises).

#### Scenario: LLMError 400 produces structured failure_detail

- **GIVEN** `agent.loop.loop` is mocked to raise `LLMError("http 400", kind="http", status=400, body='{"error":{"type":"exceed_context_size_error","n_prompt_tokens":34074}}')`
- **WHEN** `_run_case(case, llm_client=ANY, browser=ANY)` is called
- **THEN** the returned `CaseResult.failure_detail` SHALL contain the substring `"status=400"`
- **AND** the returned `CaseResult.failure_detail` SHALL contain a slice of the body string (e.g. `"exceed_context_size_error"`)
- **AND** `CaseResult.failure_class` SHALL equal `"tool_error"`

#### Scenario: non-LLMError exceptions are unaffected

- **GIVEN** `agent.loop.loop` is mocked to raise `RuntimeError("unexpected")`
- **WHEN** `_run_case(case, llm_client=ANY, browser=ANY)` is called
- **THEN** the returned `CaseResult.failure_detail` SHALL equal `repr(RuntimeError("unexpected"))` (i.e. `"RuntimeError('unexpected')"`)
- **AND** `CaseResult.failure_class` SHALL equal `"tool_error"`
