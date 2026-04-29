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
   - **Process-only-diff fast path (skip benchmark when no agent runtime can be affected).** Inspect the same diff. If EVERY changed path under `task2/` matches one of:
     - `task2/scripts/{score,bench,trends,webvoyager_trends,regen_tickets_index}.py`
     - `task2/scripts/opsx_ff_template*.py` (or any `task2/scripts/*template*.py` template helper)
     - `task2/tickets/**` (ticket file moves, frontmatter edits, INDEX regen)
     - `task2/README.md`, `task2/CLAUDE.md`, `task2/AGENTS.md`
     - `task2/benchmark/**` (backfilling old artifacts; never *running* the agent)
     - `task2/tests/test_score*.py`, `task2/tests/test_trends*.py`, `task2/tests/test_bench_repeats.py`, `task2/tests/test_tickets*.py` (tests for those scripts)
     - `openspec/**`
   - AND no path matches `task2/agent/**`, `task2/api/**`, `task2/prompts/**`, or any other `task2/tests/**` (i.e. tests that exercise the agent loop / API / browser), THEN skip this entire step (the WebVoyager run, the trends regen, AND the commit). Print one line: `done_pr: skipping webvoyager benchmark — diff is process/scoreboard-math only (no task2/agent/** or task2/prompts/** changes)`. Step 1b and step 1b' also short-circuit because they are gated on "step 1a was skipped" — no double-fire. Why: confirmed in ticket #77 lever 2 on 2026-04-29 — every iteration of `/auto_task2` today runs WebVoyager (~3-5 min, ~$0.40 of Qwen, non-deterministic flake source) regardless of whether the diff could plausibly move an agent runtime axis; for ~30% of tickets (process / scoreboard math / tickets-folder maintenance) the run is pure overhead. How to apply: this gate is conservative — when in doubt about a path's classification (e.g. a new `task2/scripts/<name>.py` that *does* drive agent calls, like a one-off eval runner), default to running the benchmark. The denylist (`task2/agent/**`, `task2/api/**`, `task2/prompts/**`, agent-exercising tests) is the source of truth; if any one path matches the denylist, run 1a unconditionally. Two safety co-conditions: (i) skip ONLY when the diff is non-empty AND fully matches the allowlist (an empty diff already short-circuits at the line above); (ii) NEVER skip when the touched files include a new top-level `task2/agent/<x>` or `task2/prompts/<x>` directory, even if it's only one file.
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

