## 1. Red — Write failing tests for migration script

- [ ] 1.1 In `task2/tests/`, create `test_migrate_plan_to_tickets.py`. Add test `test_migration_count_matches_plan_md`: run `task2/scripts/migrate_plan_to_tickets.py` in a tmp directory (copy plan.md in), count emitted files, assert equals `grep -c '^[0-9]\+\. \*\*' task2/plan.md`.
- [ ] 1.2 Add test `test_archived_changes_produce_archive_ticket_with_merged_pr`: for each `openspec/changes/archive/*/proposal.md` that cites `ticket #N`, assert that after migration `task2/tickets/archive/` contains a file for ticket N with non-null `merged_pr` integer.
- [ ] 1.3 Run `uv run pytest task2/tests/test_migrate_plan_to_tickets.py -x` — confirm tests fail red (script does not exist yet).

## 2. Green — Write and run migration script

- [ ] 2.1 Create `task2/scripts/migrate_plan_to_tickets.py` (~150 LOC). Parse plan.md ticket entries with regex `^(\d+)\.\s+\*\*(.+?)\*\*`. For each ticket: extract body, cross-reference urgency from `## Undone` rubric, cross-reference merged status from `openspec/changes/archive/*/proposal.md` (grep `ticket #<N>`), cross-reference merge SHA from `git log --oneline --grep '#<N>\b'`. Emit `task2/tickets/active/<NNN>-<slug>.md` or `task2/tickets/archive/<NNN>-<slug>.md` with full frontmatter. Assert postcondition `pre_count == post_count`; exit non-zero on mismatch.
- [ ] 2.2 Run `uv run pytest task2/tests/test_migrate_plan_to_tickets.py -x` — confirm both tests pass green.
- [ ] 2.3 Run the migration script for real: `uv run python task2/scripts/migrate_plan_to_tickets.py` — inspect output under `task2/tickets/`. Verify count matches, spot-check 3–5 ticket files for correct frontmatter.
- [ ] 2.4 Stage and commit all emitted ticket files: `git add task2/tickets/active/ task2/tickets/archive/`.

## 3. Red — Write failing tests for index regen script

- [ ] 3.1 In `task2/tests/`, create or extend to include idempotency test `test_regen_tickets_index_idempotent`: run `regen_tickets_index.py`, capture INDEX.md content; run again, assert zero diff.
- [ ] 3.2 Run the test — confirm it fails red (script does not exist yet).

## 4. Green — Write regen script and seed INDEX.md

- [ ] 4.1 Create `task2/scripts/regen_tickets_index.py` (~80 LOC). Read all `task2/tickets/active/*.md` and `task2/tickets/archive/*.md` frontmatter using PyYAML. Write `task2/tickets/INDEX.md` with: active section sorted ascending by id, archive section sorted ascending by archived_at. Include columns: id, urgency, tier, axes (pass_rate/tokens_pct/latency_pct), dependencies, pre_flight_gates, one-line summary, file path.
- [ ] 4.2 Run `uv run python task2/scripts/regen_tickets_index.py` to produce `task2/tickets/INDEX.md`.
- [ ] 4.3 Run `uv run pytest task2/tests/test_migrate_plan_to_tickets.py -x` — confirm idempotency test passes green.
- [ ] 4.4 Run full test suite `uv run pytest task2/` — confirm no regressions.

## 5. Red — Write failing sync test

- [ ] 5.1 Create `task2/tests/test_tickets_index.py`. Add assertions (all initially red before ticket files exist with correct data):
  - Schema: every active and archive file has all 14 required frontmatter fields; `axes` has all three numeric sub-fields; `tier ∈ {1..6}`; `dependencies` is a list of ints; `pre_flight_gates` only contains known gate vocabulary.
  - Index mirrors frontmatter: for every ticket file, INDEX.md row matches id, urgency, tier, axes, dependencies, pre_flight_gates.
  - Directory/status consistency: no active file has archived status; no archive file has active status.
  - Dependency resolution: every id in any `dependencies` list resolves to an existing ticket file (active or archive).
- [ ] 5.2 Run `uv run pytest task2/tests/test_tickets_index.py -x` — confirm tests fail red (frontmatter fields may be incomplete or INDEX.md not yet seeded correctly).

