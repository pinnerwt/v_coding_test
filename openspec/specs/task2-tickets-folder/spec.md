# task2-tickets-folder Specification

## Purpose

Per-file ticket layout under `task2/tickets/{active,archive}/` with YAML frontmatter, replacing the monolithic `task2/plan.md`. `task2/tickets/INDEX.md` is the strict source of truth for selection-time data consumed by `/new_task2`, `/done_pr`, and `/review_task2`.

## Requirements

### Requirement: Per-ticket frontmatter schema is the canonical record
Every file under `task2/tickets/active/` and `task2/tickets/archive/` SHALL begin with a YAML frontmatter block delimited by `---` lines containing all of the following fields: `id` (int), `slug` (kebab-case string), `status` (one of `active`, `in-flight`, `merged`, `archived`, `dropped`), `tier` (int, 1–6 inclusive, where 1=process/standards, 2=measurement, 3=stop-the-bleeding, 4=diagnostic-unblocker, 5=benchmark-impact, 6=hygiene), `urgency` (one of `P0`, `P1`, `P2`, `P3`), `axes` (mapping with three integer sub-fields: `pass_rate`, `tokens_pct`, `latency_pct` — all required, even when zero), `dependencies` (list of ints — ticket ids that must be merged before this ticket is selectable; empty list when none), `pre_flight_gates` (list of strings drawn from the known gate vocabulary: `no-other-task2-prs-open`, `qwen-reachable`, `no-benchmark-in-flight`; empty list when none), `evidence` (list of relative paths; empty list when none), `related` (list of ints; empty list when none), `filed_pr` (int), `merged_pr` (int or null), `archived_at` (ISO-8601 date string or null), `trigger` (non-empty string; ideally cites the date and workflow event that surfaced the ticket, but legacy tickets migrated from `task2/plan.md` may fall back to the ticket title). The file path SHALL follow the pattern `task2/tickets/<folder>/<NNN>-<slug>.md` where `<NNN>` is the zero-padded id (minimum 3 digits) and `<folder>` is `active` for status `active` or `in-flight`, and `archive` for status `merged`, `archived`, or `dropped`.

#### Scenario: Active ticket file has all required frontmatter fields
- **WHEN** `task2/tests/test_tickets_index.py` parses every file under `task2/tickets/active/`
- **THEN** each file SHALL have all 14 required frontmatter fields present with values matching their declared types and allowed values

#### Scenario: Archive ticket file has all required frontmatter fields
- **WHEN** `task2/tests/test_tickets_index.py` parses every file under `task2/tickets/archive/`
- **THEN** each file SHALL have all 14 required frontmatter fields present, `merged_pr` SHALL be an int or null, and `archived_at` SHALL be a non-null ISO-8601 date string

#### Scenario: axes block always has all three numeric sub-fields
- **WHEN** `test_tickets_index.py` reads the `axes` frontmatter of any ticket file
- **THEN** `axes.pass_rate`, `axes.tokens_pct`, and `axes.latency_pct` SHALL each be present as integers, even when all are zero

#### Scenario: tier is within allowed range
- **WHEN** `test_tickets_index.py` reads the `tier` field of any ticket file
- **THEN** `tier` SHALL be an integer in the range 1–6 inclusive

#### Scenario: dependencies is a list of ints
- **WHEN** `test_tickets_index.py` reads the `dependencies` field of any ticket file
- **THEN** `dependencies` SHALL be a list (possibly empty) where every element is an integer

#### Scenario: pre_flight_gates only contains known gate identifiers
- **WHEN** `test_tickets_index.py` reads the `pre_flight_gates` field of any ticket file
- **THEN** every string in `pre_flight_gates` SHALL be one of `no-other-task2-prs-open`, `qwen-reachable`, `no-benchmark-in-flight`

### Requirement: INDEX.md is the strict source of truth for selection-time data
`task2/tickets/INDEX.md` SHALL contain one row per ticket (both active and archive sections) with at minimum: `id`, `urgency`, `tier`, `axes.pass_rate`, `axes.tokens_pct`, `axes.latency_pct`, `dependencies`, `pre_flight_gates`, a one-line summary, and the relative file path. `test_tickets_index.py` SHALL assert that for every ticket file on disk the INDEX.md row for that ticket reflects the same `id`, `urgency`, `tier`, `axes`, `dependencies`, and `pre_flight_gates` values as the file's frontmatter — the index cannot silently drift from the canonical source.

