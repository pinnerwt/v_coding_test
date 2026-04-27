---
name: done_pr
description: Finalize an open PR by archiving its OpenSpec change, committing the spec updates, pushing, merging the PR, then syncing master. Use when the user types `/done_pr` once a PR is approved and ready to land.
---

# done_pr

Wraps up an OpenSpec-driven PR end-to-end: archive → commit → push → merge → sync master.

## Steps

0. **Pre-flight: working tree.** Before invoking any sub-skill, run `git status` and decide:
   - **Clean** → proceed.
   - **Dirty with files in this PR's scope** (e.g. an in-progress `.claude/commands/<name>.md` skill update from the same lessons-learned thread on this branch — especially when there is already a sibling `chore(skills):` commit on the branch) → commit it on the branch as a separate `chore(<scope>):` commit *before* archive, with the standard `Co-Authored-By` trailer. Do not bundle it into the archive commit.
   - **Dirty with unrelated files** → stop and ask the user. Never silently `git stash` or `git restore`.

1. **Archive the change.** Invoke the `opsx:archive` skill (equivalently `openspec-archive-change`). If the user did not pass a change name as `args`, follow the archive skill's normal prompting flow to pick one. Pass `args` straight through if provided.

   **Critical ordering:** if the change has delta specs under `openspec/changes/<name>/specs/`, the `opsx:sync` step MUST run *before* `mv`-ing the directory to `archive/`. The archive skill's prompt assesses sync state and offers to invoke `/opsx:sync`; accept it (or invoke `/opsx:sync <name>` yourself) **before** the move. Once the directory has moved, the deltas are no longer at the path the sync skill looks at, and the main specs will silently miss the update. This is especially important when a delta introduces a *new* capability (a directory under `specs/` that does not yet exist under `openspec/specs/`) — sync is the only step that creates the new main spec.

   **CLI fallback after manual sync:** if you bypass the `opsx:archive` skill and invoke `openspec archive <name> --yes` directly (e.g. mid-`/full_task2` after `/opsx:sync` already applied the deltas), the CLI will refuse with `... ADDED failed for header "<requirement>" - already exists` and abort. Pass `--skip-specs`: `openspec archive <name> --yes --skip-specs`. The skill's `mv`-based path does not hit this because it never re-applies deltas; only the CLI does. Confirmed in PR #55's `/done_pr` run on 2026-04-27 — sync had been completed by hand, the CLI tried to re-apply, and `--skip-specs` was the unblock.

1a. **Record task2 benchmark (if task2 was touched).**
   - Detect: `git diff --name-only origin/master...HEAD -- task2/` — if empty, skip this step entirely.
   - **Pre-check Qwen reachability** before starting the benchmark (the run takes minutes and silently degrades with a dead endpoint):
     `curl -sf http://localhost:8090/v1/models -m 3 -o /dev/null && echo Qwen reachable || echo Qwen NOT reachable`
     If unreachable, stop and ask the user.
   - From the repo root run:
     `cd task2 && LLM_BASE_URL=http://localhost:8090 LLM_MODEL=qwen3.5-27b uv run python -m scripts.benchmark --branch "$(git rev-parse --abbrev-ref HEAD)"`
   - Then regenerate the trend SVGs and refresh the README's `<!-- TRENDS:BEGIN -->` block (latest-run table):
     `cd task2 && uv run python -m scripts.trends`
     (reads every `task2/benchmark/*/results.json`, overwrites `task2/benchmark/_trends/{pass_rate,latency,cost}.svg`, and rewrites the trends block in `task2/README.md` between the `<!-- TRENDS:BEGIN -->` / `<!-- TRENDS:END -->` markers.)
   - Stage `task2/benchmark/<sanitized-branch>/`, `task2/benchmark/_trends/`, and `task2/README.md` and commit with a HEREDOC message:
     `chore(task2): record benchmark for <branch>`
     including the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
   - **`[FAIL]` cases in the benchmark output do not block the merge.** The CI workflow `task2-benchmark` only checks that the results file exists and that its `run_at` is newer than the merge-base with master. The benchmark is a tracking artifact, not a gate. If a regression is suspected, surface it to the user but do not stop unless they ask. (The trend SVGs make multi-run regressions visually obvious; a single `[FAIL]` on drift cases is normal under the current Qwen 27B and not actionable here.)
   - **No-op case:** the only time `git status` is clean after this step is a re-run of `/done_pr` on an already-finalized branch (rare). In that case skip the commit. A first run on a new branch always produces at least the new `task2/benchmark/<sanitized-branch>/results.json` and an updated trend SVG, so a clean `git status` after a *first* run is a signal that the benchmark script silently failed — investigate before continuing.

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
   - **Verifying the merge landed:** there is no `merged` JSON field on `gh pr view` (it will fail with `Unknown JSON field: "merged"`). Use `gh pr view --json state,mergedAt,mergeCommit -q .` instead — `state` flips to `MERGED`, `mergedAt` becomes a timestamp, and `mergeCommit.oid` is the squash sha.

5. **Sync master.** `gh pr merge --delete-branch` already switches the local checkout back to `master` and prunes the remote branch, so a bare `git checkout master` is usually a no-op (and `git pull` without a fast-forward guard will silently pull a merge commit if your local master has diverged). Prefer `git pull --ff-only` here. If `--ff-only` refuses, stop and investigate — your local master has work that isn't on the remote and a blind pull would hide that. Report the new HEAD briefly.

## Notes

- Never force-push, never `--amend`, never `--no-verify`. If a pre-commit hook fails, fix the issue and create a new commit.
- Never push or merge to `master`/`main` directly — this skill operates on a feature branch's PR.
- If the working tree has unrelated dirty changes at the start, stop and ask the user before committing.
- If `gh` is not authenticated or the branch has no PR, stop after step 3 and tell the user — don't try to open a PR yourself unless asked.
