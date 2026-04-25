## ADDED Requirements

### Requirement: LocatorCache class and storage contract

The system SHALL provide `agent.locator_cache.LocatorCache` — a SQLite-backed cache for locator resolutions keyed by `(origin, intent)`. `LocatorCache` SHALL be constructible via `LocatorCache(*, path: str = ":memory:")`. The constructor SHALL open or create a SQLite database at `path` and SHALL create the `locator_cache` table on first use. The constructor SHALL NOT read environment variables, SHALL NOT consult any global registry, and SHALL NOT have any module-load-time side effects beyond importing `sqlite3` and `dataclasses`.

The `locator_cache` table SHALL have these columns:

- `origin TEXT NOT NULL`
- `intent TEXT NOT NULL`
- `role TEXT NOT NULL`
- `name TEXT` (nullable)
- `selector TEXT NOT NULL` (empty string permitted for `tier="L4_vision"` rows)
- `ax_fingerprint TEXT NOT NULL`
- `confidence REAL NOT NULL`
- `tier TEXT NOT NULL` (one of `"L1_ax"`, `"L2_dom"`, `"L3_rerank"`, `"L4_vision"`)
- `coords_x INTEGER` (nullable; populated when `tier="L4_vision"`)
- `coords_y INTEGER` (nullable; populated when `tier="L4_vision"`)
- `written_at_utc TEXT NOT NULL` (ISO-8601 UTC timestamp)

The primary key SHALL be `(origin, intent)`.

If the existing table's column set does not match the expected schema, `__init__` SHALL drop and recreate the table. There SHALL be no schema migration framework.

`LocatorCache` SHALL expose `close(self) -> None`, which closes the underlying connection idempotently. `LocatorCache` SHALL implement `__enter__` and `__exit__` so callers may use `with LocatorCache(path=...) as cache:`.

#### Scenario: Construct an in-memory cache

- **WHEN** code constructs `LocatorCache()` with no arguments
- **THEN** the construction SHALL succeed
- **AND** the underlying SQLite database SHALL be `:memory:`
- **AND** the `locator_cache` table SHALL exist with the columns specified above

#### Scenario: Construct a file-backed cache

- **GIVEN** a writable temporary file path `tmp_path/locator.sqlite`
- **WHEN** code constructs `LocatorCache(path=str(tmp_path / "locator.sqlite"))`
- **THEN** the construction SHALL succeed
- **AND** the file SHALL exist on disk after construction
- **AND** a second construction against the same path SHALL succeed and find the existing table without dropping any rows

#### Scenario: Schema mismatch drops and recreates the table

- **GIVEN** a SQLite file at `tmp_path/locator.sqlite` containing a table named `locator_cache` with a different column set (e.g. only `origin` and `intent`)
- **WHEN** code constructs `LocatorCache(path=...)` against that file
- **THEN** the construction SHALL succeed
- **AND** the resulting `locator_cache` table SHALL have the full expected column set
- **AND** any rows from the previous schema SHALL have been discarded

#### Scenario: Constructor has no environment-variable dependency

- **GIVEN** the environment variable `LOCATOR_CACHE_PATH` is set to some value
- **WHEN** code constructs `LocatorCache()` with no arguments
- **THEN** the underlying database SHALL be `:memory:` (the default)
- **AND** the value of `LOCATOR_CACHE_PATH` SHALL be ignored

### Requirement: CacheEntry dataclass shape

The system SHALL define `agent.locator_cache.CacheEntry` as a frozen dataclass with the fields `origin: str`, `intent: str`, `role: str`, `name: str | None`, `selector: str`, `ax_fingerprint: str`, `confidence: float`, `tier: str`, `coords: tuple[int, int] | None`, `written_at_utc: str`. The dataclass SHALL be frozen so cache state cannot be mutated after construction. `LocatorCache.get` SHALL return `CacheEntry | None`; `LocatorCache.put` SHALL accept a `CacheEntry`.

#### Scenario: CacheEntry round-trips through the cache

