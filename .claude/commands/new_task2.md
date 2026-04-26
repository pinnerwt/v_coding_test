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

Match archived/active change names against the TDD ticket list to determine the **lowest-numbered ticket** that is not yet done. If unsure, use the **AskUserQuestion** tool to confirm with the user before proceeding.

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

If the working tree is dirty, **stop and ask** the user how to proceed — do not stash or discard.

### 3. Scaffold the OpenSpec change

Invoke the `/opsx:new` skill with the change name (kebab-case derived above). This creates `openspec/changes/<change-name>/` with the default schema.

### 4. Generate all artifacts (subagent)

Spawn a `general-purpose` subagent via the **Agent** tool to run `/opsx:ff` and produce every artifact required for `apply` (typically `proposal.md`, `design.md`, `tasks.md`, `specs/...`). The subagent has no conversation context, so the prompt must be self-contained.

Agent call:
- `subagent_type`: `general-purpose`
- `model`: `sonnet` — artifact generation translates a defined ticket into structured files; Opus-grade planning is not needed here and is reserved for the orchestrator.
- `description`: `Generate opsx artifacts for <change-name>`
- `prompt`: include all of the following so the subagent can run autonomously:
  - The exact change name (kebab-case, derived in Step 1).
  - The ticket number, title, and full ticket text from `task2/plan.md`.
  - Instruction: "Invoke the `/opsx:ff` skill on `<change-name>`. Do not commit or push. Do not implement code — artifacts only."
  - Grounding sources to read before drafting:
    - `task2/plan.md` (ticket acceptance criteria).
    - `task2/CLAUDE.md` and the rest of `task2/` for code conventions and existing structure.
    - Repo-root `CLAUDE.md` (TDD non-negotiable, `uv` + `ruff` tooling, no hardcoded LLM provider).
  - Required report back: list of files created under `openspec/changes/<change-name>/`, plus any open questions or assumptions made.

Wait for the subagent to return, then **verify the actual artifacts on disk** (`ls openspec/changes/<change-name>/`, spot-read `proposal.md` and `tasks.md`) before continuing. The subagent's summary describes intent, not necessarily what landed.

### 5. Commit the scaffold

Stage the new `openspec/changes/<change-name>/` directory and commit:
```
chore(task2): scaffold <change-name>
```
Use a HEREDOC for the message and include the standard `Co-Authored-By` trailer per the repo commit protocol.

### 6. Implement via /opsx:apply (subagent)

Spawn a `general-purpose` subagent via the **Agent** tool to drive `/opsx:apply` for `<change-name>`. The subagent runs the full TDD loop and commits along the way; it has no conversation context, so embed everything it needs in the prompt.

