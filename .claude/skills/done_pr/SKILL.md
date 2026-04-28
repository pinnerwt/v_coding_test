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

   **`--no-validate` for new-capability spec.md drift:** if the change introduces a brand-new capability and its delta at `openspec/changes/<name>/specs/<new-capability>/spec.md` was authored as a *full main-spec* (top-level `# <Capability> Specification` + `## Purpose` + `## Requirements`) rather than the delta format (`## ADDED Requirements` followed by `### Requirement: ...`), `openspec archive --yes --skip-specs` will still refuse with `No delta sections found. Add headers such as "## ADDED Requirements" or move non-delta notes outside specs/.` Pass `--no-validate` together with `--skip-specs`: `openspec archive <name> --yes --skip-specs --no-validate`. The right long-term fix lives upstream in `/new_task2`'s artifact-generation step (the subagent should produce delta-format specs even for new capabilities); `--no-validate` here is a one-shot unblock so the PR can land. Confirmed in PR #58's `/done_pr` run on 2026-04-27.

1a. **Record task2 WebVoyager benchmark (if task2 was touched).**
   - Detect: `git diff --name-only origin/master...HEAD -- task2/` — if empty, skip this step entirely.
   - **Pre-check Qwen reachability** before starting the benchmark (the run takes minutes and silently degrades with a dead endpoint):
     `curl -sf http://localhost:8090/v1/models -m 3 -o /dev/null && echo Qwen reachable || echo Qwen NOT reachable`
     If unreachable, stop and ask the user.
   - WebVoyager cases are live-only (they have no fixture). Confirm the workstation can reach the public web (a single `curl -sfI https://www.google.com -m 5 -o /dev/null && echo web reachable || echo web NOT reachable`); if not, stop and ask.
   - From the repo root run, directing output into the per-branch directory:
     ```bash
     BRANCH="$(git rev-parse --abbrev-ref HEAD)"
     SAFE_BRANCH="${BRANCH//\//-}"
     cd task2 && \
       EVAL_RESULTS_DIR="benchmark/${SAFE_BRANCH}/webvoyager" \
       LLM_BASE_URL=http://localhost:8090 LLM_MODEL=qwen3.5-27b \
       uv run python -m scripts.bench --suite webvoyager --live
     ```
     This writes `task2/benchmark/<sanitized-branch>/webvoyager/<timestamp>.json` (a `cases` payload in the same shape as `task2/benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json`).
   - Then regenerate the WebVoyager trend SVGs and refresh the README's `<!-- WEBVOYAGER_TRENDS:BEGIN -->` block:
     `cd task2 && uv run python -m scripts.webvoyager_trends`
     (reads each `task2/benchmark/<branch>/webvoyager/*.json` — taking the latest per branch by `run_at` — overwrites `task2/benchmark/_webvoyager_trends/{pass_rate,latency,cost,failure_classes}.svg`, and rewrites the trends block in `task2/README.md` between the `<!-- WEBVOYAGER_TRENDS:BEGIN -->` / `<!-- WEBVOYAGER_TRENDS:END -->` markers.)
   - Stage `task2/benchmark/<sanitized-branch>/webvoyager/`, `task2/benchmark/_webvoyager_trends/`, and `task2/README.md` and commit with a HEREDOC message:
     `chore(task2): record webvoyager benchmark for <branch>`
     including the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
   - **Exit code 1 with `[FAIL]` cases is not a crash.** `scripts.bench` exits 1 whenever any case status is in `FAIL_STATUSES`, but the JSON results file is written before exit. WebVoyager runs against live websites and a non-trivial fail rate is expected. Verify the artifact exists (`ls task2/benchmark/<sanitized-branch>/webvoyager/*.json`) and inspect the tail of stdout for `[PASS]`/`[FAIL]`/`[SKIP]` lines; if the artifact is present, proceed to the trends step and commit.
   - **No-op case:** the only time `git status` is clean after this step is a re-run of `/done_pr` on an already-finalized branch (rare). A first run always produces a new `<timestamp>.json` under `task2/benchmark/<sanitized-branch>/webvoyager/`; a clean `git status` on a first run signals the bench script silently failed — investigate before continuing.

