## ADDED Requirements

### Requirement: Case YAML canary field

The eval runner's case YAML schema SHALL recognize an optional `canary: bool` field (default `false`). Its presence SHALL NOT alter the runner's skip logic, execution order, or result status computation. A case with `canary: true` runs exactly as a case without it; `canary` is informational metadata consumed downstream by `canary_gate.py`.

`load_cases` SHALL accept YAML files that include `canary: true` or `canary: false` without raising a `ValueError`. The field SHALL be forwarded verbatim in the returned case dict.

`CaseResult` SHALL gain a `canary: bool = False` field. `__post_init__` SHALL NOT add any new invariant on `canary`. The field SHALL appear in the serialized results JSON on every case entry (as `"canary": true` or `"canary": false`).

`run_suite` SHALL pass `canary=case.get("canary", False)` when constructing each `CaseResult` via `_skipped_result` or `_run_case`. `_run_case` itself does not need to inspect `canary`; it merely accepts and forwards it to `CaseResult`.

#### Scenario: load_cases accepts canary field without error

- **WHEN** `load_cases` is called on a YAML file containing `canary: true`
- **THEN** no `ValueError` is raised and the returned dict has `canary == True`

#### Scenario: load_cases sets canary to false by default when field is absent

- **WHEN** `load_cases` is called on a YAML file with no `canary` key
- **THEN** the returned dict has `canary` either absent or falsy (gate uses `.get("canary", False)`)

#### Scenario: CaseResult accepts canary=True without error

- **WHEN** `CaseResult` is constructed with `canary=True` and `status="succeeded"`
- **THEN** construction SHALL succeed and `result.canary` SHALL be `True`

#### Scenario: CaseResult canary defaults to False

- **WHEN** `CaseResult` is constructed without specifying `canary`
- **THEN** `result.canary` SHALL be `False`

#### Scenario: canary field appears in results JSON for canary-tagged case

- **GIVEN** a case with `canary: true` is run by `run_suite`
- **WHEN** the results JSON is parsed
- **THEN** the case entry SHALL have `"canary": true`

#### Scenario: canary field appears as false in results JSON for non-canary case

- **GIVEN** a case YAML with no `canary` key
- **WHEN** `run_suite` produces the results JSON
- **THEN** the case entry SHALL have `"canary": false`
