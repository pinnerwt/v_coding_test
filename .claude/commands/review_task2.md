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
- **Cross-check against the change's OpenSpec docs.** If the branch has an active change directory under `openspec/changes/<change>/`, grep its `proposal.md`, `spec.md`, `design.md`, and `tasks.md` for any mention of the symbols/contracts codex flagged. A "remove this dead fallback" finding may collide with a `Requirement: Fallback when X` in the spec — that mismatch is itself a finding (either restore the fallback OR update the spec to match the simpler contract; pick one and document why). Don't skip `proposal.md`: the "What Changes" bullets there often make stronger claims than the spec scenarios (e.g. "seq is assigned by the writer") and drift the moment you narrow scope.
- **Recognize codex blind spots.** Codex reads only the diff you piped in. It does NOT see prior iterations' decisions, the OpenSpec change docs, or earlier conversation context. If a finding repeats a complaint you already resolved by tightening a spec or by deliberate design choice in an earlier iteration, treat it as (c) invalid — not as a regression. Common case: codex re-flags a fallback you removed and a spec you updated to match; the spec change itself is the resolution.
- **Recognize "tracked follow-up ticket" findings.** When codex flags concern X and the spec, proposal, PR notes, or `task2/plan.md` already says "X is tracked under ticket #N" (or "out of scope here, see ticket #N"), that is prima facie (b) deferred — not (a). Don't re-implement deferred work just because codex re-surfaces it; the deferral is the documented decision. By iteration 3-4 codex often *acknowledges* this itself once the plan.md follow-up is in the diff (`/new_task2` step 11 puts it there) — easy convergence signal.
- **Anchor new (b) deferrals as plan.md tickets *during* the iteration.** When codex surfaces a concern that is genuinely valid but out-of-scope and there is *not yet* a tracking ticket for it, append a new numbered ticket to the **TDD tickets** section of `task2/plan.md` as part of this iteration's plan (separate `docs(task2): record <X> as ticket #N` commit alongside the (a) fixes). This is faster than waiting for `/new_task2` step 11 of a future ticket and turns iteration N+1's likely re-flag of the same finding into an automatic (b) deferral. The ticket text should name the symbol/file codex cited and the specific contract gap, so a future implementer can pick it up cold. Confirmed working pattern: in PR #52, ticket #29 (`TraceWriter.iter_events`) was added during review iteration 1; iteration 2's codex re-flagged the same private-trace-internals concern, and it was immediately categorized (b) by reference to the just-added ticket.
- **Test-quality findings are usually (a) and small.** Codex catches semantic drift between a test's name and its body (e.g. `test_X_backward_compat_missing_Y_fields` that loads a fixture which already contains `Y`). These typically need only a one-test edit — replace the fixture read with a synthetic in-memory dict that genuinely omits the named fields, and add an assertion that the default-path output is correct. Treat as (a), TDD-shape it (the new dict shape *is* the new test surface), and don't touch the production code being defaulted in.
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

**Prefer per-iteration commits over one bundled commit at the end.** When iteration N produces a cohesive set of fixes that resolves a distinct codex topic (e.g. "apply review fixes", "sync tasks.md with narrowed spec", "align proposal.md with as-built behavior"), commit it at the end of that iteration with a topic-specific subject. The next iteration's `git diff master` then includes the prior commit, so codex sees the full state and the audit trail explains *why each iteration happened*. This is what worked in practice; the older "single bundled commit" rule made the squash log opaque.

Subject conventions for the per-iteration pattern:
- `chore(task2): apply codex review fixes` — the iteration that addresses the bulk of (a) findings.
- `chore(task2): sync tasks.md with narrowed spec scenarios` — when the iteration only updates tasks.md/checklist text to match a spec narrowed in an earlier iteration.
- `chore(task2): align proposal.md with as-built <X> behavior` — when the iteration only fixes proposal.md drift.
- `chore(task2): drop redundant <X> in <test-or-file>` — when the iteration only removes a single now-unreachable branch, redundant `try/except`, or dead assertion that codex flagged once the surrounding contract was tightened in a prior iteration.
- `docs(task2): record <X> as ticket #N (deferred follow-up)` — when the iteration only appends a new TDD ticket to `task2/plan.md` to anchor a (b)-deferred concern that codex re-surfaces. Pairs with the "anchor as plan.md ticket" pattern in step 3: the commit makes the deferral durable so the next iteration's categorization (and any future codex pass) can cite the ticket number as proof of intent.

