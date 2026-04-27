---
name: "New Task2"
description: Pick the next Task 2 ticket from task2/plan.md, scaffold an OpenSpec change, and drive it through implementation, verification, and simplification with commits along the way.
category: Workflow
tags: [task2, workflow, automation]
---

Automate the full development cycle for the next Task 2 TDD ticket: derive ticket → scaffold change → implement → verify → simplify, committing at each meaningful boundary.

## Steps

### 1. Identify the next ticket

Read `task2/plan.md` and locate the **`## TDD tickets`** section (numbered list near the bottom, starting "1. `llm.py`").

Then check what is already done:
```bash
ls openspec/changes/archive/ 2>/dev/null
ls openspec/changes/ 2>/dev/null
```

Match archived/active change names against the TDD ticket list to determine the **lowest-numbered ticket** that is not yet done. Archived directories carry a date prefix (e.g. `2026-04-25-implement-llm-client`); strip that when matching against ticket slugs. If unsure, use the **AskUserQuestion** tool to confirm with the user before proceeding.

Derive a kebab-case change name from the ticket title. Convention: `implement-<short-slug>`, e.g.:
- Ticket 3 "`locate.py` L1" → `implement-locate-l1`
- Ticket 7 "Locator cache" → `implement-locator-cache`
- Ticket 11 "`loop.py` silent-failure guard" → `implement-loop-silent-failure-guard`

State the chosen ticket number, title, and derived change name in one line before continuing.

### 2. Create a development branch

From the current branch, create and switch to a new branch:
```bash
git checkout -b task2/<change-name>
```

If the working tree is dirty, **stop and ask** the user how to proceed — do not stash or discard. Two known patterns:

- **`task2/plan.md` modified** — leftover from a prior run's Step 11 (follow-up ticket appended but never committed/pushed). Typical answer: carry into the next branch as a `docs(task2):` commit.
- **`.claude/skills/<name>/SKILL.md` or `.claude/commands/<name>.md` modified** — a sibling skill update authored in a separate lessons-learned thread (e.g. tightening `/done_pr`). Typical answer: commit on master *before* branching, as a `chore(skills):` commit. These are unrelated to task2 and don't belong in the PR.

When in doubt, surface the diff and offer four options via **AskUserQuestion**: (a) commit on master and proceed, (b) carry into next branch, (c) discard, (d) pause for manual handling. Never silently stash or run `git restore`.

### 3. Scaffold the OpenSpec change

Invoke the `/opsx:new` skill with the change name (kebab-case derived above). This creates `openspec/changes/<change-name>/` with the default schema.

### 4. Generate all artifacts (subagent)

Spawn a `general-purpose` subagent via the **Agent** tool to run `/opsx:ff` and produce every artifact required for `apply` (typically `proposal.md`, `design.md`, `tasks.md`, `specs/...`). The subagent has no conversation context, so the full self-contained prompt template lives at `.claude/skills/new_task2/subagent-prompts/ff.md`. **Read that file**, substitute the placeholders (`{{change-name}}`, `{{ticket-number}}`, `{{ticket-title}}`, `{{ticket-text}}`), and pass the rendered string as the agent's `prompt`.

Agent call:
- `subagent_type`: `general-purpose`
- `model`: `sonnet` — artifact generation translates a defined ticket into structured files; Opus-grade planning is not needed here and is reserved for the orchestrator.
- `description`: `Generate opsx artifacts for <change-name>`
- `prompt`: rendered contents of `subagent-prompts/ff.md` with placeholders substituted.

Wait for the subagent to return, then **verify the actual artifacts on disk** (`ls openspec/changes/<change-name>/`, spot-read `proposal.md` and `tasks.md`) before continuing. The subagent's summary describes intent, not necessarily what landed.

### 5. Commit the scaffold

Stage the new `openspec/changes/<change-name>/` directory and commit:
```
chore(task2): scaffold <change-name>
```
Use a HEREDOC for the message and include the standard `Co-Authored-By` trailer per the repo commit protocol.

