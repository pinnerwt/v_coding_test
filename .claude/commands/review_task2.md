---
name: "Review Task2"
description: Review the current branch's diff against master with an Opus 4.7 reviewer subagent, write an implementation plan from the findings, dispatch a sonnet subagent to execute the plan, run /simplify, and loop until the working tree is clean. Commit any changes produced before exiting.
category: Workflow
tags: [task2, review, automation]
---

Iteratively review the current branch against `master` using an Opus 4.7 reviewer subagent. The orchestrator (you, the Opus session running this command) reads each review report, **writes the implementation plan**, and hands the plan to a sonnet subagent for execution. After the subagent returns, run `/simplify`. Repeat until the loop produces no code changes. Commit any work the loop produced before exiting.

The split is: **Opus plans, Sonnet implements.** The reviewer subagent (also Opus) produces findings only — it does not plan or write code. Do not delegate the diagnostic / planning step — Sonnet only receives prescriptive instructions.

## Loop

Repeat the steps below until the **stop condition** is met. Track the iteration count; abort with a clear message if it exceeds 5 (something is likely thrashing).

### 1. Snapshot the pre-iteration HEAD

Capture the current commit so we can detect whether this iteration changed anything:

```bash
git rev-parse HEAD
git status --porcelain
```

Save the HEAD SHA and the porcelain output as `before_sha` / `before_status` for this iteration.

### 2. Spawn the reviewer subagent

Write the diff to a file the subagent can read, then dispatch an Opus subagent scoped to **review only**. The reviewer must see only the diff — not OpenSpec docs, not prior iterations' decisions, not this conversation. That preserves the "independent second opinion" property; the orchestrator (you) cross-checks against the change docs in step 3.

Use `git diff master` (NOT `git diff master...HEAD`): the working tree may have uncommitted iteration changes that we want included in the review.

```bash
git diff master > /tmp/effective.diff
wc -l /tmp/effective.diff
```

Use the **Agent** tool with:
- `subagent_type`: `general-purpose`
- `model`: `opus`
- `description`: `Review branch diff for correctness/TDD`
- `prompt`: a self-contained brief that includes:
  - **Context**: "This diff is from the `vici` repo (path `/home/pgi/vici`), against `master`. The branch belongs to task2 (Generalized Browser Automation Agent). Repo conventions: TDD is non-negotiable (`CLAUDE.md`), Python tooling is `uv` + `ruff`, no mocking the LLM, no comments/docstrings in production code under `task2/`."
  - **The diff to review**: "The full diff is at `/tmp/effective.diff`. Read it with the Read tool before producing findings."
  - **What to review for**: correctness, regressions, test coverage gaps, TDD discipline (was the failing test plausibly written first? does each behavior have a covering test?), boundary leaks (private symbols imported across module boundaries, raw SQL outside its owning module), and dead code introduced by the diff.
  - **What NOT to do**: do not run tests, do not modify files, do not open additional repo files beyond the diff itself unless necessary to disambiguate a finding (and if you do, name the file in the finding). Produce findings only.
  - **Output contract**: a numbered list of findings. For each: file:line, severity (`blocker` / `major` / `nit`), one-sentence problem statement, and a one-sentence recommended fix. If there are no issues, say so explicitly with the literal phrase "no findings".

Capture the subagent's returned report — this is the review.

**Failure handling, in order:**
- **Tool error from the Agent call** (rate limit, auth, transport, model unavailable): stop and surface to the user. Do not loop. Do not retry silently. Do not silently switch models.
- **Subagent reports it could not read the diff**: check `/tmp/effective.diff` exists and is non-empty; if so, re-dispatch once with an explicit `Read /tmp/effective.diff first` instruction. If still failing, stop and surface.
- **Subagent returns the literal "no findings"** or an empty findings list: treat as no issues and skip to step 6 with `iteration_changed=false`.
- **Subagent returns a malformed report** (no findings list, no clear severities): re-dispatch once with a stricter output-contract reminder. If still malformed, stop and surface.

### 3. Read the report and decide

Read the reviewer's report carefully. If it explicitly reports no issues / nothing to change (e.g. "no findings", "looks good", empty issue list), **skip to step 6** with `iteration_changed=false`.

Otherwise, you (the orchestrator) must now do the diagnostic work yourself before dispatching anyone:

