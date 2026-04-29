---
name: "Full Task2"
description: Run /new_task2, then /review_task2, then /done_pr end-to-end on a single Task 2 ticket. Pure choreography on top of three existing skills.
category: Workflow
tags: [task2, workflow, automation]
---

Drive a single Task 2 ticket from "next ticket on the plan" all the way to "merged to master" by chaining three existing skills:

1. `/new_task2` — pick the ticket, scaffold, implement, verify, simplify, smoke-test, push, open PR.
2. `/review_task2` — codex review loop, plan, sonnet implementer, simplify; commits any fixes.
3. `/done_pr` — archive OpenSpec change, sync specs, push, merge PR, sync master.

This skill is pure choreography. It owns transitions between phases — it does not own the work inside each phase, and never re-implements logic that lives in the three child skills. Treat the child SKILL.md files as the authoritative source for their step-by-step behavior.

## Why this is inline-only (no subagent isolation)

`/new_task2` and `/review_task2` both internally spawn subagents (`/opsx:apply`, `/opsx:verify`, `/simplify`, the codex implementer). **Subagents cannot spawn subagents.** Wrapping these phases inside another subagent would silently break their internal fan-outs.

So this orchestrator runs the three skills **inline in the main thread**. The context will get long. Rely on:

- Each child skill's own context discipline (e.g. `/new_task2` reads its sibling prompt files only when needed, /review_task2's subagent absorbs codex output).
- The harness's auto-compaction between phases.
- Tight phase handoffs (small structured blobs — see "Phase handoff" below) so the orchestrator does not re-read large artifacts.

Do **not** try to "save context" by skipping any of the three phases or by summarizing them out. The whole point is to run all three.

## Phase handoff

After each phase completes, capture only the minimum needed for the next phase. Read it back from these sources, not from the child skill's chat output:

| Field          | Where to read it after each phase                                          |
|----------------|----------------------------------------------------------------------------|
| `branch`       | `git rev-parse --abbrev-ref HEAD`                                          |
| `change_name`  | `ls openspec/changes/` (single non-`archive` entry created by Phase 1)     |
| `pr_url`       | `gh pr view --json url -q .url` on the current branch                      |
| `pr_state`     | `gh pr view --json state,mergeable -q '"\(.state) \(.mergeable)"'`         |
| `head_sha`     | `git rev-parse HEAD`                                                       |

Do not parse free-text summaries from the child skills for these — the filesystem and `gh` are authoritative.

## Steps

### 0. Pre-flight

Before invoking any child skill:

```bash
git status --porcelain
git rev-parse --abbrev-ref HEAD
```

- Working tree must be clean. If dirty, **stop and ask** — never silently stash. Same rule as the child skills.
- Current branch should be `master` (or the branch the user wants `/new_task2` to fork from). If on a feature branch, ask before continuing — running Phase 1 on a stale branch creates a tangled history.
- Confirm `gh` is authenticated: `gh auth status`. Phase 3 needs it; failing here is cheap, failing in Phase 3 wastes the run.
- Confirm Qwen reachability for the smoke test (Phase 1 step 9) and benchmark (Phase 3 step 1a):
  `curl -sf http://localhost:8090/v1/models -m 3 -o /dev/null && echo Qwen reachable || echo Qwen NOT reachable`
  If unreachable, stop and ask.

### 1. Phase 1 — `/new_task2`

Invoke the **`/new_task2`** skill (no args). It runs its full 12-step flow: pick ticket → scaffold → apply → verify → simplify → smoke test → push → open PR → record follow-ups → final report.

After it returns, read the handoff fields from the table above. Record:

