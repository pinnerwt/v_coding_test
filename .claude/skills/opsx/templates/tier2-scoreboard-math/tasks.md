## 1. Red — failing tests

- [ ] 1.1 {{test_function_1}} — {{what_test_1_asserts}}
- [ ] 1.2 {{test_function_2}} — {{what_test_2_asserts}}
- [ ] 1.3 {{test_function_3}} — {{what_test_3_asserts}} ({{backward_compat_test_clause}})
- [ ] 1.4 Run `uv run pytest task2/tests/{{test_file_name}}.py -x` from `task2/` and confirm tests fail for the expected reason ({{expected_red_failure_reason}}).

## 2. Green — minimal implementation

- [ ] 2.1 Add {{symbols}} to `task2/scripts/{{primary_script}}.py` ({{field_or_helper_addition}}).
- [ ] 2.2 Wire {{helper_function}} through `{{call_site}}` in `task2/scripts/{{secondary_script}}.py` so {{render_change}}.
- [ ] 2.3 Run `uv run pytest task2/tests/{{test_file_name}}.py -x` from `task2/` and confirm all tests pass.

## 3. Full Suite

- [ ] 3.1 Run `uv run pytest task2/tests/` from `task2/` and confirm no regressions. If a golden-snapshot fixture (`task2/tests/fixtures/results/*_scoreboard.md`) exists and the new render path changes its output, update the snapshot in this commit and verify it still serves as a regression guard.
- [ ] 3.2 {{spot_check_step_optional}}

## 4. Clean — lint + format

- [ ] 4.1 `uv run ruff check --fix .` from `task2/`.
- [ ] 4.2 `uv run ruff format .` from `task2/`.
- [ ] 4.3 `uv run ruff check .` from `task2/` — confirm zero errors, zero warnings.
- [ ] 4.4 `uv run pytest` from `task2/` — confirm green bar after formatting.
