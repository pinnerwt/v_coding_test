## ADDED Requirements

### Requirement: CaseResult skip_reason field
`CaseResult` SHALL include a `skip_reason` field typed as
`Literal["live_disabled", "infra_unavailable", "fixture_missing", "feature_not_implemented"] | None`
with a default value of `None`.

The field SHALL appear in the serialized results JSON as `"skip_reason"` on every case entry. For non-skipped cases it SHALL be `null`. For skipped cases it SHALL be one of the four valid literal values.

`__post_init__` SHALL enforce two invariants at construction time:

1. When `status == "skipped"`, `skip_reason` MUST be non-`None`. Constructing a `CaseResult` with `status="skipped"` and `skip_reason=None` SHALL raise `ValueError`.
2. When `skip_reason` is non-`None`, its value MUST be one of the four allowed literals. Passing an unrecognized string SHALL raise `ValueError`.

#### Scenario: skip_reason is None for non-skipped case
- **WHEN** a `CaseResult` is constructed with `status="succeeded"` and `skip_reason=None`
- **THEN** construction SHALL succeed and `result.skip_reason` SHALL be `None`

#### Scenario: skip_reason is required when status is skipped
- **WHEN** a `CaseResult` is constructed with `status="skipped"` and `skip_reason=None`
- **THEN** `ValueError` SHALL be raised at construction time

#### Scenario: unrecognized skip_reason is rejected at construction
- **WHEN** a `CaseResult` is constructed with `skip_reason="unknown_reason"`
- **THEN** `ValueError` SHALL be raised at construction time

#### Scenario: valid skip_reason values are accepted
- **WHEN** a `CaseResult` is constructed with `status="skipped"` and each of `"live_disabled"`, `"infra_unavailable"`, `"fixture_missing"`, `"feature_not_implemented"`
- **THEN** construction SHALL succeed for each value

### Requirement: live_disabled skip path sets skip_reason
When `run_suite()` skips a case because `live=False` and the case lacks `fixture: true`, the resulting `CaseResult` SHALL have `skip_reason="live_disabled"`.

#### Scenario: --no-live run produces live_disabled skip_reason for non-fixture case
- **GIVEN** a case with no `fixture: true` field
- **AND** `run_suite()` is called with `live=False`
- **WHEN** the results JSON is read back
- **THEN** the case entry SHALL have `"status": "skipped"` and `"skip_reason": "live_disabled"`

#### Scenario: fixture case does not get skip_reason when run without --live
- **GIVEN** a case with `fixture: true`
- **AND** `run_suite()` is called with `live=False`
- **WHEN** the case executes via `_run_case`
- **THEN** the resulting `CaseResult.skip_reason` SHALL be `None` (the case ran; it was not skipped)

### Requirement: fixture_missing skip path sets skip_reason
When a case references a `fixture_path` (a filesystem path to a local HTML fixture) and that path does not exist on disk, `run_suite()` SHALL produce a `CaseResult` with `status="skipped"` and `skip_reason="fixture_missing"` instead of raising an exception or calling `_run_case`.

The `fixture_path` key in the case YAML is optional. Its absence SHALL NOT change existing behaviour.

#### Scenario: missing fixture file produces fixture_missing skip
- **GIVEN** a case dict with `fixture_path` set to a path that does not exist on disk
- **AND** `run_suite()` is called with `live=False`
- **WHEN** the suite processes that case
- **THEN** the `CaseResult` SHALL have `status="skipped"` and `skip_reason="fixture_missing"`
- **AND** `_run_case` SHALL NOT be called for that case

#### Scenario: fixture_path absent leaves existing skip logic unchanged
- **GIVEN** a case dict with no `fixture_path` key
- **WHEN** `run_suite()` processes that case
- **THEN** skip/run behaviour SHALL be identical to before this change
