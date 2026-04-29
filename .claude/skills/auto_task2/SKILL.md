---
name: "Auto Task2"
description: Loop /full_task2 across remaining Task 2 tickets without user intervention, distilling lessons from each iteration into the supporting skills (/new_task2, /review_task2, /done_pr, /full_task2) before the next ticket runs. Use when the user wants the skill family to keep merging tickets and getting smarter on its own.
category: Workflow
tags: [task2, workflow, automation, loop]
---

Indefinitely drive Task 2 tickets to merge by looping `/full_task2`, distilling lessons from each iteration into the supporting skills (`/new_task2`, `/review_task2`, `/done_pr`, `/full_task2`) between iterations.

This skill assumes auto mode. The user invoked it specifically because they don't want to interfere — make reasonable assumptions on routine decisions, halt loudly only on real blockers (merge conflicts, smoke failures, destructive operations).

## Why a loop wrapper

`/full_task2` already chains the three child skills end-to-end for one ticket. The missing piece is **skill evolution**: each iteration produces friction (a missing flag, an ordering bug, a categorization heuristic the reviewer keeps tripping on) that should be folded back into the skill family so the *next* iteration is cheaper, not just identical. This skill owns that reflective step and the loop.

## Loop

Repeat until the **stop condition** fires.

### 1. Pre-flight

```bash
git rev-parse --abbrev-ref HEAD                       # must be master
git status --porcelain                                # must be empty
gh auth status                                        # must be authed
curl -sf http://localhost:8090/v1/models -m 3 -o /dev/null && echo Qwen reachable || echo Qwen NOT reachable
```

Any failure → **halt** with a one-line reason. Don't try to fix the environment from inside the loop (e.g. don't restart Qwen, don't `git stash`).

Also confirm there is still work to do: read `task2/tickets/INDEX.md` (Active section) and cross-check each active ticket against `openspec/changes/archive/` to see whether any ticket remains unimplemented. If every active ticket maps to an archived change, **halt with success**.

### 2. Snapshot iteration state

Record before invoking the child skill — these become the "what changed in this iteration" inputs for step 4:

- `loop_start_sha` ← `git rev-parse HEAD` on master.
- `iteration_n` ← incremented from prior iteration (start at 1).

Also note the current count of skill files under `.claude/skills/` so step 5 can detect outside edits.

### 3. Run `/full_task2`

Invoke the `/full_task2` skill via the Skill tool, no args. Await completion. The child skill produces its own final report (ticket, change, branch, PR, merge commit, follow-ups). Capture the PR URL and the change name from that report.

If `/full_task2` halts on any of its stop conditions — smoke regression that didn't converge, `/opsx:apply` design block, codex review thrash, merge conflict, no eligible ticket — **halt the auto loop**. Preserve the child skill's stop message verbatim; do not retry. The user invoked auto mode for routine work, not for papering over real blockers.

#### 3a. Optional: parallel-worktree fan-out (manual concurrency, ticket #77 lever 1)

When the next 2-N tickets in INDEX.md touch **disjoint** file sets, the orchestrator can prepare parallel worktrees so the user runs N concurrent Claude Code sessions, one per worktree. This roughly halves wall-clock when there are 2+ disjoint candidates available (typical with 14+ active tickets).

**Why this is a runbook, not an automated step.** `/full_task2` runs inline in the main thread because `/new_task2` and `/review_task2` already spawn subagents internally and subagents-of-subagents silently break (documented in `full_task2/SKILL.md`). One Claude conversation therefore cannot fan out two parallel `/full_task2` runs via the Agent tool — only the human can, by opening N separate sessions with different `cwd`s. So this section sets up the worktrees and prints launch instructions; the actual parallelism happens user-side.

**When to suggest fan-out.** Apply this BEFORE step 3's single-/full_task2 invocation, only when ALL of the following hold:
- The user invoked `/auto_task2 --parallel N` (or equivalent), with N >= 2. If invoked plainly, default to single-track and skip this section.
- INDEX.md has at least N tickets passing the cross-cutting filters (dependencies merged, pre-flight gates satisfied) per `/new_task2` Step 1's selection rule.
- The top N candidates pass the **collision check** below.

**Collision check.** For each of the top N candidates, derive an "implied touch set" from the ticket body (search for fenced filenames, `task2/...` paths, `agent/...`, `scripts/...` mentions). Pair-wise compare:
- Two candidates conflict if their implied touch sets share any path under `task2/agent/**`, `task2/api/**`, `task2/prompts/**`, `task2/scripts/{score,bench,trends,webvoyager_trends,regen_tickets_index}.py`, or any single concrete file (e.g. `task2/scripts/score.py`).
- Tickets with `task2/tickets/**`-only touch sets (process tickets) never conflict with code tickets.
- When in doubt about a ticket's touch set, treat it as conflicting with everything — fall back to single-track for that iteration.