Agent call:
- `subagent_type`: `general-purpose`
- `model`: `sonnet` — TDD implementation is the canonical Sonnet workhorse task (Anthropic Advisor Strategy: Opus plans/reviews, Sonnet executes). Cheaper, faster, and benchmark-comparable on code-gen following an existing plan.
- `description`: `Apply opsx change <change-name>`
- `prompt`: must include:
  - The exact change name and the path `openspec/changes/<change-name>/`.
  - The current branch name (`task2/<change-name>`) and instruction: "Stay on this branch. Do not switch branches, rebase, push, or open a PR — those are handled outside this subagent."
  - Instruction: "Invoke the `/opsx:apply` skill on `<change-name>` and drive every task in `tasks.md` to completion under TDD discipline (red → green → refactor; tests live under `task2/tests/`)."
  - **Tooling** — every command runs from the `task2/` directory:
    - One-time setup if not already done: `uv sync && uv run playwright install chromium`.
    - Tests: `uv run pytest`.
    - Lint: `uv run ruff check .` (auto-fix with `uv run ruff check --fix .` only when safe).
    - Format: `uv run ruff format .`.
  - **Per red-green-refactor cycle:**
    1. **Red** — write the failing test, run `uv run pytest <path-to-new-test>`, confirm it fails for the expected reason. Commit: `test(task2): <what the new failing test covers>`.
    2. **Green** — minimal implementation. Run `uv run pytest` until green. Commit: `feat(task2): <what now works>`.
    3. **Refactor** (optional, only while green). Re-run `uv run pytest` after each meaningful edit. Commit: `refactor(task2): <what changed>`.
  - **No comments or docstrings in production code.** Write zero `#` comments and zero docstrings (module, class, or function) in any file under `task2/` that is not a test. Tests may have a single-line docstring only when it materially clarifies intent. Rationale: the `/simplify` pass strips them anyway, so writing them burns tokens for no kept output. Rely on clear naming. The only exception is a one-line comment explaining a non-obvious *why* (hidden constraint, workaround, surprising invariant) — never *what* the code does.
  - **Pre-commit gate (mandatory before every commit):**
    ```bash
    cd task2
    uv run ruff format .
    uv run ruff check .
    uv run pytest
    ```
    All three must be clean. Stage any `ruff format` rewrites into the same commit. Never commit with failing tests or ruff errors. Never use `--no-verify`.
  - Keep commits small enough that the diff matches the message. Do not bundle unrelated changes.
  - If a task surfaces a design problem, **stop and report back** (per `/opsx:apply` guardrails) instead of papering over it.
  - Honor `task2/CLAUDE.md` and the repo-root `CLAUDE.md` (TDD, `uv`, `ruff`, configurable LLM base URL).
  - Required report back: list of commits made (sha + subject), final `pytest` / `ruff` status, any tasks left unchecked in `tasks.md`, and any design questions that surfaced.

Wait for the subagent to return, then **verify the work on disk**: `git log --oneline task2/<change-name> ^master`, re-run the pre-commit gate yourself, and read `tasks.md` to confirm checkboxes match what the subagent claims. If anything is off, address it in the main thread before continuing.

### 7. Verify (subagent)

Once `tasks.md` is fully checked off, spawn a `general-purpose` subagent via the **Agent** tool to run `/opsx:verify` and close any gaps it surfaces.

Agent call:
- `subagent_type`: `general-purpose`
- `model`: `sonnet` — verification follows a defined rubric (`/opsx:verify` output → close gap → re-run); the orchestrator re-runs the verifier itself in the main thread for the final judgment call.
- `description`: `Verify opsx change <change-name>`
- `prompt`: must include:
  - The change name and the path `openspec/changes/<change-name>/`.
  - The branch name (`task2/<change-name>`) and instruction: "Stay on this branch. Do not switch branches, push, or open a PR."
  - Instruction: "Invoke `/opsx:verify` on `<change-name>`. Address every gap it reports — **extend tests first** when behavior is missing, then code. Re-run `/opsx:verify` until it is clean."
  - Commit conventions for fixes:
    - `fix(task2): address verify feedback for <change-name>` for code fixes.
    - `test(task2): <what the new test covers>` if the change is purely additional tests.
  - Pre-commit gate (same as Step 6) must pass before every commit; never `--no-verify`.
  - **No comments or docstrings** in any non-test file. If `/opsx:verify` flags a missing comment/docstring, push back - close the gap with a clearer name or a test, not a comment. Same rule as Step 6: `/simplify` will strip them, so don't write them in the first place.
  - Required report back: the final `/opsx:verify` output, list of commits added, and a confirmation that the verifier reports zero gaps.

Wait for the subagent to return, then re-run `/opsx:verify` yourself in the main thread to confirm it really is clean. If any gap remains, decide whether to re-invoke the subagent or handle it directly.

### 8. Simplify

Invoke the `/simplify` skill scoped to the diff introduced on this branch. Focus on:
- **Reuse** — collapse duplication with existing `task2/` helpers; do not create new abstractions for hypothetical callers.
- **Quality** — naming, dead code, ruff cleanliness.
- **Efficiency** — obvious wasted work in hot paths (locator pipeline, observation building).

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

### 11. Final report

Print a short summary to the user:
- Branch name.
- Ticket implemented (number + title).
- Change directory.
- Test + ruff status (pass/clean).
- Smoke test status (pass, plus how many verify/simplify loops it took if >1).
- PR URL.
- Outstanding follow-ups, if any.
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
