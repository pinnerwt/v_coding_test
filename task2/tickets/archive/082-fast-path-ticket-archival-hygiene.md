---
id: 82
slug: fast-path-ticket-archival-hygiene
status: archived
tier: 1
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/tickets/active/079-opsx-ff-artifact-template-cache.md
related:
- 76
- 79
filed_pr: null
merged_pr: 126
archived_at: '2026-04-29'
trigger: '`/full_task2` iteration 6 on 2026-04-29 — discovered ticket #79''s file is still in `task2/tickets/active/` with `merged_pr: null` and `archived_at: null` even though PR #122 merged on 2026-04-29 via the workflow-only fast path. The fast path skips `/done_pr`''s OpenSpec archive substep (no `openspec/changes/<change>/` exists) and never updates the ticket frontmatter or moves the file to `task2/tickets/archive/`. Every workflow-only PR going forward inherits this rot.'
---

82. **`/done_pr` workflow-only fast path needs to update ticket frontmatter and move the file to `task2/tickets/archive/` on merge.** The standard `/done_pr` flow archives the OpenSpec change directory via `mv openspec/changes/<change>/ openspec/changes/archive/<date>-<change>/` and depends on the ticket's `merged_pr` / `archived_at` frontmatter being updated as part of `openspec/changes/archive/<date>-*/proposal.md` citing the ticket number. The workflow-only fast path (added in `/new_task2` step 1a, expanded in `/full_task2` Phase 3) skips that substep entirely because there is no change directory to archive. Result: workflow-only tickets land their PR but never have their ticket file marked as merged or moved to `task2/tickets/archive/`. Confirmed in PR #122 (ticket #79): merged 2026-04-29, but `task2/tickets/active/079-opsx-ff-artifact-template-cache.md` still has `merged_pr: null`, `archived_at: null`, and lives under `active/`. The cross-cutting "is this ticket merged?" filter in `/new_task2` step 2a falls through to the GitHub PR-search check, which works — but the `task2/tickets/INDEX.md` Active section gets longer monotonically until someone manually cleans up. **Concrete fix:** in `/done_pr`'s workflow-only fast path (the branch that runs `gh pr merge "$pr_url" --squash --delete-branch` directly without invoking `/opsx:archive`), add three steps after the merge succeeds: (1) parse the merged PR title for a trailing `(#NN)` pattern to extract the ticket number; (2) edit `task2/tickets/active/<NNN>-<slug>.md`'s frontmatter to set `merged_pr: <PR-number>` and `archived_at: <ISO-date>`; (3) `git mv` the file to `task2/tickets/archive/<NNN>-<slug>.md`; (4) run `task2/scripts/regen_tickets_index.py` to refresh INDEX.md; (5) commit as `docs(task2): archive ticket #<NN>` on master (since master is branch-protected, this needs to be its own `chore/archive-ticket-<NN>` branch + small PR + auto-merge — same pattern as the `chore(skills): lessons` PRs in `/auto_task2`). **Tests:** end-to-end is hard to fixture, but a unit test on `task2/scripts/archive_workflow_only_ticket.py` (a new helper module) — given a ticket slug + PR number + date, asserting it: edits the YAML frontmatter idempotently, performs the `git mv`, regenerates INDEX.md, and a stub-test verifying the function rejects invalid input (missing ticket file, mismatched ticket-number-in-filename vs argument). **Acceptance:** when the next workflow-only PR merges via `/full_task2`, the ticket file is archived automatically and the next iteration's `/new_task2` step 1's INDEX.md scan does NOT show that ticket as active. *Why useful:* without this, every chore/skills- PR going through `/auto_task2` permanently bloats the active-ticket list. The fast path was added in PR #112 specifically to make workflow-only tickets cheap to land — leaving the bookkeeping side broken half-defeats the saving. Also: PR #122 (#79) and PR #124 (#80) both need retroactive cleanup once this ticket lands — done as a separate `chore/archive-tickets-79-and-80` PR after the helper exists. *Risks:* (a) a malformed PR title that doesn't end in `(#NN)` would skip the archive step silently — mitigation is to log a warning when the parse fails so the user can re-run manually; (b) ticket-file frontmatter format drift (a new required field added in a future migration like #76's plan-to-tickets one) could break the YAML edit — mitigation is to use `pyyaml` round-trip, not `sed`. *Trigger:* `/full_task2` iteration 6 on 2026-04-29 — discovered #79's file is still in active/ with stale frontmatter even though PR #122 merged.