- `branch` (starts with `task2/` for standard path; `chore/skills-` for the workflow-only fast path — see `/new_task2` Step 1a).
- `change_name` (the kebab-case slug under `openspec/changes/`; **empty** for the workflow-only fast path because no change directory was created).
- `pr_url`.
- `ticket_number` and `ticket_title` from the final report (only used in the orchestrator's own final summary; not needed by Phase 2 or 3).
- `is_workflow_only`: `true` if Phase 1's final report says `Path: workflow-only fast path`, else `false`. This determines whether Phase 2 runs and how Phase 3 is invoked.

**Stop conditions** — do not advance to Phase 2 if any of these hold:

- Phase 1 reported a smoke-test failure that did not converge within its loop budget. (`/new_task2` step 9 already loops on smoke regressions; if it stopped and surfaced to the user, this skill stops too.)
- Phase 1 reported a design question or `/opsx:apply` block. Surface and stop.
- `gh pr view` returns no PR for the branch (something failed silently in step 10).
- The PR exists but `pr_state` is not `OPEN MERGEABLE` (e.g. `CONFLICTING`, or already `MERGED` from a prior aborted run).

When the stop condition fires, print a single status line — `full_task2: stopped after Phase 1 — <reason>` — plus the PR URL if any, and exit. Do not auto-retry.

### 2. Phase 2 — `/review_task2`

**Skip Phase 2 entirely if `is_workflow_only == true`.** The reviewer subagent reviews diffs through the lens of correctness / TDD / test coverage — none of which apply to skill prose. `/new_task2` Step 1a's fast path explicitly excludes Phase 2 from the workflow-only flow. Print one line `full_task2: Phase 2 skipped (workflow-only fast path)` and proceed to Phase 3.

Invoke the **`/review_task2`** skill (no args). It runs the codex → plan → sonnet → simplify loop on the current branch's diff against master, committing any fixes at step 8.

The orchestrator does **not** participate in the planning. `/review_task2` is explicit that the running session is the planner; do not re-read codex output here, do not second-guess categorizations, do not reshape its plan. Just wait for it to return.

After it returns:

- `git rev-list --count <pr_head_before>..HEAD` on the branch — were there new commits this phase?
- `git status --porcelain` — should be clean (review_task2 step 8 commits).

If the working tree is dirty after Phase 2 returns, that is a `/review_task2` contract violation — surface it and stop. Do not commit on its behalf.

If new commits were added, push them so the PR picks them up:

```bash
git push
```

Phase 3 will fail to merge a PR whose remote head lags behind local — pushing here closes that gap.

**Stop conditions** — do not advance to Phase 3:

- `/review_task2` aborted with iterations > 5 (its own thrash guard).
- It reported a subagent block reason that the loop did not resolve (genuine pre-existing failure, design question, etc.).
- A test or ruff check is now failing on the branch (re-run `cd task2 && uv run ruff check . && uv run pytest` from the repo root to confirm).

### 3. Phase 3 — `/done_pr`

**Workflow-only fast path (`is_workflow_only == true`):** there is no `change_name` and no OpenSpec directory to archive. Do **not** invoke `/done_pr` with a change-name argument it cannot resolve. Instead, run the merge sequence directly, then execute the 5-step post-merge ticket-archival sequence below.

**Step 1 — Merge:**

```bash
gh pr merge "$pr_url" --squash --delete-branch
git checkout master && git pull --ff-only
```

Skip the benchmark substep — it is gated on `task2/` code changes (none here).

**Step 2 — Parse ticket number from merged PR title:**

```bash
pr_title=$(gh pr view "$pr_url" --json title -q .title)
# pr_title typically ends with "(#NN)" from the squash-merge subject
```

Extract `ticket_number` with: `re.search(r'\(#(\d+)\)\s*$', pr_title)` (or the shell equivalent: `echo "$pr_title" | grep -oP '\(#\K\d+(?=\)\s*$)'`).

If the parse returns nothing (human edited the squash subject in the merge dialog), print:

```
full_task2 Phase 3: WARNING — could not parse ticket number from PR title "<title>"; skipping ticket archival. Run manually: (cd task2 && uv run python scripts/archive_workflow_only_ticket.py --slug <slug> --ticket-number <NNN> --pr-number <PR-NN> --date <YYYY-MM-DD>)
```

Then jump to Phase 4 without failing.

**Step 3 — Archive the ticket file:**

`<slug>` and `<NNN>` come from the ticket selected in Phase 1. `<PR-NN>` is the PR number parsed from `$pr_url` (e.g. `gh pr view "$pr_url" --json number -q .number`). `<YYYY-MM-DD>` is today (`date -I`).

```bash
ticket_slug="<slug-from-phase-1>"   # e.g. fast-path-ticket-archival-hygiene
ticket_num=<NN>                      # e.g. 82 (no leading zero; helper and padding handle it)
pr_num=$(gh pr view "$pr_url" --json number -q .number)
iso_date=$(date -I)

(cd task2 && uv run python scripts/archive_workflow_only_ticket.py \
  --slug "$ticket_slug" \
  --ticket-number "$ticket_num" \
  --pr-number "$pr_num" \
  --date "$iso_date")
```

This edits `task2/tickets/active/<NNN>-<slug>.md` frontmatter (`status: archived`, `merged_pr`, `archived_at`), `git mv`s it to `task2/tickets/archive/`, and regenerates `task2/tickets/INDEX.md`.

**Step 4 — Commit on a chore branch (master is branch-protected; direct push is rejected):**

This is the same shape as the `chore/skills-lessons-<change>` PRs in `/auto_task2` step 5 — small commit on a `chore/*` branch, `gh pr create`, auto-merge.

```bash
git checkout -b "chore/archive-ticket-${pr_num}"
ticket_num_padded=$(printf '%03d' "$ticket_num")
git add "task2/tickets/active/${ticket_num_padded}-${ticket_slug}.md" 2>/dev/null || true  # deletion
git add "task2/tickets/archive/${ticket_num_padded}-${ticket_slug}.md"
git add "task2/tickets/INDEX.md"
git commit -m "docs(task2): archive ticket #${ticket_num} — ${ticket_slug}

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
git push -u origin "chore/archive-ticket-${pr_num}"
```

Note: `git add` on the deleted active file may show "pathspec did not match" if `git mv` already handled it — the `2>/dev/null || true` guards against that. Use `git status --porcelain` to confirm the right files are staged before committing.

**Step 5 — Open PR and auto-merge:**

```bash
gh pr create \
  --title "docs(task2): archive ticket #${ticket_num} — ${ticket_slug}" \
  --body "Automated post-merge archival for workflow-only ticket #${ticket_num}. Merged via PR #${pr_num}." \
  --base master
gh pr merge "chore/archive-ticket-${pr_num}" --squash --delete-branch --auto
git checkout master && git pull --ff-only
```

Then jump to Phase 4.

**Standard path:** invoke the **`/done_pr`** skill with the change name from Phase 1: `/done_pr <change-name>`. It handles archive → spec sync → benchmark capture → push → merge → master sync.

`/done_pr` itself has a pre-flight check for working-tree state, the OpenSpec sync ordering rule, and the benchmark-then-merge ordering. Trust those — do not pre-run any of its substeps in this orchestrator.

After it returns, capture:

- `merge_commit_sha`: `gh pr view <pr_url> --json mergeCommit -q .mergeCommit.oid` (where `<pr_url>` is the cached one from Phase 1, since the local branch may already be deleted by `--delete-branch`).
- `pr_state`: should be `MERGED`.
- Local `master` HEAD: `git rev-parse HEAD` after the `git pull --ff-only` from `/done_pr` step 5.

**Stop conditions** — `full_task2` does not declare success unless `pr_state == MERGED` and local master has fast-forwarded to include the merge commit.

### 4. Final report

Print one block with:

- Ticket: `<number>. <title>` from Phase 1.
- Change: `<change-name>` (now under `openspec/changes/archive/<date>-<change-name>/`).
- Branch: `<branch>` (deleted on remote by `gh pr merge --delete-branch`).
- PR: `<pr_url>` — `MERGED`.
- Merge commit: `<merge_commit_sha>`.
- Phase commit counts: `phase1_commits` (from `/new_task2`), `phase2_commits` (from `/review_task2`, often 0), `phase3_commits` (archive + benchmark).
- Outstanding follow-ups from Phase 1 step 11 (new ticket files written to `task2/tickets/active/`), or `none`.
- Suggested next: `/full_task2` again if there are active tickets remaining in `task2/tickets/INDEX.md`, otherwise stop.

## Guardrails

- **Never** run `/new_task2`, `/review_task2`, or `/done_pr` with overrides that change their behavior. If a phase needs a different shape, fix the phase skill in its own PR — not here.
- **Never** wrap any phase in a subagent. The Skill tool calls are direct, in the main thread.
- **Never** advance past a stop condition. Phase 2 does not run if Phase 1 surfaces a blocker; Phase 3 does not run if Phase 2 leaves the tree dirty. Each child skill has good reasons for its blockers — respect them.
- **Never** force-push, never `--no-verify`, never weaken any test or quality gate to make a phase converge. These rules are inherited from `task2/CLAUDE.md` and the child skills, and they are not relaxed here.
- If the orchestrator needs to surface a blocker, do it with one short sentence and the relevant artifact paths/URLs — do not dump the child skill's full output. The user can read the child skill's transcript directly if they need detail.