If fewer than N non-conflicting candidates emerge, reduce N to the largest non-conflicting subset (minimum 1; if 1, skip fan-out and run single-track in step 3).

**Worktree prep (orchestrator-side).** For each of the M (= effective parallel count) tickets:

```bash
WT_ID=<short ticket slug>
git worktree add -b task2/<change-name>-w${WT_ID} ../vici-w-${WT_ID} master
```

Each worktree is a sibling directory that shares the `.git` object store but has its own working tree, branch, and HEAD. Conflicts at merge time are mediated by the master branch's protection (sequential PR squash) — the merge phase is intrinsically serial because `gh pr merge` against a protected branch refuses concurrent fast-forwards.

**Launch instructions (printed to user, not executed).** After preparing worktrees, halt with this message verbatim:

```
auto_task2 parallel fan-out prepared:
  worktree A: ../vici-w-<slug-A> on branch task2/<change-A>-wA — ticket #<A> <title>
  worktree B: ../vici-w-<slug-B> on branch task2/<change-B>-wB — ticket #<B> <title>
  ...

To proceed, open M new Claude Code sessions, one per worktree. In each session:
  cd ../vici-w-<slug-X>
  /full_task2
Each session runs independently. Their PRs land sequentially (master is protected; gh pr merge serializes on its own).
After all M land, return to this session and re-invoke /auto_task2 to continue the loop.
```

