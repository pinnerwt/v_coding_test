---
name: "Review Task2"
description: Review the current branch's diff against master with codex, write an implementation plan from the findings, dispatch a sonnet subagent to execute the plan, run /simplify, and loop until the working tree is clean. Commit any changes produced before exiting.
category: Workflow
tags: [task2, review, automation]
---

Iteratively review the current branch against `master` using `codex`. The orchestrator (you, the Opus session running this command) reads each codex report, **writes the implementation plan**, and hands the plan to a sonnet subagent for execution. After the subagent returns, run `/simplify`. Repeat until the loop produces no code changes. Commit any work the loop produced before exiting.

The split is: **Opus plans, Sonnet implements.** Do not delegate the diagnostic / planning step — Sonnet only receives prescriptive instructions.

## Loop

Repeat the steps below until the **stop condition** is met. Track the iteration count; abort with a clear message if it exceeds 5 (something is likely thrashing).

### 1. Snapshot the pre-iteration HEAD

Capture the current commit so we can detect whether this iteration changed anything:

```bash
git rev-parse HEAD
git status --porcelain
```

Save the HEAD SHA and the porcelain output as `before_sha` / `before_status` for this iteration.

### 2. Run codex review

Codex's bwrap sandbox cannot read the repo on this host (errors with `bwrap: loopback: Failed RTM_NEWADDR`). Pipe the diff in explicitly via stdin. Use `git diff master` (NOT `git diff master...HEAD`): the working tree may have uncommitted iteration changes that we want included in the review.

```bash
git diff master > /tmp/effective.diff
cat /tmp/effective.diff | codex exec "Review the following diff against master for correctness, regressions, test coverage gaps, and TDD discipline. Be specific about file/line. The diff follows on stdin."
```

Capture the full stdout — this is the review report.

**Failure handling, in order:**
- **Auth / model error** (e.g. `invalid_request_error: The 'X' model is not supported when using Codex with a ChatGPT account`): stop and surface to the user. Do not loop. Do not silently switch models — `~/.codex/config.toml` is the user's choice.
- **Missing binary**: stop and surface.
- **Trailing `ERROR codex_core::session: failed to record rollout items: thread ... not found`**: this is non-fatal noise emitted after a successful review. If review content was produced before this line, accept the review and proceed. The bash exit code may still be non-zero; that alone does NOT mean the review failed.
- **No review content at all** (only error lines): stop and surface.

### 3. Read the report and decide

Read the codex report carefully. If it explicitly reports no issues / nothing to change (e.g. "no findings", "looks good", empty issue list), **skip to step 6** with `iteration_changed=false`.

Otherwise, you (the orchestrator) must now do the diagnostic work yourself before dispatching anyone:

