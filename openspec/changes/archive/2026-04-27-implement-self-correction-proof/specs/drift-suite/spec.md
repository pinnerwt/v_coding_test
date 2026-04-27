## ADDED Requirements

### Requirement: drift/rename fixture pair for cache-invalidation proof

The repository SHALL include two HTML fixture files under `task2/tests/fixtures/drift/rename/`:

- `v1/index.html` — a minimal HTML page containing `<button>Submit</button>`. The button has accessible name "Submit" so L1 resolves it and `locate()` writes a cache entry with an AX fingerprint computed from `"button:Submit"`.
- `v2/index.html` — the same page where the button text has changed to `<button>Send</button>`. The selector written by v1 still resolves to one element on v2's DOM, but the AX fingerprint differs (accessible name is now "Send" not "Submit"). When `locate()` probes the cache with the v1 entry, it detects the fingerprint mismatch, calls `cache.invalidate()`, and falls through to L1 to resolve fresh.

Both files SHALL be static HTML served without any server-side processing.

#### Scenario: drift/rename/v1 fixture has accessible button "Submit"

- **WHEN** `task2/tests/fixtures/drift/rename/v1/index.html` is loaded
- **THEN** `page.get_by_role("button", name="Submit", exact=False).count()` SHALL equal `1`

#### Scenario: drift/rename/v2 fixture has accessible button "Send" (not "Submit")

- **WHEN** `task2/tests/fixtures/drift/rename/v2/index.html` is loaded
- **THEN** `page.get_by_role("button", name="Send", exact=False).count()` SHALL equal `1`
- **AND** `page.get_by_role("button", name="Submit", exact=False).count()` SHALL equal `0`

#### Scenario: Warm cache from v1 is invalidated when locate runs against v2

- **GIVEN** a `LocatorCache(path=":memory:")` warmed by `locate(v1_page, "Submit button", cache=cache)`
- **WHEN** `locate(v2_page, "Submit button", cache=cache)` is called
- **THEN** `cache.get(origin=..., intent="Submit button")` SHALL return `None` after the call (the v1 entry was invalidated)
- **AND** the call SHALL return a fresh `LocateResult` (not `tier="cache"`)