- **GIVEN** a `LocatorCache(path=":memory:")` and a `CacheEntry` with `origin="http://127.0.0.1:9000"`, `intent="Submit button"`, `role="button"`, `name="Submit"`, `selector='role=button[name="Submit" i]'`, `ax_fingerprint="abc123"`, `confidence=1.0`, `tier="L1_ax"`, `coords=None`, `written_at_utc="2026-04-25T12:00:00Z"`
- **WHEN** code invokes `cache.put(entry)` and then `cache.get(origin="http://127.0.0.1:9000", intent="Submit button")`
- **THEN** the returned `CacheEntry` SHALL be equal to the inserted entry
- **AND** the returned object SHALL be a new `CacheEntry` instance, not the same object

### Requirement: Cache get / put / invalidate operations

`LocatorCache.get(self, *, origin: str, intent: str) -> CacheEntry | None` SHALL look up a row by exact `(origin, intent)` match and return it as a `CacheEntry`, or `None` if no row exists. `LocatorCache.put(self, entry: CacheEntry) -> None` SHALL insert a new row OR replace an existing row at the same `(origin, intent)` key (`INSERT OR REPLACE` semantics). `LocatorCache.invalidate(self, *, origin: str, intent: str) -> None` SHALL delete the row at the given key; if no row exists, the call SHALL succeed silently.

All three methods SHALL commit their changes before returning so a subsequent `get` from the same connection sees the updated state.

#### Scenario: Get on an empty cache returns None

- **GIVEN** a freshly constructed `LocatorCache(path=":memory:")`
- **WHEN** code invokes `cache.get(origin="http://example.com", intent="Submit button")`
- **THEN** the call SHALL return `None`

#### Scenario: Put then get returns the entry

- **GIVEN** a `LocatorCache(path=":memory:")`
- **AND** a `CacheEntry` constructed for `origin="http://x", intent="Save button"`
- **WHEN** code invokes `cache.put(entry)` then `cache.get(origin="http://x", intent="Save button")`
- **THEN** the call SHALL return the same logical entry

#### Scenario: Put twice replaces the row

- **GIVEN** a `LocatorCache` containing a row for `(origin="http://x", intent="Save button")` with `selector="role=button[name=\"Save\" i]"`
- **WHEN** code invokes `cache.put(...)` again with the same `(origin, intent)` but a new `selector="role=button[name=\"Save\" i] >> nth=2"` and a new `ax_fingerprint`
- **THEN** the subsequent `cache.get(origin="http://x", intent="Save button")` SHALL return the newer entry
- **AND** the table SHALL contain exactly one row for that `(origin, intent)` pair

#### Scenario: Invalidate deletes the row

- **GIVEN** a `LocatorCache` containing a row for `(origin="http://x", intent="Save button")`
- **WHEN** code invokes `cache.invalidate(origin="http://x", intent="Save button")` and then `cache.get(...)` for the same key
- **THEN** the `get` call SHALL return `None`

#### Scenario: Invalidate on a missing row is a no-op

- **GIVEN** a freshly constructed `LocatorCache(path=":memory:")`
- **WHEN** code invokes `cache.invalidate(origin="http://x", intent="Save button")`
- **THEN** the call SHALL succeed without raising
- **AND** subsequent `get` calls for any key SHALL still return `None`

### Requirement: Cache scoping by origin and intent

The cache SHALL treat `(origin_a, intent_x)` and `(origin_b, intent_x)` as independent keys for any distinct origin pair. The cache SHALL treat `(origin_x, intent_a)` and `(origin_x, intent_b)` as independent keys for any distinct intent pair. Reads against one key SHALL NOT return rows written under the other key.

#### Scenario: Different origins do not share entries

- **GIVEN** a `LocatorCache` containing one row at `(origin="http://a:80", intent="Submit button")`
- **WHEN** code invokes `cache.get(origin="http://b:80", intent="Submit button")`
- **THEN** the call SHALL return `None`

#### Scenario: Different intents do not share entries

- **GIVEN** a `LocatorCache` containing one row at `(origin="http://x", intent="Submit button")`
- **WHEN** code invokes `cache.get(origin="http://x", intent="Cancel button")`
- **THEN** the call SHALL return `None`

### Requirement: Origin derivation from a Playwright page URL

The system SHALL provide an internal helper `agent.locator_cache._origin_from_url(url: str) -> str` (or equivalent name in the cache integration) that produces a canonical origin string from a URL. The canonical form SHALL be `scheme://host[:port]` where:

- `scheme` is lower-cased.
- `host` is lower-cased.
- The port suffix `:80` is stripped when `scheme == "http"`, the port suffix `:443` is stripped when `scheme == "https"`, and any other port is preserved as `:{port}`.