#### Scenario: INDEX.md row mirrors frontmatter for an active ticket
- **WHEN** `test_tickets_index.py` reads both `task2/tickets/INDEX.md` and an active ticket's frontmatter
- **THEN** the id, urgency, tier, axes (all three sub-fields), dependencies, and pre_flight_gates in the INDEX.md row SHALL exactly match the corresponding frontmatter values

#### Scenario: INDEX.md row mirrors frontmatter for an archived ticket
- **WHEN** `test_tickets_index.py` reads both `task2/tickets/INDEX.md` and an archived ticket's frontmatter
- **THEN** the id, urgency, tier, axes, dependencies, and pre_flight_gates in the INDEX.md row SHALL exactly match the corresponding frontmatter values

#### Scenario: INDEX.md update does not remove any ticket
- **WHEN** `regen_tickets_index.py` is run after adding a new ticket file
- **THEN** the resulting INDEX.md SHALL contain one row per ticket file on disk with no omissions

### Requirement: Active vs archive directory layout
Ticket files under `task2/tickets/active/` SHALL have `status` ∈ `{active, in-flight}`. Ticket files under `task2/tickets/archive/` SHALL have `status` ∈ `{merged, archived, dropped}`. No ticket file with `status: active` or `status: in-flight` SHALL exist under `archive/`, and no ticket file with `status: merged`, `status: archived`, or `status: dropped` SHALL exist under `active/`. The file naming convention is `<NNN>-<slug>.md` where `<NNN>` is the id zero-padded to at least 3 digits.

#### Scenario: Active ticket placed in active subdirectory
- **WHEN** a ticket with `status: active` exists on disk
- **THEN** its file path SHALL be `task2/tickets/active/<NNN>-<slug>.md`

#### Scenario: Archived ticket placed in archive subdirectory
- **WHEN** a ticket with `status: archived` exists on disk
- **THEN** its file path SHALL be `task2/tickets/archive/<NNN>-<slug>.md`

#### Scenario: No status/directory mismatch
- **WHEN** `test_tickets_index.py` checks every ticket file
- **THEN** no file under `active/` SHALL have status `merged`, `archived`, or `dropped`, and no file under `archive/` SHALL have status `active` or `in-flight`

### Requirement: regen_tickets_index.py is idempotent
`task2/scripts/regen_tickets_index.py` SHALL regenerate `task2/tickets/INDEX.md` deterministically from the current ticket files on disk: active section sorted ascending by id, archive section sorted ascending by archived_at. Running the script twice in a row SHALL produce zero diff between the two outputs.

#### Scenario: Two consecutive regen runs produce zero diff
- **WHEN** `regen_tickets_index.py` is run once producing INDEX.md, then run a second time
- **THEN** the second run SHALL produce byte-identical output (no diff)

#### Scenario: regen after adding a ticket reflects the new entry
- **WHEN** a new ticket file is added to `task2/tickets/active/` and `regen_tickets_index.py` is run
- **THEN** INDEX.md SHALL contain a row for the new ticket matching its frontmatter

### Requirement: Migration script preserves ticket count
`task2/scripts/migrate_plan_to_tickets.py` SHALL parse `task2/plan.md`, emit one ticket file per ticket found, and assert as a postcondition that the count of files emitted equals the count of tickets parsed from the source. If the counts differ the script SHALL exit non-zero and print a diagnostic. The test for this requirement SHALL invoke the script against the pre-migration plan.md and assert the emitted file count matches `grep -c '^[0-9]\+\. \*\*' task2/plan.md`.

#### Scenario: Migration produces one file per ticket
- **WHEN** `migrate_plan_to_tickets.py` is run against the current `task2/plan.md`
- **THEN** the total count of files written under `task2/tickets/active/` and `task2/tickets/archive/` SHALL equal the number of ticket entries detected in `task2/plan.md` by `grep -c '^[0-9]\+\. \*\*'`

#### Scenario: Migration asserts count at exit
- **WHEN** the parsed count differs from the emitted file count
- **THEN** the script SHALL exit with a non-zero return code and a diagnostic message naming the mismatch

