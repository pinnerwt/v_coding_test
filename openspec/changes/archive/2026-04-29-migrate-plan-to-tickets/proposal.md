## Why

`task2/plan.md` is a ~415-line monolith covering 75+ tickets that causes a merge conflict in every recent task2 PR and forces `/new_task2` step 1 to read ~7K tokens of prose per invocation just to score three selection-time axes. Splitting the ticket bodies into per-file cold storage and housing the selection-time metadata in a single `INDEX.md` cuts step-1 token cost by ~50% and makes archival a one-commit operation.

## What Changes

- New directory tree `task2/tickets/{active,archive}/` — one Markdown file per ticket with required YAML frontmatter (id, slug, status, tier, urgency, axes, dependencies, pre_flight_gates, evidence, related, filed_pr, merged_pr, archived_at, trigger).
- `task2/tickets/INDEX.md` — the strict source of truth for all fields `/new_task2` step 1 reads at selection time (id, urgency, axes, one-line summary, file path). Per-ticket files are cold storage paged in only on selection or grep.
- `task2/scripts/migrate_plan_to_tickets.py` (~150 LOC, throwaway one-shot) — regex-parses plan.md ticket bodies, cross-references urgency from `## Undone`, cross-references merged status from `openspec/changes/archive/*/proposal.md` and `git log`, emits per-ticket files; postcondition asserts pre_count == post_count.
- `task2/scripts/regen_tickets_index.py` (~80 LOC, kept) — reads all active/archive frontmatter, regenerates INDEX.md deterministically; idempotent.
- `task2/tickets/README.md` — schema reference + skill consumer contract.
- Skill updates in lockstep: `/new_task2` step 1 (read INDEX.md, parse axes, score), step 11 (write new ticket file + run regen), `/done_pr` step 1b/1b' (grep shifts to `task2/tickets/active/`), step 1c (`git mv` + frontmatter update + regen INDEX.md — one commit instead of two), `/review_task2` step 3 (cross-check greps `task2/tickets/active/`).
- `task2/plan.md` collapses to a stub redirecting to `task2/tickets/INDEX.md`; its prose preamble (`## Honest risks / tradeoffs`, architectural notes) extracts to `task2/PLAN.md` as a static doc.
- Sync test `task2/tests/test_tickets_index.py` — validates every required frontmatter field, asserts INDEX.md mirrors frontmatter for every entry, and asserts all dependency id references resolve to existing ticket files.
- Must run with no other task2 PRs open (enforced by `no-other-task2-prs-open` pre-flight gate).

## Capabilities

### New Capabilities

- `task2-tickets-folder`: Per-ticket file layout, frontmatter schema, INDEX.md source-of-truth invariant, migration and regen scripts, skill consumer contract, and sync test.

### Modified Capabilities

<!-- None: skills (.claude/commands/) are updated in tasks.md as implementation work but do not have an openspec spec file; their behavior change is covered under task2-tickets-folder's consumer-contract requirement. -->

## Impact

- `task2/scripts/migrate_plan_to_tickets.py` — new throwaway script.
- `task2/scripts/regen_tickets_index.py` — new kept script.
- `task2/tickets/` — new directory tree with 75+ ticket files + INDEX.md + README.md.
- `task2/tests/test_tickets_index.py` — new sync/schema test.
- `task2/plan.md` — collapses to a stub (existing file, major content removal).
- `task2/PLAN.md` — new static doc extracted from plan.md preamble.
- `.claude/commands/new_task2.md`, `done_pr.md`, `review_task2.md` — step-level edits (skill consumer contract update).
- No external API, dependency, or schema changes.
