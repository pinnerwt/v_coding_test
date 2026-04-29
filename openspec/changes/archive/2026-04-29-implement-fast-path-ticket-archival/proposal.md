## Why

The workflow-only fast path (`chore/skills-*` PRs merged by `/full_task2` Phase 3 without invoking `/done_pr`) skips ticket archival because there is no `openspec/changes/<change>/` directory to anchor the standard `/opsx:archive` ride-along. Every workflow-only PR leaves its ticket file in `task2/tickets/active/` with `merged_pr: null` and `archived_at: null`, permanently bloating the active list and half-defeating the fast path's cost saving (confirmed: tickets #79 and #80 both landed via workflow-only merges and remain in `active/` as of 2026-04-29).

## What Changes

- Introduce `task2/scripts/archive_workflow_only_ticket.py` — a helper module that, given `(slug, ticket_number, pr_number, iso_date, repo_root)`, edits frontmatter (`merged_pr`, `archived_at`, `status`), `git mv`s the file from `task2/tickets/active/<NNN>-<slug>.md` to `task2/tickets/archive/<NNN>-<slug>.md`, and regenerates `task2/tickets/INDEX.md`.
- Update `.claude/skills/full_task2/SKILL.md` Phase 3 workflow-only branch with a 5-step post-merge sequence: parse PR title for `(#NN)`, invoke helper, commit on a `chore/archive-ticket-<NN>` branch, open small PR, auto-merge.
- Retroactively archive tickets #79 and #80 via a follow-up `chore/archive-tickets-79-and-80` PR after the helper lands (separate from this change).

## Capabilities

### New Capabilities

- `workflow-only-ticket-archival` — the helper module behavior (frontmatter edit + git mv + INDEX regen) and the post-merge integration contract in `/full_task2` Phase 3.

### Modified Capabilities

<!-- None: no existing capability requirement is changing. The skill prose in full_task2/SKILL.md is process documentation, not a spec requirement. -->

## Impact

- `task2/scripts/archive_workflow_only_ticket.py` — new
- `task2/tests/test_archive_workflow_only_ticket.py` — new
- `.claude/skills/full_task2/SKILL.md` — prose update (Phase 3 workflow-only branch)
- Follow-up cleanup PR: retroactively archive tickets #79 and #80