- Read the relevant files cited by the reviewer with the `Read` tool. Do not trust the report blindly — verify each finding against the current code.
- **Cross-check against the change's OpenSpec docs.** If the branch has an active change directory under `openspec/changes/<change>/`, grep its `proposal.md`, `spec.md`, `design.md`, and `tasks.md` for any mention of the symbols/contracts the reviewer flagged. A "remove this dead fallback" finding may collide with a `Requirement: Fallback when X` in the spec — that mismatch is itself a finding (either restore the fallback OR update the spec to match the simpler contract; pick one and document why). Don't skip `proposal.md`: the "What Changes" bullets there often make stronger claims than the spec scenarios (e.g. "seq is assigned by the writer") and drift the moment you narrow scope.
- **Verify reviewer spec citations against the actual scenario text.** When a reviewer's finding cites a spec scenario by content or quotes a spec line ("the spec scenario actually says ...", "the spec at line X says ..."), open `openspec/changes/<change>/specs/<cap>/spec.md` and read that exact scenario before accepting the categorization. Reviewers paraphrase from the diff and frequently misquote — particularly when two adjacent scenarios in the same requirement differ subtly (e.g. one asserts position before "the per-case table header row", another asserts position before "the first `| <prefix>-` row"). If the cited quote doesn't match the spec, treat the finding as (c) invalid even if the underlying critique sounds plausible. Why: confirmed in PR #71 on 2026-04-27 — iter 2's reviewer claimed the spec required a position assertion against the first `| fixture-` row; I changed the test accordingly; iter 3's reviewer flagged the same test back the other way (correctly — the relevant scenario asserts against the header row). Result was one wasted iteration cycle. How to apply: before applying any (a) fix that hinges on a quoted spec snippet, `grep -n "<quoted phrase>"` the spec file and confirm the quote exists in the scenario the reviewer named.
- **Recognize reviewer blind spots.** The reviewer subagent reads only the diff you handed it. It does NOT see prior iterations' decisions, the OpenSpec change docs, or earlier conversation context. If a finding repeats a complaint you already resolved by tightening a spec or by deliberate design choice in an earlier iteration, treat it as (c) invalid — not as a regression. Common case: reviewer re-flags a fallback you removed and a spec you updated to match; the spec change itself is the resolution.
- **Recognize "tracked follow-up ticket" findings.** When the reviewer flags concern X and the spec, proposal, PR notes, or `task2/tickets/active/` already tracks "X" (or "out of scope here, see ticket #N"), that is prima facie (b) deferred — not (a). Don't re-implement deferred work just because the reviewer re-surfaces it; the deferral is the documented decision. By iteration 3-4 the reviewer often *acknowledges* this itself once the ticket file is in the diff (`/new_task2` step 11 puts it there) — easy convergence signal.
- **Anchor new (b) deferrals as ticket files *during* the iteration.** When the reviewer surfaces a concern that is genuinely valid but out-of-scope and there is *not yet* a tracking ticket for it, write a new ticket file `task2/tickets/active/<NNN>-<slug>.md` with all required frontmatter and a body that names the symbol/file the reviewer cited and the specific contract gap, then run `uv run python task2/scripts/regen_tickets_index.py` (separate `docs(task2): file ticket #<N> — <X>` commit alongside the (a) fixes). This is faster than waiting for `/new_task2` step 11 of a future ticket and turns iteration N+1's likely re-flag of the same finding into an automatic (b) deferral. Confirmed working pattern: in PR #52, ticket #29 (`TraceWriter.iter_events`) was added during review iteration 1; iteration 2's review re-flagged the same private-trace-internals concern, and it was immediately categorized (b) by reference to the just-added ticket.
- **Test-quality findings are usually (a) and small.** Reviewers catch semantic drift between a test's name and its body (e.g. `test_X_backward_compat_missing_Y_fields` that loads a fixture which already contains `Y`). These typically need only a one-test edit — replace the fixture read with a synthetic in-memory dict that genuinely omits the named fields, and add an assertion that the default-path output is correct. Treat as (a), TDD-shape it (the new dict shape *is* the new test surface), and don't touch the production code being defaulted in.
- Categorize each finding as: (a) valid and in-scope, (b) valid but out-of-scope for this branch (defer), or (c) invalid (reviewer misread / didn't see context). Drop (b) and (c) from the plan.
- **If after categorization there are zero (a) findings**, the plan is empty. Skip step 5 (no subagent dispatch) and proceed to step 6 with `iteration_changed=false`. This is distinct from the reviewer saying "no findings" but produces the same loop outcome.
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

Do **not** include the raw reviewer report in the plan — pass only your distilled, validated instructions. The implementer subagent should not have to re-do the diagnostic work.

### 5. Spawn the implementer subagent

Use the **Agent** tool with:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `description`: `Implement review plan`
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

**Prefer per-iteration commits over one bundled commit at the end.** When iteration N produces a cohesive set of fixes that resolves a distinct review topic (e.g. "apply review fixes", "sync tasks.md with narrowed spec", "align proposal.md with as-built behavior"), commit it at the end of that iteration with a topic-specific subject. The next iteration's `git diff master` then includes the prior commit, so the reviewer sees the full state and the audit trail explains *why each iteration happened*. This is what worked in practice; the older "single bundled commit" rule made the squash log opaque.

Subject conventions for the per-iteration pattern:
- `chore(task2): apply review fixes` — the iteration that addresses the bulk of (a) findings.
- `chore(task2): sync tasks.md with narrowed spec scenarios` — when the iteration only updates tasks.md/checklist text to match a spec narrowed in an earlier iteration.
- `chore(task2): align proposal.md with as-built <X> behavior` — when the iteration only fixes proposal.md drift.
- `chore(task2): drop redundant <X> in <test-or-file>` — when the iteration only removes a single now-unreachable branch, redundant `try/except`, or dead assertion that the reviewer flagged once the surrounding contract was tightened in a prior iteration.
- `docs(task2): file ticket #<N> — <X> (deferred follow-up)` — when the iteration only writes a new ticket file to `task2/tickets/active/` to anchor a (b)-deferred concern that the reviewer re-surfaces. Pairs with the "anchor as ticket file" pattern in step 3: the commit makes the deferral durable so the next iteration's categorization (and any future review pass) can cite the ticket number as proof of intent.

Each commit:
- Stages only the relevant files (do **not** `git add -A` blindly — exclude `.venv/`, scratch files, anything not tied to the review fixes).
- Uses a HEREDOC for the message body listing each finding addressed.
- Includes the standard `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
- Does NOT push, amend, or use `--no-verify`.

After the loop exits, check `git status --porcelain` once more:

- If clean (because every iteration already committed): print `review_task2: <N> commits, <M> iterations` and stop.
- If dirty (the loop made an edit you forgot to commit): stage and commit it now with the appropriate topic-specific subject.

**Single-bundled-commit fallback.** If iterations all addressed the same topic (no distinct narrowing/sync passes), one `chore(task2): apply review fixes` commit at step 8 with a multi-bullet body is fine. The rule is: subject should describe the diff, not the loop.

## Notes

- The orchestrator owns the plan; the reviewer subagent owns findings; the implementer subagent owns the keystrokes. If you find yourself writing "figure out X" or "decide whether Y" in the plan, stop and decide it yourself first.
- Never disable or weaken tests to make the loop converge. If a test is genuinely wrong, that is its own commit with its own reasoning, surfaced to the user.
- If the working tree is already dirty when the command starts, **stop and ask** the user how to proceed (commit / stash / discard) before running the reviewer — mixing pre-existing changes with review fixes corrupts the audit trail.
- **Per-iteration commits are fine — even preferred — when each iteration resolves a distinct topic.** See step 8. Use `git diff master` (not `git diff master...HEAD`) so each iteration's review sees both committed and uncommitted state from prior iterations.
- **Working dir hygiene.** `cd <task-dir>` persists across `Bash` tool calls, but absolute paths (`uv run pytest --rootdir /home/pgi/vici/task2 ...`) or `(cd /home/pgi/vici/task2 && ...)` subshells are safer when later calls assume repo root. A previous `cd task2` makes a later `cd task2` fail with "no such file or directory".
- **The reviewer repeats blind-spot findings across iterations.** It sees only the piped diff, not your prior reasoning. Iteration 2 may flag the same thing iteration 1 resolved (e.g. "you removed a fallback the spec requires" after you've also updated the spec to drop that requirement). That's why step 3 cross-checks against the OpenSpec change docs and tracks "already resolved" as a (c) category.
- **Iterations 3+ usually converge as no-op.** If iteration 2 ended in spec/doc edits only, iteration 3's review run typically replays the same complaints and is rejected via (b)/(c). Treat empty-after-categorization as the natural stop signal — don't keep running iterations to chase the reviewer into agreeing with you. 4 iterations is normal when the reviewer repeatedly flags the same deferred concern; the abort-at-5 thrash guard is the real ceiling.

- **Adjacent-artifact drift cascades across iterations.** Each time you narrow a spec.md scenario in iteration N (e.g. drop a cross-kind ordering claim because it's deferred), the next iteration's review pass tends to surface the *adjacent* artifact (`tasks.md`, `proposal.md`, sometimes `design.md`) still asserting the wider claim. This isn't iteration-N's bug — it's expected drift. To shorten the loop, when you fix spec.md in any iteration, immediately grep `tasks.md` / `proposal.md` for the same removed phrase and update them in the *same* iteration's commit, not wait for the reviewer to flag it next time. Common drift sources after a scenario narrowing:
    - `tasks.md` items that name the old test-name (renamed in spec) or describe the old assertion.
    - `proposal.md` "What Changes" bullets that paraphrase the old requirement (e.g. "seq is assigned by the writer" when implementation now uses a local counter).
    - `design.md` flow diagrams that show the old ordering.
