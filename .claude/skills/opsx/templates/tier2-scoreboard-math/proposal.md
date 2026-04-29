## Why

{{rationale_one_liner}}

## What Changes

- `task2/scripts/{{primary_script}}.py` — {{primary_script_change}}.
- `task2/scripts/{{secondary_script}}.py` — {{secondary_script_change}} ({{render_or_compute_role}}).
- {{helper_summary}} — a small `{{helper_function}}` encapsulates {{threshold_or_logic}} and is unit-tested directly.
- New tests in `task2/tests/{{test_file_name}}.py` covering: {{test_axes_summary}}.

## Capabilities

### New Capabilities

{{new_capabilities_block}}

### Modified Capabilities

- `{{capability}}`: {{capability_modification_summary}}

## Impact

- `task2/scripts/{{primary_script}}.py`: {{primary_script_impact}}.
- `task2/scripts/{{secondary_script}}.py`: {{secondary_script_impact}}.
- `task2/tests/{{test_file_name}}.py`: {{tests_impact}}.
- {{additional_impact_lines}}
- No breaking changes: {{backward_compat_clause}} (the new field defaults to {{default_value}}, so old results JSONs without the key render unchanged).
- No new dependencies; pure Python arithmetic on existing fields.