Do NOT proceed past this halt automatically — the orchestrator's job ends after the worktrees are prepared. The user-side parallelism is what produces the wall-clock win. When the user resumes with `/auto_task2`, treat this as a fresh iteration: the worktrees may or may not have landed; reconcile with `git worktree list` and `gh pr list --head 'task2/*' --state merged` before picking again.

**Cleanup of merged worktrees.** Before each new fan-out (or before exiting the loop), remove worktrees whose branches have been merged or deleted upstream:

```bash
git worktree list
# for each ../vici-w-* whose branch is gone or merged:
git worktree remove ../vici-w-<slug>
```

**Do NOT use parallel fan-out when:**
- The next ticket is a tier-1 process/skill ticket that mutates the orchestrator skills themselves — those changes affect every concurrent session's skill files mid-run. Run tier-1 skill tickets single-track, then fan out the next batch.
- The WebVoyager benchmark would run for any of the M tickets — the live-only WebVoyager run is a serialized resource (Qwen is one process, the public web is shared). With ticket #77 lever 2 in `/done_pr`, process-only tickets skip the benchmark entirely and can fan out freely; agent-touching tickets still serialize at `/done_pr` step 1a even when fanned-out.
- Any candidate ticket has unmerged dependencies that another candidate is *currently implementing*. Treat the in-flight candidate as merged for filter purposes only after its PR lands.

**Why this is filed as a runbook rather than wired up.** Confirmed in ticket #77 lever 1 design pass on 2026-04-29 — the spec called for `/auto_task2 --parallel N` to "spawn N /full_task2 runs in parallel git worktrees," but the subagent-of-subagent constraint makes literal in-process spawning impossible. Documenting the runbook here gives the user a concrete, reproducible mechanism without pretending the orchestrator can drive concurrent main-thread sessions.

### 4. Distill lessons learned

This is the *point* of this wrapper. After `/full_task2` returns success, reflect on what just happened. The bar for emitting an update is **high** — only edit a SKILL.md when one of the following is true:

- An action you took was a **course-correction** caused by missing or wrong guidance in a SKILL.md (e.g. a CLI flag refused with an error the skill didn't pre-empt; an ordering rule that, if reversed, would have produced the same result without rework).
- A **decision heuristic** the orchestrator made (categorizing a reviewer finding as (a)/(b)/(c); choosing a delay; picking a flag) is undocumented and would force the next iteration to re-derive it from scratch.
- A **subagent failed** in a way the skill could have pre-empted by tightening its prompt.
- A **stop condition fired and was misclassified** (e.g. the skill treated a recoverable case as fatal, or vice versa).

Do **not** edit a SKILL.md for:

- Work that succeeded on the first try, even if it felt non-trivial.
- Friction that resolved itself without action (transient flake, retry succeeded).
- Things already documented elsewhere — search the skill's existing notes before adding.
- Stylistic reformatting of existing guidance.

For each genuine learning:

- Find the **most specific location** in the relevant SKILL.md (e.g. `done_pr` step 3, not its top-level Notes). General notes are where guidance goes to die.
- Write a 2–4 line addendum that **leads with the rule**, then a `Why:` one-liner naming the concrete iteration that surfaced it (`observed in PR #<N> on <date>`), then a `How to apply:` line if the trigger isn't obvious from the rule.
- Cross-reference related rules already in the skill rather than duplicating them.

If no genuine learnings surface, **skip step 5 entirely** and print one line: `auto_task2 iteration <N>: no skill updates`. Resist the temptation to invent updates to feel productive.

### 5. Land skill updates via a small PR

`master` is branch-protected — direct `git push` to master is rejected. Skill commits ship the same way feature work does: branch → PR → squash merge. Keep the cycle tight so the next iteration is not blocked.

```bash
git status --porcelain                                # confirm only .claude/skills/** changed
git checkout -b chore/skills-lessons-<change-name>    # fresh branch from master
git add .claude/skills/<edited-skill-dirs>            # never git add -A
git diff --staged                                     # quick eyeball
```

Commit with a HEREDOC body listing each addendum (one bullet per skill touched, naming the rule):

```
chore(skills): lessons from <change-name>

- /done_pr step 3: <one-line rule>
- /new_task2 step 6: <one-line rule>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

Then push the branch and open the PR:

```bash
git push -u origin chore/skills-lessons-<change-name>
SKILLS_PR_URL=$(gh pr create --base master --title "chore(skills): lessons from <change-name>" \
  --body "$(cat <<'EOF'
## Summary
Distilled from auto_task2 iteration <N> (PR #<X>).

- /done_pr step 3: <rule>
- /new_task2 step 6: <rule>

## Test plan
- [x] Skill files load (markdown only, no executable changes)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)")
echo "skills PR: $SKILLS_PR_URL"
```

**Then immediately merge it (mandatory — do not leave the skill PR open between iterations):**

```bash
gh pr merge "$SKILLS_PR_URL" --squash --delete-branch  # explicit URL avoids ambiguity if other PRs are open
git pull --ff-only                                     # pull the squash commit onto master
```

**Verify the merge landed before continuing.** Pass the URL captured above (an open PR with CI in flight will silently leave the merge pending without `--auto`):

```bash
gh pr view "$SKILLS_PR_URL" --json state,mergedAt,mergeCommit -q .
```

`state` MUST be `MERGED` and `mergeCommit.oid` MUST be non-null. If it is still `OPEN` (e.g. branch protection requires a passing check), re-run with `--auto`:
`gh pr merge "$SKILLS_PR_URL" --squash --delete-branch --auto`
and poll `gh pr view` until `state == MERGED` before starting the next iteration. Why: the next iteration's pre-flight requires clean master AND the local checkout on master; an unmerged skill PR leaves the working branch undeleted on the remote and can collide with the next ticket's branch name. Confirmed behavior in PR #67 on 2026-04-27 — merge succeeded immediately because `chore/skills-*` has no required checks; the verification step still ran in <1s and made the success unambiguous.

The next iteration's `/full_task2` will see the updated skills automatically.

**Never edit this skill (`auto_task2/SKILL.md`) from within the loop.** A self-modifying orchestrator mid-run is a debugging nightmare. If you spot a meta-observation about the auto loop itself, surface it to the user in the iteration summary and let them edit between sessions.

### 6. Iteration summary and continue

Print one line:

```
auto_task2 iteration <N> done — merged PR #<X> for <change-name>, skill commits: <0|1>, follow-ups: <count>
```

Loop back to step 1. There is no `ScheduleWakeup` — execute the loop inline in the current conversation. Each iteration is independent: the prompt cache will warm and cool naturally, and the harness's auto-compaction handles long sessions.

## Stop condition

Halt the loop on **any** of:

- A pre-flight check fails in step 1.
- `/full_task2` halts in step 3 with any blocker. Surface its message verbatim.
- `task2/tickets/INDEX.md` Active section has no eligible tickets remaining.
- Iteration count reaches **8**. Five tickets is a typical productive session; eight is a hard ceiling that protects against a runaway loop. If you hit it, stop and ask the user whether to extend.
- The orchestrator detects `git status` dirty after step 5 push — that means a child skill left work uncommitted, which is a contract violation and warrants user attention.

When halting, print this final block:

```
auto_task2: halted after <N> iterations
- merged PRs: <urls>
- skill commits: <count>
- follow-up tickets filed: <count>
- reason: <one-line>
```

## Guardrails

- **Never** override `/full_task2`, `/new_task2`, `/review_task2`, or `/done_pr` defaults. If a phase needs different behavior, change the phase skill via step 4 — not by passing args from here.
- **Never** spawn a subagent to wrap any of the child skills. They each fan out subagents internally; subagents-of-subagents silently break. Run inline in the main thread.
- **Never** force-push, `--no-verify`, weaken any test or quality gate, or skip the smoke test. Auto mode is not a license to relax discipline.
- **Never** auto-resolve a `/done_pr` merge conflict or a smoke regression. Halt and surface.
- The user can interrupt at any iteration boundary — treat their input as a course correction and integrate it before continuing.
- Skill changes ship as their **own** PR with a `chore(skills):` subject — `master` is protected and rejects direct pushes. Never bundle skill edits into a feature commit, and never let skill edits sit in the working tree when the next iteration starts (`/full_task2`'s pre-flight requires clean master).