### 6. Implement via /opsx:apply (subagent)

Spawn a `general-purpose` subagent via the **Agent** tool to drive `/opsx:apply` for `<change-name>`. The subagent runs the full TDD loop and commits along the way; the full self-contained prompt (TDD discipline, tooling commands, pre-commit gate, comment-discipline, scope rules, report-back schema) lives at `.claude/skills/new_task2/subagent-prompts/apply.md`. **Read that file**, substitute the placeholders (`{{change-name}}`, `{{branch}}`), and pass the rendered string as the agent's `prompt`.

Agent call:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `description`: `Apply opsx change <change-name>`
- `prompt`: rendered contents of `subagent-prompts/apply.md` with placeholders substituted.

Wait for the subagent to return, then **verify the work on disk**: `git log --oneline task2/<change-name> ^master`, re-run the pre-commit gate yourself, and read `tasks.md` to confirm checkboxes match what the subagent claims. If anything is off, address it in the main thread before continuing.

### 7. Verify (subagent)

Once `tasks.md` is fully checked off, spawn a `general-purpose` subagent via the **Agent** tool to run `/opsx:verify` and close any gaps it surfaces. The full self-contained prompt lives at `.claude/skills/new_task2/subagent-prompts/verify.md`. **Read that file**, substitute the placeholders (`{{change-name}}`, `{{branch}}`), and pass the rendered string as the agent's `prompt`.

Agent call:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `description`: `Verify opsx change <change-name>`
- `prompt`: rendered contents of `subagent-prompts/verify.md` with placeholders substituted.

Wait for the subagent to return, then re-run `/opsx:verify` yourself in the main thread to confirm it really is clean. If any gap remains, decide whether to re-invoke the subagent or handle it directly.

### 8. Simplify

Invoke the `/simplify` skill scoped to the diff introduced on this branch. Focus on:
- **Reuse** — collapse duplication with existing `task2/` helpers; do not create new abstractions for hypothetical callers.
- **Quality** — naming, dead code, ruff cleanliness.
- **Efficiency** — obvious wasted work in hot paths (locator pipeline, observation building).

