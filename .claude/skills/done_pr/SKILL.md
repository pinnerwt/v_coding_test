---
name: done_pr
description: Finalize an open PR by archiving its OpenSpec change, committing the spec updates, pushing, merging the PR, then syncing master. Use when the user types `/done_pr` once a PR is approved and ready to land.
---

# done_pr

Wraps up an OpenSpec-driven PR end-to-end: archive → commit → push → merge → sync master.

## Steps

1. **Archive the change.** Invoke the `opsx:archive` skill (equivalently `openspec-archive-change`). If the user did not pass a change name as `args`, follow the archive skill's normal prompting flow to pick one. Pass `args` straight through if provided.

1a. **Record task2 benchmark (if task2 was touched).**
   - Detect: `git diff --name-only origin/master...HEAD -- task2/` — if empty, skip this step entirely.
   - Otherwise, from the repo root run:
     `cd task2 && LLM_BASE_URL=http://localhost:8090 LLM_MODEL=qwen3.5-27b uv run python -m scripts.benchmark --branch "$(git rev-parse --abbrev-ref HEAD)"`
     (the local Qwen at `localhost:8090` must be reachable; if it isn't, stop and ask the user.)
   - Then regenerate the trend SVGs:
     `cd task2 && uv run python -m scripts.trends`
     (reads every `task2/benchmark/*/results.json` and overwrites `task2/benchmark/_trends/{pass_rate,latency,cost}.svg`. README image refs are static and don't need updating.)
   - Stage `task2/benchmark/<sanitized-branch>/` and `task2/benchmark/_trends/` and commit with a HEREDOC message:
     `chore(task2): record benchmark for <branch>`
     including the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
   - If `git status` shows no changes after the run (results identical to what's already on the branch), skip the commit — do not create an empty one.
   - The CI workflow `task2-benchmark` checks that this file exists and that its `run_at` is newer than the merge-base with master, so this step is what makes the PR mergeable.

2. **Commit the spec/archive updates.** After archive completes:
   - Run `git status` and `git diff --stat` to confirm only OpenSpec files moved/changed (typically `openspec/changes/<name>/` → `openspec/changes/archive/<name>/`, and possibly `openspec/specs/...`).
   - Stage exactly those paths (do not `git add -A`).
   - Commit with a conventional message like:
     `chore(openspec): archive <change-name> and sync specs`
     Use a HEREDOC for the message and include the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
   - If there is nothing new to commit, skip to step 3 — do not create an empty commit.

3. **Push the branch.** Confirm the current branch is *not* `master`/`main`. Then `git push` (use `-u origin <branch>` if upstream isn't set). This ensures the archive commit is on the PR before merging.

4. **Merge the PR.** Identify the PR for the current branch with `gh pr view --json number,state,mergeable,headRefName -q .` (no number arg → uses the branch's PR).
   - If state is not `OPEN`, report it and stop (don't try to merge a closed/already-merged PR).
   - If mergeable is `CONFLICTING`, stop and ask the user.
   - Otherwise merge with `gh pr merge --squash --delete-branch` (default: squash + delete branch). If the user passed a different strategy via `args` (e.g. `merge`, `rebase`), honor it.

5. **Sync master.** Run `git checkout master && git pull`. Report the new HEAD briefly.

## Notes

- Never force-push, never `--amend`, never `--no-verify`. If a pre-commit hook fails, fix the issue and create a new commit.
- Never push or merge to `master`/`main` directly — this skill operates on a feature branch's PR.
- If the working tree has unrelated dirty changes at the start, stop and ask the user before committing.
- If `gh` is not authenticated or the branch has no PR, stop after step 3 and tell the user — don't try to open a PR yourself unless asked.
