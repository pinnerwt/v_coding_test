## Context

`/full_task2` Phase 3 has two branches:

- **Standard path**: invokes `/done_pr <change-name>`, which archives the OpenSpec change directory. `/done_pr` step 1c then locates the ticket file by reading the change's `proposal.md` for a ticket reference, and archives it with a frontmatter edit + `git mv` + INDEX regen.
- **Workflow-only fast path**: runs `gh pr merge "$pr_url" --squash --delete-branch` directly. There is no `openspec/changes/<change>/` directory; `/done_pr` is never invoked; and `/done_pr`'s step 1c (the only place ticket archival happens today) never executes. The ticket file stays in `active/` indefinitely.

Confirmed instances: ticket #79 (`079-opsx-ff-artifact-template-cache.md`, PR #122) and ticket #80 (`080-opsx-ff-artifact-template-cache-part-2.md`, PR #124) both merged 2026-04-29 via the workflow-only path and remain in `active/` with stale frontmatter.

## Goals / Non-goals

**Goals:**
- Archive workflow-only tickets automatically after the corresponding PR merges.
- Keep `task2/tickets/INDEX.md` accurate without manual intervention.
- Cover the helper with pytest unit tests (TDD-required).

**Non-goals:**
- Changing the standard path's archival flow — it works correctly already.
- Retroactive cleanup of #79 and #80 in this change — handled as a follow-up PR once the helper exists.

## Decisions

### Helper location: `task2/scripts/`, not `.claude/skills/`

pytest is the mandatory test surface for production code. A function in `.claude/skills/` is unreachable from `uv run pytest`. The helper therefore lives in `task2/scripts/archive_workflow_only_ticket.py`, which pytest can import directly.

### pyyaml round-trip for frontmatter edits

`regen_tickets_index.py` already uses `yaml.safe_load` for parsing frontmatter. The helper uses the same approach: read the raw file, parse the YAML block between the two `---` delimiters, mutate the three fields (`status`, `merged_pr`, `archived_at`), and write back using `yaml.dump(..., allow_unicode=True, sort_keys=False)`. This preserves field ordering and quoting, and is resilient to future frontmatter field additions. `sed`/regex is ruled out because it is fragile against multi-line values and quoting variants.

### Helper API

```python
def archive_workflow_only_ticket(
    slug: str,
    ticket_number: int,
    pr_number: int,
    iso_date: str,
    repo_root: Path,
) -> None
```

- Raises `FileNotFoundError` if neither `active/<NNN>-<slug>.md` nor `archive/<NNN>-<slug>.md` exists.
- Raises `ValueError` if the filename's leading integer does not equal `ticket_number`.
- Is idempotent: if the file is already in `archive/` with matching `merged_pr`, returns without re-editing or re-moving.
- Uses `subprocess.run(["git", "mv", ...], check=True)` for the file move (git tracks the rename).
- Invokes `regen_tickets_index.py` via subprocess: `uv run python scripts/regen_tickets_index.py` run from `task2/` (resolves the pyyaml dependency correctly; same pattern as the subshell in `/done_pr` step 1c prose).

### Integration point: `full_task2/SKILL.md` Phase 3 workflow-only branch

The ticket's "Concrete fix" section names `/done_pr`'s workflow-only fast path, but `/done_pr` is **not invoked at all** on the workflow-only path — `/full_task2` Phase 3 runs `gh pr merge` directly. Patching `/done_pr` for a code path it never enters adds dead branch logic. The natural integration point is `/full_task2` Phase 3's workflow-only branch, immediately after `gh pr merge ... --squash --delete-branch` succeeds.

The 5-step post-merge sequence added to Phase 3:

1. Parse the merged PR's title for a trailing `(#NN)` pattern: `re.search(r'\(#(\d+)\)\s*$', pr_title)`. Source: `gh pr view "$pr_url" --json title -q .title` after merge (the PR stays queryable after merge by URL).
2. If parse fails (squash commit subject was rewritten), log a warning and skip — manual cleanup rather than fail the iteration.
3. Run: `(cd task2 && uv run python scripts/archive_workflow_only_ticket.py --slug <slug> --ticket-number <NN> --pr-number <PR-NN> --date <YYYY-MM-DD>)` where `<slug>` and `<NN>` come from the ticket selected in Phase 1, and `<YYYY-MM-DD>` is today's date (`date -I`).
4. Create branch `chore/archive-ticket-<NN>`, stage the modified ticket file and `INDEX.md`, commit `docs(task2): archive ticket #<NN> — <slug>`.
5. Push, open PR, auto-merge: `gh pr create ... && gh pr merge ... --squash --delete-branch --auto && git pull --ff-only`.

### Why a separate `chore/archive-ticket-<NN>` PR, not a direct push

`master` is branch-protected; direct `git push origin master` is rejected. This is the same constraint that drives the `chore/skills-lessons-<change>` PRs in `/auto_task2` step 5 — exact same shape (small commit, push to a `chore/*` branch, `gh pr create`, `gh pr merge --squash --delete-branch --auto`, `git pull --ff-only`). Prior art: `/auto_task2` step 5 and every `chore(skills):` PR in the repo history (PRs #112, #113, #114, etc.).

### PR-title parse resilience

GitHub squash-merge by default uses the PR title as the commit subject, which preserves the trailing `(#NN)` pattern. However, a human editing the squash subject in the merge dialog could strip it. When `re.search` returns `None`, the sequence logs:

```
full_task2 Phase 3: WARNING — could not parse ticket number from PR title "<title>"; skipping ticket archival. Run manually: (cd task2 && uv run python scripts/archive_workflow_only_ticket.py ...)
```

and continues to Phase 4 without failing the iteration. The warning message includes the manual invocation so cleanup is trivial.

## Risks / Alternatives

**Risk: frontmatter format drift.** A future migration (like #76's plan-to-tickets) could add new required fields. Mitigated by pyyaml round-trip — unknown fields are preserved verbatim; the helper only writes the three fields it knows about.

**Risk: helper invoked on standard-path PRs by mistake.** Mitigated by explicit invocation only inside the `is_workflow_only == true` branch of Phase 3. The standard path never reaches that branch.

**Alternative: patch `/done_pr` to add a workflow-only sub-branch.** Rejected. `/done_pr` is not invoked in the workflow-only path; adding logic there creates a dead code path with no test surface and no caller. The fix belongs where the merge actually happens.

**Alternative: shell out to the full `regen_tickets_index.py` script vs. importing its `regen()` function.** Chosen: shell out. The script sets up its own `REPO_ROOT` from `__file__`, which is correct when called from `task2/`. Importing requires replicating or parameterizing that path setup in the helper. Subshell is simpler and matches the pattern already in `/done_pr` step 1c prose.
