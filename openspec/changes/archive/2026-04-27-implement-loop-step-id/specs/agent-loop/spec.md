## MODIFIED Requirements

### Requirement: LocateEvent emission on cache actions

When `loop()` is called with `locator_cache` AND `trace_writer` AND `run_id`, the loop SHALL emit exactly one `LocateEvent` per cache action taken inside `_locate_with_supervisor`. Emission SHALL use a strictly-increasing `seq` allocated via `trace_writer.next_seq(run_id)` and SHALL populate `intent`, `tier`, `outcome`, `cache_action`, `chosen`, and **`step_id`** according to the action taken.

The `step_id` SHALL be set to `f"{run_id}:step-{step_num}"` where `step_num` is the loop's current 1-indexed step counter. The `step_id` SHALL be threaded from `loop()` into `_dispatch`, from `_dispatch` into `_locate_with_supervisor`, and from `_locate_with_supervisor` into `_emit_locate_event`.

- `cache_action="read"` + `outcome="hit"` + `tier="cache"` when a cached entry's live fingerprint matches.
- `cache_action="invalidate"` + `outcome="miss"` + `tier="cache"` whenever `cache.invalidate(...)` is called.
- `cache_action="write"` + `outcome="hit"` + `tier=<resolved ladder tier>` whenever `cache.put(...)` is called after a fresh ladder resolve.
- The loop SHALL NOT emit a `LocateEvent` when `locator_cache is None` or when the ladder resolves without any cache interaction.

#### Scenario: Write event emitted on first resolve into an empty cache

- **GIVEN** an empty `LocatorCache` and a `TraceWriter` open on `run_id`
- **AND** the LLM emits `read(intent="Submit button")` for a v1 fixture page on step 2
- **WHEN** the locate call resolves through the L1/L2 ladder and writes to the cache
- **THEN** exactly one `LocateEvent` row SHALL be appended with `cache_action="write"`, `outcome="hit"`, `intent="Submit button"`, `tier` equal to the ladder tier that resolved the element, **and `step_id` equal to `f"{run_id}:step-2"`**

#### Scenario: Invalidate event emitted before write on drift

- **GIVEN** a shared `LocatorCache` warmed from a v1 run
- **AND** a fresh `TraceWriter` and `run_id` for a second run on the v2 fixture page
- **WHEN** the locate call probes the cache, finds a fingerprint mismatch, invalidates, then resolves freshly through the ladder
- **THEN** the trace for the v2 run SHALL contain a `LocateEvent` row with `cache_action="invalidate"` whose `seq` is strictly less than that of a subsequent `LocateEvent` row with `cache_action="write"`
- **AND** both rows SHALL have the same `step_id` (the step that triggered the locate call)

#### Scenario: No emission without trace_writer + run_id

- **GIVEN** `loop()` is called with `locator_cache` provided but no `trace_writer` or `run_id`
- **WHEN** the loop dispatches `read` calls that interact with the cache
- **THEN** no `LocateEvent` rows SHALL be emitted (there is nowhere to write them) and the loop SHALL still function correctly

#### Scenario: LocateEvent step_id matches the step that triggered the locate call

- **GIVEN** `loop()` is called with `run_id="test-run"`, `locator_cache=<cache>`, and a `TraceWriter`
- **AND** the LLM emits `read(intent="Submit button")` on step 3
- **WHEN** the `LocateEvent` is emitted for the cache action
- **THEN** the `LocateEvent.step_id` SHALL equal `"test-run:step-3"`