## 6. Green — Fix frontmatter and regen to satisfy sync test

- [ ] 6.1 Inspect test failures; patch any ticket files where frontmatter is incomplete or incorrect (e.g., missing `axes` sub-fields, wrong `pre_flight_gates` values, status/directory mismatch).
- [ ] 6.2 Run `uv run python task2/scripts/regen_tickets_index.py` to update INDEX.md after any frontmatter fixes.
- [ ] 6.3 Run `uv run pytest task2/tests/test_tickets_index.py -x` — confirm all assertions pass green.
- [ ] 6.4 Run full test suite `uv run pytest task2/` — confirm no regressions.

## 7. Collapse plan.md and extract PLAN.md

- [ ] 7.1 Copy the prose preamble sections from `task2/plan.md` (`## Honest risks / tradeoffs`, architectural notes, component descriptions — everything that is NOT ticket prose) into a new file `task2/PLAN.md`.
- [ ] 7.2 Replace `task2/plan.md` with a stub containing a redirect to `task2/tickets/INDEX.md` and `task2/PLAN.md`. The stub SHALL NOT contain `## TDD tickets`, `## Benchmark improvements (candidates)`, or `## Undone` sections.
- [ ] 7.3 Run `uv run pytest task2/` — confirm no regressions.

## 8. Skill updates — update .claude/commands/ in lockstep

- [ ] 8.1 Edit `.claude/commands/new_task2.md` step 1: replace "read task2/plan.md" with "read task2/tickets/INDEX.md; parse axes, tier, urgency, dependencies, pre_flight_gates, one-line summary; score and rank candidates; page in selected ticket file for full body".
- [ ] 8.2 Edit `.claude/commands/new_task2.md` step 11: replace "append ticket prose to task2/plan.md" with "write new ticket file at `task2/tickets/active/<NNN>-<slug>.md` with all required frontmatter; run `uv run python task2/scripts/regen_tickets_index.py`".
- [ ] 8.3 Edit `.claude/commands/done_pr.md` steps 1b and 1b': replace `grep task2/plan.md` with `grep task2/tickets/active/` when finding the current ticket for archival.
- [ ] 8.4 Edit `.claude/commands/done_pr.md` step 1c: replace the two-commit pattern (plan.md edit + archival note) with: `git mv task2/tickets/active/<NNN>-<slug>.md task2/tickets/archive/<NNN>-<slug>.md`; update `status: archived`, `merged_pr`, `archived_at` in the moved file's frontmatter; run `uv run python task2/scripts/regen_tickets_index.py`; commit all in one commit.
- [ ] 8.5 Edit `.claude/commands/review_task2.md` step 3: replace cross-check grep target from `task2/plan.md` to `task2/tickets/active/`.
- [ ] 8.6 Verify each edited skill file opens and reads cleanly. Run `uv run pytest task2/` — confirm no regressions.

## 9. Documentation

- [ ] 9.1 Write `task2/tickets/README.md` documenting: the full frontmatter schema with field types and allowed values; the skill consumer contract (what each skill reads/writes and when); how to run `regen_tickets_index.py` manually; the pre-flight gate vocabulary.

## 10. Lint, format, final sweep

- [ ] 10.1 Run `uv run ruff check task2/scripts/migrate_plan_to_tickets.py task2/scripts/regen_tickets_index.py task2/tests/test_migrate_plan_to_tickets.py task2/tests/test_tickets_index.py` — fix any issues.
- [ ] 10.2 Run `uv run ruff format task2/scripts/ task2/tests/` — apply formatting.
- [ ] 10.3 Run `uv run ruff check task2/` — confirm exits clean.
- [ ] 10.4 Final sweep: run `grep -rn 'task2/plan.md\|## Undone\|## TDD tickets\|## Benchmark improvements' .claude/` — ensure every hit is either the updated skill file or an intentional retention (document any intentional retentions in a comment).
- [ ] 10.5 Run `uv run pytest task2/` one final time — all green.
- [ ] 10.6 Confirm `git diff task2/plan.md` shows a stub (not the full monolith), `task2/PLAN.md` exists, and `task2/tickets/` has the expected directory structure.
