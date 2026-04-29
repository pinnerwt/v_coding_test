## Context

`task2/plan.md` is a ~415-line monolith housing 75+ tickets across three sections (`## TDD tickets`, `## Benchmark improvements (candidates)`, `## Undone` rubric). Every `/done_pr` run touches the file (1b grep, 1c status update), every `/new_task2` run reads the full ~7K token document to score three axes, and merge conflicts are routine (every recent task2 PR carries 1-3 plan.md-touching commits). The fix is structural: separate cold ticket bodies from hot selection-time metadata, and make the index the one file that must stay consistent.

## Goals / Non-Goals

**Goals:**

- Introduce `task2/tickets/{active,archive}/<NNN>-<slug>.md` per-ticket cold storage with mandatory YAML frontmatter.
- Introduce `task2/tickets/INDEX.md` as the strict source of truth for selection-time fields; enforce via sync test.
- Ship `task2/scripts/migrate_plan_to_tickets.py` (throwaway) and `task2/scripts/regen_tickets_index.py` (kept).
- Update `/new_task2`, `/done_pr`, `/review_task2` skill steps that currently read/write plan.md to use the new layout.
- Collapse `task2/plan.md` to a stub and extract prose preamble to `task2/PLAN.md`.
- Cover the invariant with `task2/tests/test_tickets_index.py`.

**Non-Goals:**

- Changing ticket content — bodies migrate verbatim; only frontmatter is added.
- Automating the cutover while other task2 PRs are open (enforced by pre-flight gate).
- Changing the three selection axes or the tier sort order used by `/new_task2`.
- Visual L2 fallback or any other non-#76 ticket work.

## Decisions

### D1 — INDEX.md as strict source of truth for selection-time fields

`/new_task2` step 1 reads INDEX.md only (id, urgency, tier, axes, one-line summary, file path). It pages in the per-ticket file only after selection. Per-ticket files are never scanned at selection time. The sync test (`test_tickets_index.py`) enforces that INDEX.md mirrors frontmatter for every entry — drift fails CI.

**Alternative considered:** scan all active/*.md frontmatter at selection time. Rejected: 75+ files × YAML parse = more I/O and more tokens than the monolith it replaces.

### D2 — Frontmatter schema is the canonical record per ticket

Every per-ticket file carries a YAML frontmatter block as the first thing in the file. All fields required by the schema MUST be present; the sync test asserts this on every active and archive file. Required fields: `id` (int), `slug` (kebab-case str), `status` ∈ `{active, in-flight, merged, archived, dropped}`, `tier` ∈ `{1,2,3,4,5,6}`, `urgency` ∈ `{P0,P1,P2,P3}`, `axes: {pass_rate: int, tokens_pct: int, latency_pct: int}`, `dependencies: [<id>, ...]`, `pre_flight_gates: [<gate>, ...]`, `evidence: [<path>, ...]`, `related: [<id>, ...]`, `filed_pr` (int), `merged_pr` (int|null), `archived_at` (ISO date|null), `trigger` (str).

The three initial known gate identifiers are `no-other-task2-prs-open`, `qwen-reachable`, `no-benchmark-in-flight`; the sync test validates against this vocabulary.

**Alternative considered:** a separate YAML sidecar per ticket. Rejected: two files per ticket doubles the file count and introduces a second sync surface.

### D3 — Active vs archive split mirrors git mv semantics

`task2/tickets/active/<NNN>-<slug>.md` → open/in-flight tickets.
`task2/tickets/archive/<NNN>-<slug>.md` → merged/dropped/archived tickets.

On merge, `/done_pr` step 1c runs `git mv active/<NNN>-*.md archive/`, updates three frontmatter fields (`status: archived`, `merged_pr`, `archived_at`) in-place, then runs `regen_tickets_index.py` — one atomic commit. This replaces the current two-commit pattern (plan.md edit + separate archival note).

### D4 — regen_tickets_index.py is idempotent and deterministic

The script reads every active/*.md and archive/*.md frontmatter, writes INDEX.md deterministically (active section sorted by id; archive section sorted chronologically by archived_at). Running it twice in a row produces zero diff. The sync test calls it twice and diffs the result to verify.

**Alternative considered:** append-only INDEX.md mutation. Rejected: append-only cannot handle re-ordering (e.g. urgent ticket added mid-list) and cannot be verified as idempotent.

### D5 — Migration script uses regex-parse, not markdown-AST

plan.md's ticket format (`^<NNN>. **<title>.**`) is stable enough for a targeted regex. An AST parser would be a heavier dependency for a throwaway script. Postcondition: `pre_count == post_count` asserted at the end of the script and covered by test (a).

Cross-referencing merged status: grep `openspec/changes/archive/*/proposal.md` for `ticket #<N>` to find which archived change covers a ticket; read its `merged_pr` field. Cross-reference the git log with `git log --oneline --grep '#<N>\b'` for the merge SHA.

### D6 — Skill updates described in tasks.md; .claude/ is off-limits to this subagent

The `.claude/commands/` files are updated by the implementer during task execution. tasks.md enumerates exactly which step in each skill changes and what the new behavior is. The artifact-generation subagent does not touch `.claude/`.

## Risks / Trade-offs

- [Migration script mis-parses oddly-formatted ticket] → Mitigation: postcondition `pre_count == post_count` assertion in the script; test (a) validates count. Any mis-parse shows up as a count mismatch before any file is committed.
- [Skill updates miss a code path in .claude/] → Mitigation: final-sweep task runs `grep -rn 'task2/plan.md\|## Undone\|## TDD tickets\|## Benchmark improvements' .claude/` and ensures every hit is either updated or intentionally retained.
- [In-flight task2 branches conflict during cutover] → Mitigation: `no-other-task2-prs-open` pre-flight gate enforced at start; `/auto_task2` must be paused for the cutover.
- [INDEX.md drifts from frontmatter silently] → Mitigation: `test_tickets_index.py` asserts INDEX.md mirrors frontmatter for every entry; this runs in CI.
- [Dangling dependency references] → Mitigation: sync test asserts every id in any ticket's `dependencies:` list resolves to an existing ticket file.

## Migration Plan

1. Write tests red-first (`test_migrate_plan_to_tickets.py`, `test_tickets_index.py`).
2. Write `migrate_plan_to_tickets.py`; run it once to seed `task2/tickets/`; commit output files.
3. Write `regen_tickets_index.py`; verify idempotency test goes green.
4. Confirm all sync-test assertions pass.
5. Collapse `task2/plan.md` to a stub; extract preamble to `task2/PLAN.md`.
6. Update `.claude/commands/new_task2.md`, `done_pr.md`, `review_task2.md` per tasks.md specs.
7. Write `task2/tickets/README.md`.
8. Final sweep: grep `.claude/` for old plan.md references; fix any misses.
9. Single PR with all of the above — must have no other task2 PRs open at merge time.

## Open Questions

None. Ticket #76 fully specifies the schema, layout, consumer contract, and test surface.
