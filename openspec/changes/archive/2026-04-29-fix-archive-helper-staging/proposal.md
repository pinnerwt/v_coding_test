## Why

`archive_workflow_only_ticket` writes updated frontmatter to the active path and then calls `git mv`, but `git mv` only re-stages the rename based on the INDEX entry (pre-write content), leaving the frontmatter edits as unstaged working-tree modifications. Every `/full_task2` iteration's archive commit therefore half-archives the ticket — the file moves but `status`/`merged_pr`/`archived_at` remain null in the index until a follow-up commit is added manually.

## What Changes

- Fix the git-staging order in `task2/scripts/archive_workflow_only_ticket.py`: call `git mv` first (stages the rename with old content), then write the new frontmatter text to `archive_path`, then call `git add <archive_path>` to stage the content update on top of the rename.
- Extend `task2/tests/test_archive_workflow_only_ticket.py::test_archives_ticket_successfully` to assert the staged diff includes both the rename AND the frontmatter content change (using a real `subprocess.run` for `git diff --staged --stat`, not a mock).
- Add `test_archives_ticket_stages_content_change`: after the helper runs, assert `git diff --name-only` (working-tree-vs-index) returns no entries for the archived file — i.e. working tree matches index.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `workflow-only-ticket-archival`: tighten the "Successful archival" scenario to require that both the rename AND the frontmatter content are staged in the index (not just present on disk); add a new scenario asserting no unstaged working-tree modifications for the archived file after the helper runs.

## Impact

- `task2/scripts/archive_workflow_only_ticket.py` — production fix (3 lines reordered + 1 `git add` call added)
- `task2/tests/test_archive_workflow_only_ticket.py` — two test-level additions; existing tests continue passing
- No dependency or API surface changes