1b. **Diagnose benchmark failures and file actionable ticket files in `task2/tickets/active/`.**

   Skip entirely if step 1a was skipped (no task2 changes), or if the WebVoyager run wrote zero `[FAIL]` cases. Otherwise:

   - Read the just-written `task2/benchmark/<sanitized-branch>/webvoyager/<timestamp>.json`. Each `cases[]` entry has `status`, `failure_class`, `failure_detail`, `validators`, `step_breakdown`, `escalations`, `replans`, and `cache_events` — the same fields the basic suite produces, just sourced from live WebVoyager tasks.
   - Check `task2/tickets/active/` and `task2/tickets/archive/` for existing tickets so you know what is already tracked. Note the highest existing ticket number: `ls task2/tickets/active/ task2/tickets/archive/ | grep -oE '^[0-9]+' | sort -n | tail -1`.
   - **Cross-run recurrence check (mandatory before "flake" classification).** Before classifying any `failed` case as flake, list the most recent prior `task2/benchmark/<other-branch>/webvoyager/*.json` files and compare per-case `failure_class` + `failure_detail` (`failure_detail` is the stringified exception, including class name and message — a meaningful enough fingerprint without further normalization). Recommended one-liner: `for f in $(ls -t /home/pgi/vici/task2/benchmark/*/webvoyager/*.json | head -5); do python3 -c "import json,sys; d=json.load(open(sys.argv[1])); [print(sys.argv[1], c['id'], c['status'], c.get('failure_class'), c.get('failure_detail','')[:80]) for c in d['cases'] if c['status']=='failed']" "$f"; done`. If the SAME `case_id` appears with the SAME `failure_class` AND essentially the same `failure_detail` (e.g. both runs say `LLMError('http 400')`) across at least one prior run, treat that case as a *recurring* failure — file a ticket regardless of whether `failure_class == "tool_error"`. The "transient flake" classification only applies to first-occurrence-or-isolated failures. Why: confirmed in PR #99 on 2026-04-28 — `webvoyager-1` failed with `LLMError('http 400')` at step 0 in both `task2-benchmarks-readme-and-tier0` and `task2-implement-fail-prompt-tightening` runs; the orchestrator initially classified both as flake and skipped the new-tickets commit, and the user had to interject to file ticket #66 manually. How to apply: run the cross-run check FIRST (before the per-case classification block below), and tag each `failed` case as `recurring` or `first-occurrence`; only `first-occurrence + tool_error` qualifies for "do not file" under the existing flake rule.
   - For each failed case, classify the symptom against existing tickets:
     - **`failure_class == "tool_error"` from a transient network/LLM error** (e.g. `LLMError('http 400')`, playwright navigation timeout on a live page) — usually environmental flake **only when the cross-run check above tagged this case as `first-occurrence`**; if it tagged as `recurring`, file a ticket.
     - **`failure_class == "no_done_emitted"` with low step count** (1-3 steps out of 20) → likely a planner / loop convergence issue against unfamiliar live DOMs. Cross-check existing tickets before filing.
     - **`failure_class == "validator_fail"` with `answer.nonempty`** → the agent finished but produced an empty answer. May indicate prompt drift on real-world pages.
     - **Novel pattern not covered by any existing ticket** → file a new ticket per the rules below.
   - For each novel pattern, write a new ticket file `task2/tickets/active/<NNN>-<slug>.md` (continuing numbering from the highest existing ticket). Each file MUST be self-contained so a fresh `/new_task2` run can pick it up cold. Use all 14 required frontmatter fields (id, slug, status: active, tier, urgency, axes, dependencies, pre_flight_gates, evidence, related, filed_pr: null, merged_pr: null, archived_at: null, trigger). Body:
     - Bold lead naming the symptom, with the failing case id inline (e.g. `webvoyager-<id>` and the originating `web` domain).
     - One-sentence description of what the trace shows or doesn't show.
     - Concrete TDD-shaped acceptance criterion: a failing test that reproduces the symptom (deterministic fixture if possible), and a passing test that asserts the fix.
     - Reference any related existing ticket so the implementer knows whether to extend or add fresh.
   - Run `uv run python task2/scripts/regen_tickets_index.py` to update INDEX.md.
   - Stage `task2/tickets/active/<NNN>-<slug>.md` and `task2/tickets/INDEX.md` on their own and commit:
     ```
     docs(task2): file ticket #<N> — <short title> (webvoyager benchmark failure from <branch>)
     ```
     with the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer. Do **not** bundle this into the step-1a benchmark commit.
   - **No new tickets case:** if every failure maps to an existing entry or is judged environmental flake, skip the commit and print one line: `done_pr: webvoyager failures all map to existing tickets / flake — no new follow-ups filed.`
   - This step does NOT block the merge in step 4, even if the analysis surfaces something concerning. The merge proceeds; the new tickets are picked up by future `/new_task2` runs.