#### Scenario: Archived OpenSpec changes produce archive ticket files with archived_at populated
- **WHEN** `migrate_plan_to_tickets.py` runs and finds `openspec/changes/archive/*/proposal.md` files whose body cites `ticket #N`
- **THEN** `task2/tickets/archive/<NNN>-*.md` for that ticket SHALL have `status: archived` and a non-null ISO-8601 `archived_at` string. `merged_pr` MAY be null when no PR can be cross-referenced from `openspec/changes/archive/` or `git log`

### Requirement: Skill consumer contract — what each skill reads and writes
`/new_task2` step 1 SHALL read only `task2/tickets/INDEX.md` to score and select a candidate ticket; it SHALL NOT read `task2/plan.md` or scan all ticket files. After selection, step 1 SHALL page in the selected ticket's file for full body. `/new_task2` step 11 SHALL write a new ticket file under `task2/tickets/active/` with all required frontmatter fields populated, then run `task2/scripts/regen_tickets_index.py` to update INDEX.md. `/done_pr` step 1b and step 1b' SHALL grep `task2/tickets/active/` (not `task2/plan.md`) to find the ticket being archived. `/done_pr` step 1c SHALL `git mv` the ticket file from `active/` to `archive/`, update `status`, `merged_pr`, and `archived_at` in the frontmatter in-place, and run `regen_tickets_index.py` — producing one commit instead of two. `/review_task2` step 3 SHALL grep `task2/tickets/active/` for cross-check purposes.

#### Scenario: /new_task2 step 1 reads INDEX.md only at scoring time
- **WHEN** `/new_task2` step 1 runs to score and rank candidate tickets
- **THEN** it SHALL read `task2/tickets/INDEX.md` (and optionally the selected ticket file after selection) and SHALL NOT read `task2/plan.md`

#### Scenario: /done_pr step 1c archives a ticket in one commit
- **WHEN** `/done_pr` step 1c runs for a merged PR whose ticket is `task2/tickets/active/<NNN>-<slug>.md`
- **THEN** it SHALL `git mv` that file to `task2/tickets/archive/<NNN>-<slug>.md`, update `status: archived`, `merged_pr`, `archived_at` in the frontmatter, run `regen_tickets_index.py`, and commit all changes in a single commit

#### Scenario: /new_task2 step 11 writes a ticket file and regens INDEX.md
- **WHEN** `/new_task2` step 11 files a new ticket
- **THEN** it SHALL create `task2/tickets/active/<NNN>-<slug>.md` with all required frontmatter fields and run `regen_tickets_index.py` to update INDEX.md

### Requirement: plan.md collapses to a stub
`task2/plan.md` SHALL contain only a short redirect stub after migration, pointing readers to `task2/tickets/INDEX.md` for the live ticket list and to `task2/PLAN.md` for the architectural notes. `task2/PLAN.md` SHALL be a new static doc containing the sections previously in `task2/plan.md` that are not ticket prose (`## Honest risks / tradeoffs`, architectural notes, etc.). The prose preamble sections SHALL NOT remain in `task2/plan.md`.

#### Scenario: plan.md is a stub after migration
- **WHEN** the migration is complete and plan.md is inspected
- **THEN** plan.md SHALL contain a redirect to `task2/tickets/INDEX.md` and SHALL NOT contain the `## TDD tickets`, `## Benchmark improvements (candidates)`, or `## Undone` sections

#### Scenario: PLAN.md contains extracted architectural notes
- **WHEN** `task2/PLAN.md` is inspected after migration
- **THEN** it SHALL contain the `## Honest risks / tradeoffs` section (and any other non-ticket architectural prose) previously found in `task2/plan.md`

### Requirement: Dependency edges resolve to existing ticket files
The sync test SHALL assert that for every id listed in any ticket's `dependencies:` frontmatter field, a ticket file exists on disk with that id in either `task2/tickets/active/` or `task2/tickets/archive/`. A dependency on an archived or merged ticket SHALL be allowed (it does not block selection, but also does not fail the test). A dependency on an id with no matching file SHALL cause the test to fail.

#### Scenario: Known dependency id resolves to a ticket file
- **WHEN** `test_tickets_index.py` reads a ticket whose `dependencies: [42]`
- **THEN** a file `task2/tickets/active/042-*.md` OR `task2/tickets/archive/042-*.md` SHALL exist on disk; otherwise the test SHALL fail with a message naming the dangling reference

#### Scenario: Empty dependencies list always passes
- **WHEN** `test_tickets_index.py` reads a ticket with `dependencies: []`
- **THEN** no dependency-resolution check is performed and the test passes for that field