Each commit:
- Stages only the relevant files (do **not** `git add -A` blindly — exclude `.venv/`, scratch files, anything not tied to the review fixes).
- Uses a HEREDOC for the message body listing each finding addressed.
- Includes the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
- Does NOT push, amend, or use `--no-verify`.

After the loop exits, check `git status --porcelain` once more:

- If clean (because every iteration already committed): print `review_task2: <N> commits, <M> iterations` and stop.
- If dirty (the loop made an edit you forgot to commit): stage and commit it now with the appropriate topic-specific subject.

**Single-bundled-commit fallback.** If iterations all addressed the same topic (no distinct narrowing/sync passes), one `chore(task2): apply codex review fixes` commit at step 8 with a multi-bullet body is fine. The rule is: subject should describe the diff, not the loop.

## Notes

- The orchestrator owns the plan; the subagent owns the keystrokes. If you find yourself writing "figure out X" or "decide whether Y" in the plan, stop and decide it yourself first.
- Never disable or weaken tests to make the loop converge. If a test is genuinely wrong, that is its own commit with its own reasoning, surfaced to the user.
- If the working tree is already dirty when the command starts, **stop and ask** the user how to proceed (commit / stash / discard) before running codex — mixing pre-existing changes with review fixes corrupts the audit trail.
- **Per-iteration commits are fine — even preferred — when each iteration resolves a distinct topic.** See step 8. Use `git diff master` (not `git diff master...HEAD`) so each iteration's review sees both committed and uncommitted state from prior iterations.
- **Working dir hygiene.** `cd <task-dir>` persists across `Bash` tool calls, but absolute paths (`uv run pytest --rootdir /home/pgi/vici/task2 ...`) or `(cd /home/pgi/vici/task2 && ...)` subshells are safer when later calls assume repo root. A previous `cd task2` makes a later `cd task2` fail with "no such file or directory".
- **Codex repeats blind-spot findings across iterations.** Codex sees only the piped diff, not your prior reasoning. Iteration 2 may flag the same thing iteration 1 resolved (e.g. "you removed a fallback the spec requires" after you've also updated the spec to drop that requirement). That's why step 3 cross-checks against the OpenSpec change docs and tracks "already resolved" as a (c) category.
- **Iterations 3+ usually converge as no-op.** If iteration 2 ended in spec/doc edits only, iteration 3's codex run typically replays the same complaints and is rejected via (b)/(c). Treat empty-after-categorization as the natural stop signal — don't keep running iterations to chase codex into agreeing with you. 4 iterations is normal when codex repeatedly flags the same deferred concern; the abort-at-5 thrash guard is the real ceiling.

- **Adjacent-artifact drift cascades across iterations.** Each time you narrow a spec.md scenario in iteration N (e.g. drop a cross-kind ordering claim because it's deferred), the next iteration's codex pass tends to surface the *adjacent* artifact (`tasks.md`, `proposal.md`, sometimes `design.md`) still asserting the wider claim. This isn't iteration-N's bug — it's expected drift. To shorten the loop, when you fix spec.md in any iteration, immediately grep `tasks.md` / `proposal.md` for the same removed phrase and update them in the *same* iteration's commit, not wait for codex to flag it next time. Common drift sources after a scenario narrowing:
    - `tasks.md` items that name the old test-name (renamed in spec) or describe the old assertion.
    - `proposal.md` "What Changes" bullets that paraphrase the old requirement (e.g. "seq is assigned by the writer" when implementation now uses a local counter).
    - `design.md` flow diagrams that show the old ordering.