1b. **Diagnose benchmark failures and file actionable tickets in `task2/plan.md`.**

   Skip entirely if step 1a was skipped (no task2 changes), or if the WebVoyager run wrote zero `[FAIL]` cases. Otherwise:

   - Read the just-written `task2/benchmark/<sanitized-branch>/webvoyager/<timestamp>.json`. Each `cases[]` entry has `status`, `failure_class`, `failure_detail`, `validators`, `step_breakdown`, `escalations`, `replans`, and `cache_events` — the same fields the basic suite produces, just sourced from live WebVoyager tasks.
   - Read the `## Benchmark improvements (candidates)` section of `task2/plan.md` so you know what is already tracked. Note the highest existing ticket number for appending.
   - For each failed case, classify the symptom against existing tickets:
     - **`failure_class == "tool_error"` from a transient network/LLM error** (e.g. `LLMError('http 400')`, playwright navigation timeout on a live page) — usually environmental flake; do not file a ticket unless the same case fails on a repeat run.
     - **`failure_class == "no_done_emitted"` with low step count** (1-3 steps out of 20) → likely a planner / loop convergence issue against unfamiliar live DOMs. Cross-check existing tickets before filing.
     - **`failure_class == "validator_fail"` with `answer.nonempty`** → the agent finished but produced an empty answer. May indicate prompt drift on real-world pages.
     - **Novel pattern not covered by any existing ticket** → file a new ticket per the rules below.
   - For each novel pattern, append a new entry to the `## Benchmark improvements (candidates)` list (continuing the numbering from the highest existing ticket). Each entry MUST be self-contained so a fresh `/new_task2` run can pick it up cold:
     - Bold lead naming the symptom, with the failing case id inline (e.g. `webvoyager-<id>` and the originating `web` domain).
     - One-sentence description of what the trace shows or doesn't show.
     - Concrete TDD-shaped acceptance criterion: a failing test that reproduces the symptom (deterministic fixture if possible), and a passing test that asserts the fix.
     - Reference any related existing ticket so the implementer knows whether to extend or add fresh.
   - Stage `task2/plan.md` on its own and commit:
     ```
     docs(task2): record webvoyager benchmark failure tickets from <branch>
     ```
     with the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer. Do **not** bundle this into the step-1a benchmark commit.
   - **No new tickets case:** if every failure maps to an existing entry or is judged environmental flake, skip the commit and print one line: `done_pr: webvoyager failures all map to existing tickets / flake — no new follow-ups filed.`
   - This step does NOT block the merge in step 4, even if the analysis surfaces something concerning. The merge proceeds; the new tickets are picked up by future `/new_task2` runs.

