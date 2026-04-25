## 1. Project scaffolding

- [x] 1.1 Add `pyproject.toml` with deps `httpx>=0.27` and dev-deps `pytest`, `respx`
- [x] 1.2 Create empty `agent/__init__.py` and `tests/__init__.py`, `tests/agent/__init__.py`
- [x] 1.3 Add `.gitignore` entries for `.venv/`, `__pycache__/`, `.pytest_cache/` if not already covered
- [x] 1.4 Add a top-level `pytest.ini` (or `[tool.pytest.ini_options]` in pyproject) pointing rootdir at `tests/` and clearing `LLM_*` env vars in a session-scoped autouse fixture

## 2. Red — failing tests for `agent/llm.py`

- [x] 2.1 `tests/agent/test_llm.py::test_default_base_url`: with no env, `chat(messages=[...], model="m")` hits `http://localhost:8090/v1/chat/completions` (assert via `respx`)
- [x] 2.2 `test_env_base_url_honored`: monkeypatch `LLM_BASE_URL=https://api.example.com/v1` and `LLM_MODEL=qwen3.5`; call `chat(messages=[...])`; assert URL is `https://api.example.com/v1/v1/chat/completions` and body `model=qwen3.5`
- [x] 2.3 `test_explicit_kwarg_overrides_env`: env `LLM_BASE_URL=https://env.example.com`; call with `base_url="https://override.example.com"`; assert override wins
- [x] 2.4 `test_request_body_shape`: assert body JSON contains `model`, `messages`, `temperature` (default 0.0); assert `tools` and `seed` are absent when not passed
- [x] 2.5 `test_tools_and_seed_forwarded`: pass `tools=[...]` and `seed=7`; assert both present verbatim in body
- [x] 2.6 `test_authorization_header_present`: `LLM_API_KEY=sk-test` → assert `Authorization: Bearer sk-test`
- [x] 2.7 `test_authorization_header_absent`: no key → assert no `Authorization` header
- [x] 2.8 `test_parses_content_response`: respx mock returns canonical OpenAI choice with text content; assert `ChatResponse.content`, `finish_reason`, `model`, `usage.*`, and that `tool_calls == []`
- [x] 2.9 `test_parses_tool_call_response`: respx returns `message.tool_calls=[…]` and no content; assert `tool_calls[0].id/name/arguments` and `content is None`
- [x] 2.10 `test_raw_field_preserved`: assert `ChatResponse.raw` equals the full parsed JSON dict
- [x] 2.11 `test_missing_model_raises_config_error`: no `LLM_MODEL` and no kwarg → `LLMError(kind="config")`; assert no HTTP request made (respx route uncalled)
- [x] 2.12 `test_http_500_raises_http_error`: respx returns 500 with body; assert `LLMError(kind="http", status=500, body="...")`
- [x] 2.13 `test_transport_error_raises_transport_error`: respx raises `httpx.ConnectError`; assert `LLMError(kind="transport")` with `cause` set
- [x] 2.14 `test_decode_error_on_bad_json`: respx returns 200 with non-JSON body; assert `LLMError(kind="decode")`
- [x] 2.15 `test_decode_error_on_missing_choices`: respx returns 200 with `{"id": "x"}`; assert `LLMError(kind="decode")`
- [x] 2.16 `test_error_body_truncated_to_2048`: respx returns 502 with 5KB body; assert `len(err.body) <= 2048`
- [x] 2.17 `test_llmclient_reuses_config`: construct `LLMClient(base_url=..., model=...)`; call `.chat()` twice; assert both calls use the same URL and model
- [x] 2.18 `test_llmclient_per_call_override`: constructor `model="default-m"`, call `.chat(model="other-m")`; assert body model is `"other-m"`
- [x] 2.19 Run `pytest`; confirm every test fails for the *expected* reason (ImportError or AssertionError on missing module — not config errors in the test harness)

## 3. Green — minimal implementation

- [x] 3.1 `agent/llm.py`: define `LLMError(Exception)` with `kind`, `status`, `body`, `cause`
- [x] 3.2 Define `@dataclass(frozen=True) Usage(prompt_tokens: int, completion_tokens: int, total_tokens: int)`
- [x] 3.3 Define `@dataclass(frozen=True) ToolCall(id: str, name: str, arguments: str)`
- [x] 3.4 Define `@dataclass(frozen=True) ChatResponse(content, tool_calls, finish_reason, model, usage, raw)`
- [x] 3.5 Implement `LLMClient.__init__(base_url=None, model=None, api_key=None, timeout=60.0)`: resolve from kwargs → env → defaults; instantiate one `httpx.Client(timeout=timeout)`
- [x] 3.6 Implement `LLMClient.chat(messages, *, model=None, temperature=0.0, tools=None, seed=None) -> ChatResponse`: build body (omit `tools`/`seed` when None), POST to `f"{base_url}/v1/chat/completions"`, set `Authorization` only when `api_key` is set, parse response, raise typed `LLMError` on each failure path with body truncation
- [x] 3.7 Module-level `chat(...)`: thin wrapper that constructs an `LLMClient` per call and delegates
- [x] 3.8 Run tests until all green

## 4. Refactor under green

- [x] 4.1 Extract a `_resolve(name, kwarg, env, default)` helper if config resolution duplicates
- [x] 4.2 Extract `_parse_choice(choice)` to keep `chat()` readable; ensure the `decode` error path still triggers on any malformed shape
- [x] 4.3 Re-run tests; ensure no regressions

## 5. Verification

- [ ] 5.1 `openspec verify implement-llm-client` passes
- [ ] 5.2 `pytest -q` shows all `tests/agent/test_llm.py` green
- [ ] 5.3 Confirm no hosted-provider URL or hardcoded API key appears anywhere in `agent/` (`grep -RIn "openai.com\|anthropic.com" agent/` returns nothing)
- [ ] 5.4 Commit on a feature branch with conventional message: `feat(task2): add agent/llm.py OpenAI-compatible client (TDD)`