**Right-size the review.** The `/simplify` skill defaults to fanning out three parallel subagents (reuse / quality / efficiency). For small diffs (under ~150 changed lines, e.g. a single-module ticket like #23 CDP cache), the orchestrator can do the same review inline and apply fixes directly — skip the fan-out. For larger diffs (multi-module, eval changes, scoring overhauls) keep the three parallel agents, since the cost of missing a finding outweighs the subagent overhead.

**Watch for recurring patterns this loop has produced before.** The catalog lives at `.claude/skills/new_task2/simplify-patterns.md`. **Read that file** at this step (not at the top of the run — keep it out of the orchestrator's prompt until it's actually needed) and check the diff against every entry. The catalog is append-mostly: when a new pattern shows up across two or more tickets, add it there rather than re-deriving it next time.

Apply the simplifier's suggestions only where they hold under the existing tests. From `task2/`, re-run the full pre-commit gate (`uv run ruff format . && uv run ruff check . && uv run pytest`) to confirm green.

Commit the cleanup:
```
refactor(task2): simplify <change-name> per review
```

### 9. Smoke test the agent API

Before opening a PR, run the end-to-end smoke test against a freshly booted API server. This is the last gate that catches integration failures the unit tests cannot — server boot, real Playwright session, real LLM at `http://localhost:8090`, real `/tasks` round-trip.

From the repo root:
```bash
bash task2/smoke_test.sh
```

The script boots `uv run uvicorn api.server:app` on `127.0.0.1:8765`, posts a task ("Open https://example.com and return the H1 text"), polls until terminal status, and exits 0 only when status is `succeeded` or `unverified`. Server log is at `/tmp/task2-smoke-api.log` if anything goes wrong.

**Known harmless warnings.** The smoke script currently emits `[smoke] WARN: trace is empty (event wiring lands in ticket #20)` and `totals: { steps: 0, llm_calls: 0, ... }` because the run-level event wiring is tracked under ticket #20. This is **not** a regression — it is the pre-existing state until ticket #20 lands. Surface it once in the PR's "Notes for reviewer" rather than treating it as a smoke failure or extending the regression-test loop.

**On pass:** proceed to Step 10.

**On fail:** do not push. The smoke test failing means production-path behavior regressed even though `pytest` and `/opsx:verify` were green — that gap itself is a bug that needs a regression test. Loop back:

1. Read `/tmp/task2-smoke-api.log` and the smoke output to identify the failure mode (server boot, task creation, run loop, trace, terminal status).
2. **Extend the test surface first.** Add a failing test under `task2/tests/` that reproduces the smoke failure at unit/integration granularity. Commit: `test(task2): regression for <smoke failure mode>`. This is the TDD red step — without it, fixing the production code is not understood.
3. Re-run **Step 7 (Verify)** — re-invoke `/opsx:verify` (in the main thread or via a subagent) and close every gap it surfaces, including the new failing test.
4. Re-run **Step 8 (Simplify)** on the resulting diff.
5. Re-run `bash task2/smoke_test.sh`.
6. Repeat until the smoke test passes. If it loops more than twice without convergence, **stop and report** to the user — there is a design-level mismatch that the loop will not resolve.

Never push or open a PR with a failing smoke test. Never weaken the smoke test to make it pass.

### 10. Push and open a pull request

Push the branch and open a PR against `master` using `gh`. **Read `.github/PULL_REQUEST_TEMPLATE.md` from the repo at this step** (with the `Read` tool) and use it as the literal skeleton for the PR body — do not rely on a hardcoded copy here, since the template evolves. Fill in every section it contains rather than leaving placeholder comments.

Section guidance (apply to whichever sections the current template defines):

- **Task** — `task2`.
- **Summary** — 1–3 bullets describing what the ticket adds, grounded in the ticket text from `task2/plan.md`.
- **Why** — the ticket motivation / failing test that drove the change.
- **Before / After Diagram** (if present) — Mermaid (preferred — GitHub renders it) or ASCII showing the pre- and post-PR state. Keep it scoped to what this PR changed (e.g. a new module in the locator pipeline, a new step in the agent loop, a changed observation schema). Do not leave the empty skeleton from the template.
- **TDD checklist** — every box checked (red-first commit, `uv run pytest` green, `uv run ruff check .` clean, `uv run ruff format --check .` clean, no scope creep).
- **OpenSpec** — `openspec/changes/<change-name>/`.
- **Notes for reviewer** — anything non-obvious, deferred follow-ups, or `/opsx:verify` gaps that were intentionally left.

Workflow:

1. `Read` `.github/PULL_REQUEST_TEMPLATE.md` to get the current skeleton.
2. Fill it in with the values for this change.
3. Write the rendered body to a temp file (e.g. `/tmp/pr-body-<change-name>.md`) so the HEREDOC stays clean even with backticks / Mermaid fences.
4. Push and create the PR:

```bash
git push -u origin task2/<change-name>
gh pr create --base master \
  --title "feat(task2): <ticket title>" \
  --body-file /tmp/pr-body-<change-name>.md
```

If `gh pr create` fails because the branch already has an open PR, run `gh pr view --json url -q .url` and reuse that URL in the final report instead of opening a duplicate. If `gh` is not authenticated, stop and ask the user to run `gh auth login` rather than attempting workarounds.

Capture the returned PR URL for the final report. Do **not** mark the PR ready-for-review-as-merge — leave merge to the user after `/opsx:archive`.

### 11. Capture outstanding follow-ups in `task2/plan.md`

If any **outstanding follow-ups** surfaced during this run — design issues deferred from `/opsx:apply` or `/opsx:verify`, smoke-test gaps that pointed at adjacent code, scope-creep items consciously left out, or TODOs uncovered by `/simplify` — record them as new TDD tickets so a future `/new_task2` invocation can pick them up. Do **not** carry them only in the PR description or the conversation; the durable record lives in `task2/plan.md`.

What counts as a follow-up worth recording:
- A concrete behavior gap with a plausible failing test (TDD-shaped).
- A refactor that was out of scope for this ticket but is now clearly worth doing.
- A design problem `/opsx:apply` flagged and stopped on, that you resolved by deferring rather than fixing in-scope.

What does **not** belong in `plan.md`:
- One-off chores already captured in commits.
- Speculative ideas without a test surface.
- Anything already covered by an existing TDD ticket — extend that ticket's text instead of adding a duplicate.

Procedure:

1. Open `task2/plan.md` and find the `## TDD tickets` numbered list near the bottom. Note the highest existing ticket number.
2. For each follow-up, append a new entry continuing the numbering. Match the style of existing tickets: a bold lead (module path or short title), a one-sentence description of the gap, and then concrete acceptance criteria / tests phrased the same way as nearby entries (e.g. ticket 23 `CDP session reuse in observe.build_observation` for shape).
3. Each ticket must be self-contained — a fresh `/new_task2` run with no conversation context should be able to pick it up. Reference file paths and existing symbols rather than "the thing we discussed."
4. If a follow-up overlaps an existing ticket (e.g. you found another sub-case of ticket N), edit that ticket's text rather than adding a new line; do not create silent duplicates.

Commit the plan update on its own, on the same branch, then push so the open PR picks it up:

```bash
cd task2 && uv run ruff format . && uv run ruff check . && uv run pytest && cd ..
git add task2/plan.md
git commit -m "$(cat <<'EOF'
docs(task2): record follow-ups surfaced by <change-name>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

The pre-commit gate still applies even though only `plan.md` changed — never `--no-verify`. If you also need to update the PR body to reference the new ticket numbers, do it with `gh pr edit --body-file ...` reusing the temp file from Step 10.

If there are zero follow-ups, skip this step entirely — do not create an empty commit and do not invent items to record.

### 12. Final report

Print a short summary to the user:
- Branch name.
- Ticket implemented (number + title).
- Change directory.
- Test + ruff status (pass/clean).
- Verify status (clean / commits added).
- Simplify status (clean / commits added).
- Smoke test status — verify and simplify always run before this; report `pass` (first run) or `pass after N loops` if Step 9's regression-test → verify → simplify → re-run-smoke loop fired (Step 9 explicitly re-invokes Steps 7–8). Never word this as "no verify/simplify needed" — those are mandatory steps, not optional ones bypassed by a green smoke test.
- PR URL.
- Outstanding follow-ups: either "none" or the numbered list of new tickets appended to `task2/plan.md` in Step 11 (with their numbers).
- Suggested next step: `/opsx:archive <change-name>` (do **not** archive automatically).

## Guardrails

- **Do not skip the red step.** Every new behavior must start with a failing test that fails for the right reason.
- **Do not `git commit --no-verify`.** If a hook fails, fix the underlying issue and create a new commit.
- **Do not switch branches or rebase** without user confirmation.
- **Push only the dev branch** created in Step 2 (Step 10). Never push to `master` directly, never `--force` push.
- **Smoke test must pass before push.** A failing `task2/smoke_test.sh` blocks the PR; fix forward through Step 9's loop (regression test → verify → simplify → re-run smoke), never weaken or skip the smoke test.
- **Do not archive the change.** Archiving is the user's call after they review the branch / PR.
- If `/opsx:apply` or `/opsx:verify` blocks on ambiguity, stop and ask — do not guess past a design question.
- Honor `task2/`-local `CLAUDE.md` if present and the repo-root `CLAUDE.md` (TDD, `uv`, `ruff`, configurable LLM base URL).
