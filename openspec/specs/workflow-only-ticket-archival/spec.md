# workflow-only-ticket-archival Specification

## Purpose
TBD - created by archiving change implement-fast-path-ticket-archival. Update Purpose after archive.
## Requirements
### Requirement: Archive workflow-only ticket frontmatter and location on merge

The system SHALL provide a helper function `archive_workflow_only_ticket(slug, ticket_number, pr_number, iso_date, repo_root)` in `task2/scripts/archive_workflow_only_ticket.py` that, given a workflow-only ticket's slug and metadata, edits the ticket file's frontmatter (`status`, `merged_pr`, `archived_at`), `git mv`s the file from `task2/tickets/active/<NNN>-<slug>.md` to `task2/tickets/archive/<NNN>-<slug>.md`, and regenerates `task2/tickets/INDEX.md`.

#### Scenario: Successful archival

- **GIVEN** a ticket file at `task2/tickets/active/<NNN>-<slug>.md` with `merged_pr: null` and `archived_at: null`
- **AND** the filename's leading integer equals `ticket_number`
- **WHEN** `archive_workflow_only_ticket(slug=<slug>, ticket_number=<NNN>, pr_number=<PR>, iso_date=<YYYY-MM-DD>, repo_root=<path>)` is called
- **THEN** the file is moved to `task2/tickets/archive/<NNN>-<slug>.md`
- **AND** the moved file's frontmatter has `merged_pr: <PR>`, `archived_at: <YYYY-MM-DD>`, and `status: archived`
- **AND** `task2/tickets/INDEX.md` is regenerated and no longer lists the ticket in the Active section

#### Scenario: Idempotent on already-archived ticket

- **GIVEN** a ticket file already at `task2/tickets/archive/<NNN>-<slug>.md` with `merged_pr: <PR>` and `archived_at: <YYYY-MM-DD>`
- **WHEN** `archive_workflow_only_ticket(slug=<slug>, ticket_number=<NNN>, pr_number=<PR>, iso_date=<YYYY-MM-DD>, repo_root=<path>)` is called
- **THEN** the call returns without raising an exception and without modifying the file or re-running `git mv`

### Requirement: Reject invalid archival inputs

The helper SHALL reject calls whose target file does not exist, whose filename's leading ticket number does not match the supplied `ticket_number` argument, or whose already-archived metadata conflicts with the supplied `pr_number` / `iso_date`.

#### Scenario: Missing ticket file

- **GIVEN** no file exists at `task2/tickets/active/<NNN>-<slug>.md` and no file exists at `task2/tickets/archive/<NNN>-<slug>.md`
- **WHEN** `archive_workflow_only_ticket(slug=<slug>, ticket_number=<NNN>, ...)` is called
- **THEN** `FileNotFoundError` is raised before any filesystem mutation occurs

#### Scenario: Mismatched ticket number in filename

- **GIVEN** a file `task2/tickets/active/082-fast-path-ticket-archival-hygiene.md` exists
- **WHEN** `archive_workflow_only_ticket(slug="fast-path-ticket-archival-hygiene", ticket_number=99, pr_number=125, iso_date="2026-04-29", repo_root=<path>)` is called
- **THEN** `ValueError` is raised before any filesystem mutation occurs

#### Scenario: Already archived with conflicting metadata

- **GIVEN** a ticket file at `task2/tickets/archive/<NNN>-<slug>.md` with `merged_pr: <PR-A>` and `archived_at: <DATE-A>`
- **WHEN** `archive_workflow_only_ticket(slug=<slug>, ticket_number=<NNN>, pr_number=<PR-B>, iso_date=<DATE-B>, ...)` is called with `<PR-B> != <PR-A>` or `<DATE-B> != <DATE-A>`
- **THEN** `ValueError` is raised before any filesystem mutation occurs
