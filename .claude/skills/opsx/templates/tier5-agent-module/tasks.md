## 1. Red — failing tests

- [ ] 1.1 {{test_function_1}} — {{what_test_1_asserts}}
- [ ] 1.2 {{test_function_2}} — {{what_test_2_asserts}}
- [ ] 1.3 {{test_function_3}} — {{what_test_3_asserts}}
- [ ] 1.4 Run `uv run pytest task2/tests/agent/{{test_file_name}}.py -x` from `task2/` and confirm all new tests fail for the expected reason ({{expected_red_failure_reason}}).

## 2. Green — minimal implementation

- [ ] 2.1 {{green_step_1}} in `{{file_path}}`.
- [ ] 2.2 {{green_step_2}} ({{symbols}} added/modified per the design decision).
- [ ] 2.3 {{green_step_3}}.
- [ ] 2.4 Run `uv run pytest task2/tests/agent/{{test_file_name}}.py -x` from `task2/` and confirm all tests pass.

## 3. Full Suite

- [ ] 3.1 Run `uv run pytest task2/tests/` from `task2/` and confirm no regressions in any existing test file.
- [ ] 3.2 {{regression_followup_step_optional}}

## 4. Clean — lint + format

- [ ] 4.1 `uv run ruff check --fix .` from `task2/`.
- [ ] 4.2 `uv run ruff format .` from `task2/`.
- [ ] 4.3 `uv run ruff check .` from `task2/` — confirm zero errors, zero warnings.
- [ ] 4.4 `uv run pytest` from `task2/` — confirm green bar after formatting.
