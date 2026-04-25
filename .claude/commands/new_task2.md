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

### 4. Generate all artifacts

Invoke the `/opsx:ff` skill with the same change name. This produces every artifact required for `apply` (typically `proposal.md`, `design.md`, `tasks.md`, `specs/...`).

While drafting artifacts, ground them in:
- The ticket text from `task2/plan.md` (acceptance criteria for the test).
- `task2/CLAUDE.md` and the rest of `task2/` for code conventions and existing structure.
- The repo `CLAUDE.md` (TDD non-negotiable, `uv` + `ruff` tooling, no hardcoded LLM provider).

### 5. Commit the scaffold

Stage the new `openspec/changes/<change-name>/` directory and commit:
```
chore(task2): scaffold <change-name>
```
Use a HEREDOC for the message and include the standard `Co-Authored-By` trailer per the repo commit protocol.

### 6. Implement via /opsx:apply

Invoke the `/opsx:apply` skill on `<change-name>`. Drive each task in the tasks file to completion under TDD discipline (red → green → refactor; tests live under `task2/tests/`).

**Tooling (per `task2/README.md`)** — every command runs from the `task2/` directory:
- One-time setup if not already done: `uv sync && uv run playwright install chromium`.
- Tests: `uv run pytest`.
- Lint: `uv run ruff check .` (auto-fix with `uv run ruff check --fix .` only when safe).
- Format: `uv run ruff format .`.

**Per red-green-refactor cycle:**
1. **Red** — write the failing test, then run `uv run pytest <path-to-new-test>` and confirm it fails for the expected reason. Commit: `test(task2): <what the new failing test covers>`.
2. **Green** — minimal implementation. Run the full suite `uv run pytest` until green. Commit: `feat(task2): <what now works>`.
3. **Refactor** (optional) — only while green. Re-run `uv run pytest` after each meaningful edit. Commit: `refactor(task2): <what changed>`.

**Pre-commit gate (mandatory before every commit on this branch):**
```bash
cd task2
uv run ruff format .
uv run ruff check .
uv run pytest
```
All three must be clean. If `ruff format` rewrites files, stage those changes into the same commit. Never commit with failing tests or ruff errors, and never bypass hooks with `--no-verify`.

Keep commits small enough that the diff matches the message. Do not bundle unrelated changes.

If a task surfaces a design problem, pause and surface it (per `/opsx:apply` guardrails) instead of papering over it.

### 7. Verify

Once `tasks.md` is fully checked off, invoke the `/opsx:verify` skill on `<change-name>`. Address every gap it reports — extend tests first when behavior is missing, then code. Re-run `/opsx:verify` until clean.

Commit any fixes:
```
fix(task2): address verify feedback for <change-name>
```
or `test(task2): ...` if the change is purely test additions.

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

### 9. Final report

Print a short summary to the user:
- Branch name.
- Ticket implemented (number + title).
- Change directory.
- Test + ruff status (pass/clean).
- Outstanding follow-ups, if any.
- Suggested next step: `/opsx:archive <change-name>` (do **not** archive automatically).

## Guardrails

- **Do not skip the red step.** Every new behavior must start with a failing test that fails for the right reason.
- **Do not `git commit --no-verify`.** If a hook fails, fix the underlying issue and create a new commit.
- **Do not switch branches or rebase** without user confirmation.
- **Do not push** to the remote unless the user explicitly asks.
- **Do not archive the change.** Archiving is the user's call after they review the branch / PR.
- If `/opsx:apply` or `/opsx:verify` blocks on ambiguity, stop and ask — do not guess past a design question.
- Honor `task2/`-local `CLAUDE.md` if present and the repo-root `CLAUDE.md` (TDD, `uv`, `ruff`, configurable LLM base URL).
