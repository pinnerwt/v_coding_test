## ADDED Requirements

### Requirement: Case YAML live field
The eval runner's case YAML schema SHALL recognize `live: true` as an optional informational field. Its presence SHALL NOT alter the runner's skip logic; skip logic remains driven solely by the absence of `fixture: true`. A case with `live: true` and no `fixture: true` SHALL be skipped when `run_suite` is called with `live=False`.

#### Scenario: Live-flagged case skipped without --live
- **WHEN** a YAML case has `live: true` and no `fixture: true`, and `run_suite` is called with `live=False`
- **THEN** the case produces a `CaseResult` with `status == "skipped"` without calling `_run_case`

#### Scenario: Live-flagged case executed with --live
- **WHEN** a YAML case has `live: true` and no `fixture: true`, and `run_suite` is called with `live=True`
- **THEN** `_run_case` is called for that case and its result (not `"skipped"`) appears in the results JSON

#### Scenario: load_cases accepts live field without error
- **WHEN** `load_cases` is called on a YAML file containing `live: true`
- **THEN** no `ValueError` is raised and the returned dict includes `live == True`
