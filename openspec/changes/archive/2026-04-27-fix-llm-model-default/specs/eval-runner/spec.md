## MODIFIED Requirements

### Requirement: Eval runner CLI
The system SHALL expose `scripts/eval.py` as a runnable script from `task2/` via `uv run python scripts/eval.py`. The CLI SHALL accept the following optional flags:

- `--live`: include non-fixture (live) cases in the run. Without this flag, only cases with `fixture: true` are executed.
- `--case <id>`: run only the case with the given `id`. Can be combined with `--live`.

The runner SHALL print per-case progress to stdout as each case completes (format: `[PASS|FAIL|SKIP] <id> (<steps> steps, $<usd>)`). After the suite completes, it SHALL print the path to the written results JSON.

The runner SHALL exit with code 0 if all executed cases have `status` in `{succeeded, unverified, skipped}`. It SHALL exit with code 1 if any executed case has `status` in `{failed, blocked, timeout}`.

The runner SHALL NOT hardcode any LLM provider URL. `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` are read from env. When `LLM_MODEL` is unset, `build_clients()` SHALL fall back to `agent.llm._DEFAULT_LLM_MODEL` — NOT to a locally-defined string literal. `LLM_BASE_URL` defaults to `http://localhost:8090/v1`; `LLM_API_KEY` defaults to `"local"`.

#### Scenario: Runner completes and writes results file
- **WHEN** `uv run python scripts/eval.py` is invoked from `task2/` with only fixture cases present
- **THEN** the runner SHALL execute all fixture cases, print progress, and write a results JSON

#### Scenario: --case flag runs only the named case
- **WHEN** `uv run python scripts/eval.py --case fixture-heading` is invoked
- **THEN** the runner SHALL execute only the `fixture-heading` case and write a results JSON with exactly 1 entry

#### Scenario: Runner exits non-zero on case failure
- **WHEN** any executed case returns `status: "failed"`
- **THEN** the runner SHALL exit with code 1

#### Scenario: Runner exits zero when all cases pass or skip
- **WHEN** all executed cases have `status` in `{succeeded, unverified, skipped}`
- **THEN** the runner SHALL exit with code 0

#### Scenario: LLM_BASE_URL is forwarded to LLMClient, not hardcoded
- **WHEN** `LLM_BASE_URL=http://custom:9999` is set in env
- **THEN** the `LLMClient` constructed by the runner SHALL use `base_url="http://custom:9999"`

#### Scenario: build_clients uses shared default when LLM_MODEL is unset
- **GIVEN** `LLM_MODEL` is not set in the process environment
- **WHEN** `build_clients()` is invoked
- **THEN** the `LLMClient` SHALL be constructed with `model` equal to `agent.llm._DEFAULT_LLM_MODEL` (`"qwen3-5-27b"`)
- **AND** the string `"qwen3"` SHALL NOT appear as a default fallback anywhere in `scripts/eval.py`