Two URLs that differ only in path, query, or fragment SHALL produce the same origin. Two URLs that differ in scheme, host, or non-default port SHALL produce different origins.

#### Scenario: HTTP URL with default port collapses to no port

- **WHEN** code derives an origin from `http://example.com/some/path?q=1#frag`
- **THEN** the origin SHALL equal `http://example.com`

#### Scenario: HTTPS URL with default port collapses to no port

- **WHEN** code derives an origin from `https://EXAMPLE.com:443/`
- **THEN** the origin SHALL equal `https://example.com`

#### Scenario: Non-default port is preserved

- **WHEN** code derives an origin from `http://127.0.0.1:9123/locate_l1.html`
- **THEN** the origin SHALL equal `http://127.0.0.1:9123`

#### Scenario: Path and query do not affect origin

- **WHEN** code derives origins from `http://x.test/a` and `http://x.test/b?q=1`
- **THEN** both origins SHALL equal `http://x.test`

### Requirement: Canonical AX fingerprint at write and revalidation time

When a `CacheEntry` is written for a row whose `tier` is one of `"L1_ax"`, `"L2_dom"`, `"L3_rerank"`, the `ax_fingerprint` column SHALL store the L1-style canonical fingerprint of the element the cached `selector` resolves to at write time, computed as `sha256(f"{role}:{accessible_name}".encode()).hexdigest()` where `accessible_name` is the result of running the existing accessible-name JS helper against the resolved element. On a subsequent read against a live page, the cache SHALL recompute the canonical fingerprint of the element the cached `selector` resolves to and SHALL compare it against `ax_fingerprint`. Equal fingerprints SHALL be treated as a cache hit. Different fingerprints SHALL be treated as a drift miss and SHALL invalidate the row.

L4 rows SHALL store `selector=""`; their `ax_fingerprint` value SHALL be the L4 vision fingerprint (`sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest()`). Their canonical revalidation rule is governed by the "L4 entries are forced-miss on read" requirement below.

#### Scenario: Canonical fingerprint matches across two resolves of the same element

- **GIVEN** a page with one accessible button named `Submit`
- **AND** a `LocatorCache` and an `agent.locate.locate(...)` resolution that wrote the cache row
- **WHEN** the test recomputes the canonical fingerprint of the resolved element via the cached selector
- **THEN** the recomputed fingerprint SHALL equal the stored `ax_fingerprint`

#### Scenario: Canonical fingerprint differs after the page mutates

- **GIVEN** a page with one accessible button named `Submit` and a cached row written for it
- **WHEN** the page is mutated so the same selector now resolves to an element whose accessible name is `Send`
- **THEN** the canonical fingerprint of the re-resolved element SHALL NOT equal the stored `ax_fingerprint`

### Requirement: L4 entries are written but forced-miss on read

When a successful resolution at tier `"L4_vision"` is cached, the row SHALL be written with `selector=""`, `coords=(cx, cy)`, and the L4 vision fingerprint stored in `ax_fingerprint`. On a subsequent cache probe, an `"L4_vision"` row SHALL ALWAYS be treated as a miss: the row SHALL be deleted via `invalidate` and the L1–L4 ladder SHALL run again. No vision LLM call SHALL be made during the cache probe itself.

This rule is intentional and documented: in-place AX-fingerprint revalidation is not possible for vision-derived entries without paying the same vision LLM cost the cache is meant to avoid. A future change MAY add a vision-revalidation strategy.

#### Scenario: L4 row is invalidated on read

- **GIVEN** a cache containing one row with `tier="L4_vision"` for `(origin, intent)`
- **AND** a page where the same intent would resolve via L1 if asked again
- **WHEN** the cache integration in `locate()` probes the cache for that `(origin, intent)`
- **THEN** the row SHALL be deleted from the cache before the L1–L4 ladder runs
- **AND** no vision LLM call SHALL be made during the probe

#### Scenario: L4 row write is preserved when no read intervenes

- **GIVEN** a cache and a successful L4 resolve via `locate()`
- **WHEN** the test inspects the cache via `get(origin=..., intent=...)` immediately after the resolve, *without* calling `locate()` again
- **THEN** the `CacheEntry` SHALL exist with `tier="L4_vision"` and `selector=""` and `coords=(cx, cy)`