1b'. **Compare aggregate benchmark axes against the prior baseline and file tickets on regression (if task2 was touched).**

   Skip entirely if step 1a was skipped. Step 1b catches failures with novel `failure_class` / `failure_detail` patterns; this step catches *aggregate* regressions that are silent on a per-case `[FAIL]` axis — e.g. a fix that converts a fast crash into a slow timeout (pass-rate stays flat, but cost and latency double). Without this step, those slip through because no individual case is "newly failing" — the case has just become more expensive to fail.

   - Pick the comparison baseline. **WebVoyager JSONs are NOT filed under `task2/benchmark/master/webvoyager/`** — that directory holds only basic-suite artifacts. WebVoyager runs live exclusively under per-branch directories (`task2/benchmark/<sanitized-branch>/webvoyager/<timestamp>.json`), and `/done_pr` writes the new JSON *before* the merge, so the prior baseline IS whichever branch's WebVoyager file was newest immediately before this run. Rule:
     1. Take the chronologically-most-recent run other than this branch's via mtime: `ls -t /home/pgi/vici/task2/benchmark/*/webvoyager/*.json | grep -v "/<sanitized-branch>/" | head -1`. This works because every WebVoyager run is merged to master through a feature-branch PR, so the newest non-self file on disk corresponds to the last `/done_pr` that landed.
     2. If that command returns nothing (first WebVoyager run ever recorded), skip this step and print `done_pr: no prior webvoyager baseline — skipping aggregate regression check`.
     **Do not** look under `task2/benchmark/master/` for WebVoyager — confirmed in PR #102's `/done_pr` follow-up on 2026-04-28: that path only contains basic-suite `results.json` / `scoreboard.md`, so a `master/webvoyager/` lookup would silently fall through and either compare against nothing or compare against the wrong file. The newest-non-self mtime rule is the only correct source.
   - Compute aggregates for both runs (this run's JSON is the one written in step 1a; the baseline is from above):
     ```python
     pass_rate = sum(1 for c in cases if c['status']=='succeeded') / len(cases)
     total_usd  = sum(c.get('usd', 0.0) for c in cases)
     total_pt   = sum(c.get('prompt_tokens', 0) for c in cases)
     total_ct   = sum(c.get('completion_tokens', 0) for c in cases)
     total_lat  = sum(c.get('latency_ms_total', 0) for c in cases)
     ```
   - Compute deltas as percentages (`(this - baseline) / baseline`, with a `1e-9` guard for divide-by-zero on baselines that legitimately scored 0). For pass-rate, also compute the absolute count change (`Δ_cases = this_pass_count - baseline_pass_count`).
   - **Regression thresholds** (any one trips the check):
     - `Δ_pass_rate < 0` (pass-rate went down at all — even by one case in a 3-case suite is meaningful).
     - `Δ_total_usd > +25%` AND absolute Δ ≥ $0.05 (filters out noise on tiny baselines).
     - `Δ_total_pt + Δ_total_ct > +25%` AND absolute Δ ≥ 10K tokens.
     - `Δ_total_lat > +25%` AND absolute Δ ≥ 30s.
     The `+25%` floor is empirical — WebVoyager's small N (3 cases) makes single-case timing noise easily ±10%, so anything under 25% is plausibly noise. The absolute-floor co-condition prevents flagging on baselines so small (e.g. $0.01 total) that any change crosses 25%.
   - **No regression** → print one line: `done_pr: aggregate webvoyager axes within tolerance vs <baseline-branch> (pass=<X/N>→<Y/N>, cost <ΔUSD%>, tokens <ΔPT+ΔCT%>, latency <Δlat%>)` and continue.
   - **Regression detected** → for each case whose individual axis numbers got worse vs the baseline's same case (matched by `case_id`), identify the *causal pattern*. Common causes seen in practice:
     - **Fast-fail → slow-timeout**: case status flipped from `failed (steps=0)` to `timeout (steps=max_steps)`. Cause: a recent fix removed a crash but the loop has no early-termination heuristic. *Fix shape:* stuck-state detector in `agent/loop.py` (e.g. K consecutive identical tool calls → `failed/stuck_repeat`).
     - **Transient nav error**: case status flipped from `succeeded` to `failed (tool_error)` with `failure_detail` matching `net::ERR_NETWORK_CHANGED|ERR_NETWORK_IO_SUSPENDED|ERR_INTERNET_DISCONNECTED|Page.goto.*Timeout`. Cause: Chromium / network flap. *Fix shape:* one-shot retry on the matching error class in `agent/browser.py:Browser.goto`.
     - **Per-case cost/token bloat without status change**: same case still passes but uses 2-3× more tokens/steps. Cause: a prompt or observation change made the agent take a longer path. *Fix shape:* needs a per-case trace investigation ticket — file a "diagnose `<case-id>` token regression at SHA `<merge_sha>`" ticket pointing at the new run JSON and the baseline JSON.
     - **Aggregate slowdown without per-case localization**: every case got marginally slower (typical of an LLM-side change or a prompt size increase). *Fix shape:* file an audit ticket pointing at `agent/loop.py` (prompt size growth?) and `agent/llm.py` (sampling change?), with the per-case diff included as evidence.
   - For each distinct causal pattern, write a new ticket file `task2/tickets/active/<NNN>-<slug>.md` (continuing numbering from the highest existing ticket — check both active and archive dirs: `ls task2/tickets/active/ task2/tickets/archive/ | grep -oE '^[0-9]+' | sort -n | tail -1`). Each file MUST be self-contained per the same rules as step 1b: bold lead, one-sentence symptom, TDD-shaped acceptance criterion, *Why useful* tied to the specific axis regression observed (cite the exact `task2/benchmark/<branch>/webvoyager/<timestamp>.json` paths and the % deltas), and a *Trigger:* line naming `/done_pr`'s aggregate-regression check on `<date>`.
   - Run `uv run python task2/scripts/regen_tickets_index.py` to update INDEX.md.
   - Stage new `task2/tickets/active/<NNN>-<slug>.md` files and `task2/tickets/INDEX.md` and commit:
     ```
     docs(task2): file ticket #<N> — <short title> (webvoyager aggregate regression from <branch>)
     ```
     with the standard `Co-Authored-By` trailer. **Combining with the step-1b commit is allowed** when both surface in the same `/done_pr` run — combine into one `docs(task2): file tickets #<N>, #<M> — webvoyager benchmark failures and regressions from <branch>` commit whose body lists all new ticket ids.
   - **No-op duplicate guard:** before filing, `grep -rn "<causal pattern keyword>" task2/tickets/active/ task2/tickets/archive/` to check for an existing ticket matching the causal pattern. If found, do not duplicate; instead reference the existing ticket number and skip the commit.
   - This step also does NOT block the merge in step 4. The new tickets are picked up by `/new_task2`'s three-axis selection on the next iteration, which is exactly the rubric needed for "performance regression" tickets.

1c. **Archive the ticket file from `task2/tickets/active/` (if task2 was touched).**

   Skip entirely if step 1a was skipped (no task2 changes) or if the change does not map to a numbered ticket. Otherwise:

   - Identify the ticket number this change implements. Source of truth, in priority order:
     1. The orchestrator already knows it (e.g. `/full_task2` / `/auto_task2` announce the ticket number when picking it). Trust that.
     2. Failing that, `grep -nE "ticket #?[0-9]+|#[0-9]+" openspec/changes/archive/<dated-dir>/proposal.md` and pick the first ticket-style reference.
   - Find the active ticket file: `ls task2/tickets/active/<NNN>-*.md` (where `<NNN>` is the zero-padded ticket id, minimum 3 digits). If not found, check if it is already in `task2/tickets/archive/` — if so, skip to no-op.
   - `git mv task2/tickets/active/<NNN>-<slug>.md task2/tickets/archive/<NNN>-<slug>.md`
   - Edit the moved file's frontmatter in-place:
     - `status: archived`
     - `merged_pr: <PR number>` — use `gh pr view --json number -q .number` to get the current PR number.
     - `archived_at: <YYYY-MM-DD>` — today's date in ISO-8601 format.
   - Run `uv run python task2/scripts/regen_tickets_index.py` to update `task2/tickets/INDEX.md`.
   - Stage the moved file and INDEX.md and commit in a single commit:
     ```
     docs(task2): archive ticket #<N> — <short title>
     ```
     with the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
   - **No-op case:** if `task2/tickets/active/<NNN>-*.md` does not exist (already archived, or skill-only PR with no ticket), skip the commit and print one line: `done_pr: ticket #<N> already archived or not found in active/` (or `done_pr: no ticket number to archive` if step 1c found none).

   Why: moving the ticket file from active/ to archive/ is the canonical record of completion — INDEX.md reflects it immediately after regen, and future `/new_task2` step 1 won't consider archived tickets as candidates. One commit replaces the prior two-commit pattern (plan.md edit + archival note), keeping the PR's `git log` cleaner.

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