- Read the relevant files cited by codex with the `Read` tool. Do not trust the report blindly — verify each finding against the current code.
- **Cross-check against the change's OpenSpec docs.** If the branch has an active change directory under `openspec/changes/<change>/`, grep its `spec.md`, `design.md`, and `tasks.md` for any mention of the symbols/contracts codex flagged. A "remove this dead fallback" finding may collide with a `Requirement: Fallback when X` in the spec — that mismatch is itself a finding (either restore the fallback OR update the spec to match the simpler contract; pick one and document why).
- **Recognize codex blind spots.** Codex reads only the diff you piped in. It does NOT see prior iterations' decisions, the OpenSpec change docs, or earlier conversation context. If a finding repeats a complaint you already resolved by tightening a spec or by deliberate design choice in an earlier iteration, treat it as (c) invalid — not as a regression. Common case: codex re-flags a fallback you removed and a spec you updated to match; the spec change itself is the resolution.
- Categorize each finding as: (a) valid and in-scope, (b) valid but out-of-scope for this branch (defer), or (c) invalid (codex misread / didn't see context). Drop (b) and (c) from the plan.
- **If after categorization there are zero (a) findings**, the plan is empty. Skip step 5 (no subagent dispatch) and proceed to step 6 with `iteration_changed=false`. This is distinct from codex saying "no findings" but produces the same loop outcome.
- For each (a) finding, decide the concrete fix: which file, which lines, which tests to add or update first (TDD), and any quality gate the implementer must rerun.

### 4. Write the implementation plan

Produce a self-contained plan as a single message that the sonnet subagent will execute verbatim. The plan MUST include:

- **Context block** — repo root `/home/pgi/vici`, current branch, the relevant task directory (e.g. `task2/`), TDD is non-negotiable (`CLAUDE.md`), Python tooling is `uv` + `ruff`. No mocking the LLM, no `--no-verify`, no weakening tests to converge.
- **Numbered task list** — one entry per accepted finding. For each:
  - **File(s)** to touch (absolute paths).
  - **Failing test first** — exact test file + test name to add or modify, with the assertion it should make. If the finding is purely cosmetic (lint, dead code, doc), say "no test needed" and explain why.
  - **The fix** — what to change, expressed as the desired post-state, not a diff. Be specific enough that a competent implementer cannot misinterpret it; do not over-prescribe stylistic detail.
  - **Acceptance check** — the command(s) the implementer must run to confirm the fix (e.g. `uv run pytest task2/tests/test_foo.py::test_bar` from the task dir).
- **Final quality gates** — `uv run ruff check .` and the full `uv run pytest` from the task directory. Both must pass before the subagent reports done.
- **Out of scope (do not touch)** — list the (b) deferred findings so the subagent does not freelance on them.
- **Output contract** — the subagent should return: per-task status (done / blocked + reason), the lint/test command outputs, and a one-line summary per task suitable for a commit message bullet.

Do **not** include the raw codex report in the plan — pass only your distilled, validated instructions. The subagent should not have to re-do the diagnostic work.

### 5. Spawn the implementer subagent

Use the **Agent** tool with:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `description`: `Implement codex review plan`
- `prompt`: the plan from step 4, verbatim.

Wait for the subagent to return. Verify with `git status --porcelain` whether files actually changed; record `subagent_changed=true`/`false`. If the subagent reports a task as blocked, surface that to the user after the loop — do not silently retry the same plan.

**Verify "pre-existing failures" claims.** If the subagent's report says some tests "were already failing before my changes" or "are pre-existing failures unrelated to this work", DO NOT trust that without checking. Stash the subagent's edits and run the same tests on the clean baseline:

```bash
git stash
(cd <task-dir> && uv run pytest <claimed-pre-existing-test-file>)
git stash pop
```

If those tests pass on the baseline, the subagent caused the regression and the plan needs another step. Common cause in this repo: tightening a contract (e.g. removing a `getattr(..., default)` fallback) breaks duck-typed test stubs in unrelated files (e.g. `agent/replay.py:StubBrowser`). Fix the stub, don't roll back the contract.

### 6. Run /simplify

Invoke the **simplify** skill on the working tree. This may further modify files. After it returns, note whether anything changed since the start of step 6.

**Avoid redundant /simplify dispatches.** If this iteration produced no new working-tree changes since the last `/simplify` pass (i.e. step 5 was skipped or made no edits, and the diff is identical to what `/simplify` already reviewed last iteration), don't re-dispatch the three parallel review agents — `/simplify`'s findings on the same diff will recur and waste tokens. Instead, do a quick self-review of any doc-only deltas and confirm clean. Re-dispatch the full skill when production code or tests changed.

### 7. Stop condition

Re-check the working tree:

```bash
git rev-parse HEAD
git status --porcelain
```

The iteration produced no code changes if **all** of the following hold:
- `HEAD` is unchanged from `before_sha`.
- `git status --porcelain` is identical to `before_status`.
- The subagent in step 5 was skipped or reported no edits, AND `/simplify` made no edits.

If unchanged → **exit the loop**.

Otherwise → loop back to step 1.

### 8. Commit any pending changes

After the loop exits, check `git status --porcelain` once more.

- If clean: print "review_task2: no changes" and stop.
- If dirty: stage the relevant files (do **not** `git add -A` blindly — exclude `.venv/`, scratch files, anything not tied to the review fixes) and create a single commit:

  ```
  chore(task2): apply codex review fixes

  - <one-line summary per finding addressed>
  ```

  Use a HEREDOC for the message. Do not push. Do not amend. Do not use `--no-verify`.

## Notes

- The orchestrator owns the plan; the subagent owns the keystrokes. If you find yourself writing "figure out X" or "decide whether Y" in the plan, stop and decide it yourself first.
- Never disable or weaken tests to make the loop converge. If a test is genuinely wrong, that is its own commit with its own reasoning, surfaced to the user.
- If the working tree is already dirty when the command starts, **stop and ask** the user how to proceed (commit / stash / discard) before running codex — mixing pre-existing changes with review fixes corrupts the audit trail.
- **Don't commit between iterations.** Working-tree changes accumulate across the loop and are committed once at step 8. Use `git diff master` (not `git diff master...HEAD`) so each iteration's review sees both committed and uncommitted state.
- **Working dir hygiene.** `cd <task-dir>` persists across `Bash` tool calls, but absolute paths (`uv run pytest --rootdir /home/pgi/vici/task2 ...`) or `(cd /home/pgi/vici/task2 && ...)` subshells are safer when later calls assume repo root. A previous `cd task2` makes a later `cd task2` fail with "no such file or directory".
- **Codex repeats blind-spot findings across iterations.** Codex sees only the piped diff, not your prior reasoning. Iteration 2 may flag the same thing iteration 1 resolved (e.g. "you removed a fallback the spec requires" after you've also updated the spec to drop that requirement). That's why step 3 cross-checks against the OpenSpec change docs and tracks "already resolved" as a (c) category.
- **Iterations 3+ usually converge as no-op.** If iteration 2 ended in spec/doc edits only, iteration 3's codex run typically replays the same complaints and is rejected via (b)/(c). Treat empty-after-categorization as the natural stop signal — don't keep running iterations to chase codex into agreeing with you.