1c. **Scrub the just-archived ticket from `task2/plan.md`'s Undone rubric (if task2 was touched).**

   Skip entirely if step 1a was skipped (no task2 changes) or if the change does not map to a numbered ticket. Otherwise:

   - Identify the ticket number this change implements. Source of truth, in priority order:
     1. The orchestrator already knows it (e.g. `/full_task2` / `/auto_task2` announce the ticket number when picking it). Trust that.
     2. Failing that, `grep -nE "ticket #?[0-9]+|#[0-9]+" openspec/changes/archive/<dated-dir>/proposal.md` and pick the first ticket-style reference.
   - Open `task2/plan.md` and find the `## Undone` section. Inside it, the entry shape is `- **#<N>** — <one-line summary>` under one of the `### P0/P1/P2/P3` urgency subheaders or `### In flight`.
   - Delete the single line whose ticket number matches. Leave the urgency subheader in place even if the section becomes empty (a future `/new_task2` may file a new entry under it). Do **not** touch the long-form ticket text in `## TDD tickets` or `## Benchmark improvements (candidates)` — those are the canonical record and stay forever.
   - Stage `task2/plan.md` on its own and commit:
     ```
     docs(task2): drop archived ticket #<N> from Undone rubric
     ```
     with the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
   - **No-op case:** if the entry was already missing (e.g. an earlier iteration scrubbed it, or the ticket was never in the Undone rubric to begin with — common for skill-only PRs that have no ticket), skip the commit and print one line: `done_pr: ticket #<N> already absent from Undone rubric` (or `done_pr: no ticket number to scrub` if step 1c found none).

   Why: the Undone rubric was previously cleaned up only by `/new_task2` step 11 of the *next* iteration, leaving a one-iteration lag where the rubric showed already-archived tickets. The picking iteration would correctly skip them (per `/new_task2` step 1's archive cross-check) but each stale entry was a small re-derivation of state. Scrubbing on archive bounds the responsibility to the skill that *causes* the staleness — no cross-iteration coordination required. Confirmed pattern: in PR #69 on 2026-04-27 (`fix-escalation-decision-policy-literal`), the rubric still listed both #45 (archived in iter 2) and #47 (archived in this iter); iter 4's selection had to mentally skip both.

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

## Archived: basic benchmark (do not run)

The text below preserves the prior step 1a/1b that drove `scripts.benchmark` (fixture + drift + canary suites) and `scripts.trends` for historical reference. **Do not invoke any of it.** WebVoyager replaced this workflow on 2026-04-28 per user directive; this section is frozen and exists only so the audit trail of past `/done_pr` runs (PRs that referenced "the benchmark" prior to this date) remains interpretable. Any future change to benchmarking goes in step 1a above; do not edit, expand, or "modernize" the text below.

> **1a. Record task2 benchmark (if task2 was touched).**
> - Detect: `git diff --name-only origin/master...HEAD -- task2/` — if empty, skip this step entirely.
> - **Pre-check Qwen reachability** before starting the benchmark (the run takes minutes and silently degrades with a dead endpoint):
>   `curl -sf http://localhost:8090/v1/models -m 3 -o /dev/null && echo Qwen reachable || echo Qwen NOT reachable`
>   If unreachable, stop and ask the user.
> - From the repo root run:
>   `cd task2 && LLM_BASE_URL=http://localhost:8090 LLM_MODEL=qwen3.5-27b uv run python -m scripts.benchmark --branch "$(git rev-parse --abbrev-ref HEAD)"`
> - Then regenerate the trend SVGs and refresh the README's `<!-- TRENDS:BEGIN -->` block (latest-run table):
>   `cd task2 && uv run python -m scripts.trends`
>   (reads every `task2/benchmark/*/results.json`, overwrites `task2/benchmark/_trends/{pass_rate,latency,cost}.svg`, and rewrites the trends block in `task2/README.md` between the `<!-- TRENDS:BEGIN -->` / `<!-- TRENDS:END -->` markers.)
> - Stage `task2/benchmark/<sanitized-branch>/`, `task2/benchmark/_trends/`, and `task2/README.md` and commit with a HEREDOC message:
>   `chore(task2): record benchmark for <branch>`
>   including the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
> - **`[FAIL]` cases in the benchmark output do not block the merge.** The CI workflow `task2-benchmark` only checks that the results file exists and that its `run_at` is newer than the merge-base with master. The benchmark is not a merge gate — but it *is* an input to step 1b, which files tickets for novel failure patterns. Trend SVGs make multi-run regressions visually obvious; a single `[FAIL]` on drift cases is normal under the current Qwen 27B and tracked under existing tickets in `task2/plan.md`.
> - **Exit code 1 with `[FAIL]` cases is not a benchmark crash.** `scripts/benchmark` exits 1 whenever at least one case is `[FAIL]`, even though `results.json`, `scoreboard.md`, and `diff.md` are all written successfully and `Wrote: benchmark/<branch>/results.json` is the final stdout line. When running this step via `run_in_background` (or any non-interactive harness), the harness will surface a "failed with exit code 1" notification that *looks* alarming but is the normal path under the current Qwen 27B failure rate. Verify the artifacts exist (`ls task2/benchmark/<sanitized-branch>/{results.json,scoreboard.md}`) and inspect the tail of the output for the `Wrote:` line — if both are present, proceed to `scripts.trends` and the commit. Why: confirmed in PR #83's `/done_pr` run on 2026-04-28 — the background task notification flagged failure with exit 1, but all artifacts were written and the merge proceeded normally.
> - **No-op case:** the only time `git status` is clean after this step is a re-run of `/done_pr` on an already-finalized branch (rare). In that case skip the commit. A first run on a new branch always produces at least the new `task2/benchmark/<sanitized-branch>/results.json` and an updated trend SVG, so a clean `git status` after a *first* run is a signal that the benchmark script silently failed — investigate before continuing.
>
> **1b. Diagnose benchmark failures and file actionable tickets in `task2/plan.md`.**
>
> Skip entirely if step 1a was skipped (no task2 changes), or if the benchmark wrote zero `[FAIL]` cases. Otherwise:
>
> - Read the just-written `task2/benchmark/<sanitized-branch>/scoreboard.md` and `results.json`. The scoreboard markdown gives per-case status, mechanism-firing counts (Escalations / Replans / Cache Inv.), and validator details. The JSON has the full per-case `events`, `step_breakdown`, and `failure_class` if ticket #31 has landed.
> - Read the `## Benchmark improvements (candidates)` section of `task2/plan.md` (tickets #31+) so you know what is already tracked. Note the highest existing ticket number for appending.
> - For each failed case, classify the symptom against existing tickets:
>   - **All mechanism columns 0/0/0 on a diagnostic case** (e.g. `correction-l1-miss-l2-hit`, `correction-replan`, `maintenance-drift-rename-v2`) → tracked by audit ticket #32. Confirm the case is still in #32's scope; do not duplicate.
>   - **Empty validators + early halt** on a non-diagnostic case (1-3 steps out of N-step budget, validators `[]`) → tracked by failure-classification ticket #31. Do not duplicate.
>   - **Skipped cases without explanation** → tracked by skip-reason tagging ticket #34. Do not duplicate.
>   - **Step / token / latency anomalies** (one step uses 10× the average tokens; one step >30s) → tracked by per-step breakdown ticket #38. Do not duplicate.
>   - **Novel pattern not covered by any existing ticket** → file a new ticket (see below).
> - For each novel pattern, append a new entry to the `## Benchmark improvements (candidates)` list (continuing the numbering from the highest existing ticket). Each entry MUST be self-contained so a fresh `/new_task2` run can pick it up cold:
>   - Bold lead naming the symptom, with the failing case path inline (e.g. `task2/eval/cases/<name>.yaml`).
>   - One-sentence description of what the trace shows or doesn't show.
>   - Concrete TDD-shaped acceptance criterion: a failing test that reproduces the symptom in `task2/tests/test_eval.py` (or the appropriate test file), and a passing test that asserts the new failure-mode field / mechanism row is populated correctly.
>   - Reference any related existing ticket so the implementer knows whether to extend or add fresh.
> - Stage `task2/plan.md` on its own and commit:
>   ```
>   docs(task2): record benchmark failure tickets from <branch>
>   ```
>   with the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer. Do **not** bundle this into the step-1a benchmark commit — the audit trail is cleaner if benchmark-artifact recording and ticket-list updates are separate commits.
> - **No new tickets case:** if every failure maps to an existing #31+ entry, skip the commit and print one line to the user: `done_pr: benchmark failures all map to existing tickets — no new follow-ups filed.` This proves you ran the analysis instead of silently skipping it.
> - This step does NOT block the merge in step 4, even if the analysis surfaces something concerning. The merge proceeds; the new tickets are picked up by future `/new_task2` runs.
