## MODIFIED Requirements

### Requirement: Archive workflow-only ticket frontmatter and location on merge

The system SHALL provide a helper function `archive_workflow_only_ticket(slug, ticket_number, pr_number, iso_date, repo_root)` in `task2/scripts/archive_workflow_only_ticket.py` that, given a workflow-only ticket's slug and metadata, `git mv`s the file from `task2/tickets/active/<NNN>-<slug>.md` to `task2/tickets/archive/<NNN>-<slug>.md`, writes updated frontmatter (`status: archived`, `merged_pr: <PR>`, `archived_at: <YYYY-MM-DD>`) to the archive path, stages the content update via `git add`, and regenerates `task2/tickets/INDEX.md`. After the helper returns, both the rename and the frontmatter content update MUST be fully staged in the git index; no related unstaged modifications SHALL remain in the working tree.

#### Scenario: Successful archival

- **GIVEN** a ticket file at `task2/tickets/active/<NNN>-<slug>.md` with `merged_pr: null` and `archived_at: null`
- **AND** the filename's leading integer equals `ticket_number`
- **WHEN** `archive_workflow_only_ticket(slug=<slug>, ticket_number=<NNN>, pr_number=<PR>, iso_date=<YYYY-MM-DD>, repo_root=<path>)` is called
- **THEN** the file is moved to `task2/tickets/archive/<NNN>-<slug>.md`
- **AND** the moved file's frontmatter has `merged_pr: <PR>`, `archived_at: <YYYY-MM-DD>`, and `status: archived`
- **AND** `task2/tickets/INDEX.md` is regenerated and no longer lists the ticket in the Active section
- **AND** `git diff --staged --stat` from `repo_root` shows both the rename of the ticket file AND a content change at the archive path (frontmatter update)

#### Scenario: Archive leaves no unstaged modifications

- **GIVEN** a ticket file at `task2/tickets/active/<NNN>-<slug>.md` committed to the git index
- **WHEN** `archive_workflow_only_ticket(slug=<slug>, ticket_number=<NNN>, pr_number=<PR>, iso_date=<YYYY-MM-DD>, repo_root=<path>)` is called
- **THEN** `git diff --name-only` from `repo_root` returns no output for the archived file path — the working tree matches the index for that file

#### Scenario: Idempotent on already-archived ticket

- **GIVEN** a ticket file already at `task2/tickets/archive/<NNN>-<slug>.md` with `merged_pr: <PR>` and `archived_at: <YYYY-MM-DD>`
- **WHEN** `archive_workflow_only_ticket(slug=<slug>, ticket_number=<NNN>, pr_number=<PR>, iso_date=<YYYY-MM-DD>, repo_root=<path>)` is called
- **THEN** the call returns without raising an exception and without modifying the file or re-running `git mv`
