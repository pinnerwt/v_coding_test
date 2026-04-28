## ADDED Requirements

### Requirement: iter_runnable_subcases shared helper

`eval.py` SHALL expose a module-level generator function with the exact signature:

- `iter_runnable_subcases(parent_cases: list[dict], *, live: bool) -> Iterator[tuple[dict, LocatorCache | None, SkipReason | None]]`

Each call to the generator iterates over `parent_cases` and, for each parent case, yields one tuple per runnable (or skippable) sub-case. The three elements of each yielded tuple are:

- `case: dict` — the fully-formed sub-case dict ready to pass to `_run_case`. When the parent has `variants`, the sub-case `id` is `<parent-id>-<variant>` and all other fields are inherited from the parent. When the parent has no `variants`, the sub-case dict is the parent dict unchanged.
- `shared_cache: LocatorCache | None` — the shared `LocatorCache(path=":memory:")` instance constructed once per parent case when `shared_cache: true` and `variants` is present; `None` otherwise. The same instance SHALL be yielded for every sub-case of the same parent when shared-cache is active (identity `is` check).
- `skip_reason: SkipReason | None` — one of `"fixture_missing"`, `"live_disabled"`, or `None`. `None` means the sub-case should be executed. Non-`None` means the consumer SHALL emit a skipped `CaseResult` and SHALL NOT call `_run_case`.

**Skip ladder (applied per sub-case in order):**

- If the sub-case has a `fixture_path` key whose value refers to a path that does not exist on disk, `skip_reason` is `"fixture_missing"`.
- Else if `live=False` and the sub-case does not have `fixture: true`, `skip_reason` is `"live_disabled"`.
- Else `skip_reason` is `None`.

The helper SHALL NOT call `_run_case`, construct a `CaseResult`, or perform any I/O beyond the filesystem existence check for `fixture_path`.

`run_suite` in `eval.py` and the `--repeats > 1` block in `benchmark.py::main` SHALL both consume `iter_runnable_subcases` and replace their inline variant-expansion and skip-ladder blocks with `for case, cache, skip_reason in iter_runnable_subcases(parent_cases, live=live): ...`.

#### Scenario: Two-variant shared-cache yields same LocatorCache instance for both sub-cases

- **GIVEN** a parent case with `variants: ["v1", "v2"]`, `fixture: true`, and `shared_cache: true`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly two tuples SHALL be yielded
- **AND** the `shared_cache` element of both tuples SHALL be the same `LocatorCache` object (identity `is` check)
- **AND** the `skip_reason` element of both tuples SHALL be `None`
- **AND** the first tuple `case["id"]` SHALL equal `<parent-id>-v1`
- **AND** the second tuple `case["id"]` SHALL equal `<parent-id>-v2`

#### Scenario: Live-only case yields live_disabled skip_reason when called with live=False

- **GIVEN** a parent case with `live: true` (no `fixture: true`) and no `variants`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly one tuple SHALL be yielded
- **AND** the `skip_reason` element SHALL equal `"live_disabled"`
- **AND** the `shared_cache` element SHALL be `None`

#### Scenario: Fixture-missing case yields fixture_missing skip_reason

- **GIVEN** a parent case with `fixture: true`, `fixture_path` set to a path that does not exist on disk, and no `variants`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly one tuple SHALL be yielded
- **AND** the `skip_reason` element SHALL equal `"fixture_missing"`
- **AND** the `shared_cache` element SHALL be `None`

#### Scenario: Non-variantized fixture case yields single tuple with no skip and no cache

- **GIVEN** a parent case with `fixture: true`, no `variants`, and no `fixture_path`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly one tuple SHALL be yielded
- **AND** the `skip_reason` element SHALL be `None`
- **AND** the `shared_cache` element SHALL be `None`
- **AND** the `case` element SHALL be the parent case dict unchanged

#### Scenario: Variants without shared_cache yields None cache for both sub-cases

- **GIVEN** a parent case with `variants: ["v1", "v2"]`, `fixture: true`, and no `shared_cache` key (or `shared_cache: false`)
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly two tuples SHALL be yielded
- **AND** the `shared_cache` element of both tuples SHALL be `None`
- **AND** the `skip_reason` element of both tuples SHALL be `None`
