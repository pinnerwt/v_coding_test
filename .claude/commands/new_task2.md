---
name: "New Task2"
description: Pick the next Task 2 ticket from task2/tickets/INDEX.md, scaffold an OpenSpec change, and drive it through implementation, verification, and simplification with commits along the way.
category: Workflow
tags: [task2, workflow, automation]
---

Automate the full development cycle for the next Task 2 TDD ticket: derive ticket → scaffold change → implement → verify → simplify, committing at each meaningful boundary.

## Steps

### 1. Identify the next ticket

**Selection rule (category-ordered, per user directive 2026-04-29 — supersedes the 2026-04-28 benchmark-impact-first rule):** evaluate candidates against six tiers in order; **the highest tier with a viable candidate wins**. Within the winning tier, the three-axis benchmark-impact rule (pass-rate / tokens / p50-p95 latency) is the tie-breaker, falling back to lowest ticket number. Two cross-cutting filters apply *before* the tier sort and can disqualify a candidate from any tier.

**Tiers, highest priority first:**

1. **Process / workflow correctness & standards-setting.** Bugs in `/new_task2`, `/done_pr`, `/review_task2`, `/full_task2`, `/auto_task2`, `task2/CLAUDE.md` conventions, OR new standards every subsequent ticket must follow (e.g. the plan.md → `task2/tickets/` migration in #76). Why this is tier 1: the cost of delay compounds — every iteration after the skill bug or the missing standard inherits it. PR #107 fixed the `step_breakdown[i].tools` field-name typo *after* PR #106 had already shipped a no-op ticket selected on that false signal; the typo cost a full iteration. A category-1 ticket prevents that class of waste.
2. **Measurement / observability correctness.** Benchmark harness, validators, scoreboard, trend SVGs, regression-onset tooling. If measurement is broken, every benchmark-impact estimate downstream is unreliable, so tier 4-5 scoring is built on noise. Examples: #57 zero-width-polygon SVG fix, a hypothetical mis-classifying validator.
3. **Stop-the-bleeding correctness regressions.** Production agent bugs that produce wrong outputs on every run (distinct from tier 2's measurement bugs — these affect agent behavior, not the meter). None active in task2 right now; reserved slot so the rule doesn't have to be improvised when one appears.
4. **Diagnostic / audit unblockers.** Tickets that don't themselves move benchmark axes but produce artifacts other tickets' impact estimates depend on. Examples: #74 (diagnose webvoyager-2 step-count regression — its output classifies whether #70 has a reset bug or whether #72 is the right fix), #55 (regression-onset workflow). Pick from this tier *only* when its absence currently blocks scoring at tier 5; otherwise treat as tier 6.
5. **Benchmark-impact tickets** — the prior three-axis rule. Pick the candidate with the highest expected total improvement across pass-rate / tokens / p50-p95 latency, weighting pass-rate while it is below ~80%.
6. **Hygiene** — pure refactors, dead-code removal, doc-only. Bottom of the list.

**Cross-cutting filters (apply *before* the tier sort):**

- **Dependency edges.** If a candidate ticket has `dependencies: [<id>, ...]` in its frontmatter (or the body explicitly says "after #B lands" / "blocked on #B"), and any listed dependency is not yet merged (no closed PR linked to that ticket number), the candidate is **filtered out** for this iteration. The dependency itself sorts in its place if viable. If both are unviable, both defer. Why: implementing A before B routinely produces no-op or wrong-shape work — confirmed by PR #106 shipping #73's mechanism before #72's observation-digest detector existed.
- **Pre-flight gates.** Tickets with explicit gate text in the body or `pre_flight_gates:` frontmatter list (e.g. `must-run-with-no-other-task2-prs-open`, `qwen-reachable`, `no-benchmark-in-flight`) are filtered out when the gate fails right now. Confirm gates with concrete checks: `gh pr list --head 'task2/*' --state open --json number` for the first; `curl -sf http://localhost:8090/v1/models -m 3 -o /dev/null` for the second. Pick the next viable candidate; do not implement around the gate.

How to apply, in order:

1. **Read the latest benchmark scoreboard** to know the current state of all three axes.
   ```bash
   ls -t task2/benchmark/*/results.json | head -3
   cat task2/benchmark/master/scoreboard.md  # or the most recent per-branch scoreboard
   ```
   Capture both:
   - **What is red and why.** Each failing case and its `failure_class` / step pattern. The "Failure histogram" block at the top of `scoreboard.md` (added in ticket #42) is the fastest summary.
   - **The headline aggregate numbers**: pass-rate (e.g. `5/9`), total USD / total tokens (or mean per-case tokens), p50 latency, p95 latency. These are the targets each candidate is judged against — write them down before scoring candidates.

2. **Read `task2/tickets/INDEX.md`** to get the candidate list. The Active section lists all non-archived tickets sorted by id; the Archive section lists completed ones. Each row has: id, urgency, tier, axes (pass_rate/tokens_pct/latency_pct), dependencies, pre_flight_gates, one-line summary, and file path. For full ticket body, `Read` the individual file (column `file`). Cross-check against `openspec/changes/archive/` for stale active entries (archived directories carry a date prefix; strip it when matching). Skip any ticket whose file is in `task2/tickets/archive/`.

2a. **Apply the cross-cutting filters.** For each candidate:
   - **Dependencies.** Read the ticket's `dependencies:` frontmatter field from the ticket file. For each listed id, confirm it is merged: either an `openspec/changes/archive/<date>-*/proposal.md` cites the ticket, OR the ticket file lives under `task2/tickets/archive/`, OR `gh pr list --search '#<N>' --state merged --json number` returns a hit. If any dependency is unmerged, **drop this candidate** and add its first-unmerged dependency to the candidate set if it is not already there.
   - **Pre-flight gates.** Read `pre_flight_gates:` frontmatter (or the body's `*Risks:*`/`*Trigger:*` section for legacy entries) for explicit gate text. Run the corresponding check now (`gh pr list --head 'task2/*' --state open --json number,title` for "no other task2 PRs open"; `curl -sf http://localhost:8090/v1/models -m 3 -o /dev/null` for "Qwen reachable"). On gate failure, drop this candidate.
   The output of this step is a filtered candidate list. Record the per-candidate filter outcome in the iteration log (e.g. `iter N: #76 filtered (gate "no-other-task2-prs-open" fails — PR #108 open); #74 filtered (depends on #66 which is merged: still viable); #72 viable`).

2b. **Categorize each remaining candidate into a tier (1-6).** Use the tier definitions from the selection rule above. Tier hints:
   - The ticket touches `.claude/`, `task2/CLAUDE.md`, or sets a contract every future ticket follows → **tier 1**.
   - The ticket touches `task2/scripts/bench.py`, `scripts/trends.py`, validators, scoreboard rendering → **tier 2**.
   - The ticket fixes a wrong-output bug in `task2/agent/` that affects every run → **tier 3**.
   - The ticket's *Why useful* says "blocks ticket #M's estimate" or "produces an artifact other tickets need" → **tier 4** (but only if #M is currently blocked; otherwise tier 6).
   - The ticket explicitly targets a benchmark axis → **tier 5**.
   - Pure refactor, doc-only, dead-code removal → **tier 6**.
   When in doubt between adjacent tiers, prefer the lower number (higher priority) only if cost-of-delay genuinely compounds; otherwise go higher (lower priority). Record the chosen tier in the iteration log per candidate.

3. **Within the highest occupied tier, estimate per-axis impact per candidate.** Skip this for tiers 1-3 unless there are multiple candidates in the tier (tiers 1-3 are picked on category alone, lowest ticket number tie-break). For tiers 4-5, write one line capturing all three axes: `ticket #N (tier T): flips ~K cases (case A, case B, ...); tokens ~ΔT% (why); latency ~ΔL% (why)`. The estimate is judgment, not arithmetic — but each axis must be grounded in the scoreboard or in the ticket's acceptance criteria. Examples:
   - A new-tool ticket (e.g. #59 `click(intent)`) → flips ~5 red cases (every read→fail drift/correction case); tokens ~unchanged (same path length per step); latency ~unchanged. **Score: pass-rate-led.**
   - A CDP-session-reuse ticket (e.g. #23) → flips 0 cases; tokens ~unchanged; latency cuts ~30–50ms per step (one fewer CDP attach/detach round-trip per observation). **Score: latency-led.**
   - A token-trimming ticket (e.g. tighter AX-tree node cap, smaller observation digest) → flips 0 cases; tokens cuts ~20–40% per step; latency cuts modestly (smaller payloads). **Score: tokens-led.**
   - An audit / classification ticket (e.g. failure-class enrichment, scoreboard traffic lights) → 0 / 0 / 0 across all three axes; pick only when its absence *currently blocks an estimate* for another candidate.
   - A pure refactor / dev-experience ticket → 0 / 0 / 0; drops to the bottom.

3a. **Validate the proposed fix mechanism against each named case's actual trace before locking the estimate.** A pass-rate-led estimate is only credible if the *mechanism* the ticket installs would actually have fired on the case it claims to flip. Before finalizing any candidate whose pass-rate score depends on a specific case (e.g. "flips webvoyager-1 because K=3 byte-identical tool-call detection terminates the stuck planner"), open that case's most recent benchmark JSON and inspect:
   - `step_breakdown[].tool_calls` — the list of tool names the planner actually emitted at each step. **The field is `tool_calls` (plural), NOT `tools`** — confirmed by inspecting `task2/benchmark/*/webvoyager/*.json` shapes on 2026-04-29; every entry under `step_breakdown` is `{"step": int, "latency_ms": int, "prompt_tokens": int, "completion_tokens": int, "usd": float, "tool_calls": ["click", ...]}`. There is no `tools` field. Reading `.tools` always returns `None`/missing for every step, which silently fakes a "no-tool-call stall" classification. If every `tool_calls` entry is `None`, `[]`, or missing, the case is a *no-tool-call* stall, not a repeated-tool stall, and any (tool_name, args)-buffer mechanism cannot fire.
   - `step_breakdown[].action` / `outcome` — whether the step had a real dispatch path or short-circuited (e.g. all `text-only`).
   - `failure_class` and the tail of the event log — confirm the failure shape the ticket targets is the failure shape the case exhibits.

   **One-liner for the field check** (paste-ready):
   ```bash
   python3 -c "import json,sys; d=json.load(open(sys.argv[1])); c=next(x for x in d['cases'] if x['id']==sys.argv[2]); [print(i, s.get('tool_calls')) for i,s in enumerate(c['step_breakdown'])]" <run.json> <case-id>
   ```

   If the trace and the mechanism don't match, downgrade that case's contribution to the candidate's pass-rate score to 0 and re-rank. Common shape mismatches that have burned past iterations:
   - **Repeated-tool buffer vs no-tool-call stall**: `step_breakdown[].tool_calls == None` for every step → K=3 byte-identical (tool_name, args) detection never accumulates a buffer entry. Need a *separate* "K consecutive empty tool_calls" detector.
   - **Locator escalation vs DOM unfamiliarity**: a case fails with `failure_class=no_done_emitted` after 1-3 steps because the agent can't read the live DOM at all. A new tool added to `_dispatch` won't help if the planner never sees enough state to call it. Validate by checking whether `step_breakdown[].observation_size` is truncated near zero or the read events never produced AX-tree content.
   - **Pre-existing supervisor-mediated path**: a `read(intent=X)` repetition case is owned by the locator-escalation / halt path in the supervisor, not by stuck-detection. The buffer is cleared on supervisor attempt-count increase. If the candidate's mechanism is "stuck-detection on `read`", the supervisor will fire first; pass-rate contribution is 0.

   **Why this step exists, with a load-bearing example.** PR #106 (ticket #73, `no_tool_call_repeat`) was picked on 2026-04-29 expecting to flip webvoyager-1 from `timeout (steps=20)` to `failed (steps=3, ~$0.05)` because the prior /done_pr report had classified webvoyager-1 as a no-tool-call stall. That classification was a false signal: the orchestrator queried the wrong field name (`step_breakdown[i].tools`, which silently returns `None`), and the actual `step_breakdown[i].tool_calls` field showed real tools (`['goto']`, `['click']`, `['type']`, `['read']`, ...) at every step. Ticket #73 shipped architecturally sound code but flipped zero cases — webvoyager-1 still timed out at 20 steps with the same trace shape. The post-merge regression analysis (`/done_pr` step 1b') showed suite cost / tokens / latency all up +43.6% vs the prior baseline, with the regression localized to webvoyager-2's environmental variance, not webvoyager-1. The ticket the trace ACTUALLY supports is #72 (observation-digest companion to the (tool_name, args) K=3 buffer), which was already filed.

   This step is **mandatory** when the candidate's pass-rate estimate is non-zero. For tokens-led or latency-led candidates with `pass_rate ≈ 0`, the trace check is optional — the failure shape doesn't constrain the mechanism. Record the trace evidence in the per-iteration log line (e.g. `iteration N picks #M (P2, expected: flips 0 / tokens -25% / latency ~0); webvoyager-1 trace: 20 steps, step_breakdown[].tool_calls = [['goto'],['click'],['type'],...], mechanism-mismatch ruled out as flip target`).

4. **Pick the candidate from the highest occupied tier.** Sort tiers ascending (1 → 6); the first tier with at least one candidate (after step 2a's filtering) wins. **Within that tier:**
   - **Tiers 1-3:** lowest ticket number wins. Three-axis estimation is not the tie-breaker here — these tiers are picked on category, because their value is "every subsequent ticket inherits the fix," not a benchmark delta.
   - **Tier 4 (diagnostic unblocker):** pick only if its absence currently blocks scoring at tier 5; otherwise demote to tier 6 and re-sort. When picked, lowest ticket number wins.
   - **Tier 5 (benchmark-impact):** pick the highest expected total improvement across the three axes. Weight each axis by distance from the done bar / visibility on the scoreboard (pass-rate dominates while it is below ~80%; tokens and latency become co-equal once pass-rate clears the bar). Tie-break by lowest ticket number.
   - **Tier 6 (hygiene):** lowest ticket number wins.
   The Undone rubric's P0/P1/P2/P3 urgency tags are *advisory* — they tie-break across rough impact estimates within tier 5, and document why a tier-6 candidate might still be picked (e.g. it unblocks several others). They do **not** override the tier order.

5. **State the chosen ticket** in one line: ticket number, title, **tier**, urgency tag, derived change name, and (for tiers 4-5) the expected per-axis deltas (e.g. `iteration 9 picks #76 (tier 1, P3) → migrate-plan-to-tickets`, or `iteration 12 picks #59 (tier 5, P1, expected: flips +5 / tokens ~0 / latency ~0) → implement-click-tool`).

The urgency tag remains useful as a tie-breaker between equally-impactful candidates and as documentation of *why* a 0-impact ticket might still be picked (e.g. it unblocks several others). Do not drop it from the rubric or the per-iteration log.

**Stop condition for the wrapping `/auto_task2` loop:** the three-axis flat-deltas rule applies **only when the picked ticket is tier 4 or tier 5** (the tiers whose value proposition *is* a benchmark axis move). For tiers 1-3, success is defined by the standard landing, not by axis deltas — a tier-1 ticket that ships a new ticket-folder layout legitimately produces zero axis movement and that is not a stop signal. After `/done_pr` records the new benchmark:
- **Picked ticket was tier 4 or 5:** compute deltas against the prior master baseline on all three axes (pass-rate, total tokens, p50 + p95 latency). If two consecutive *tier-4-or-5* iterations produce zero net improvement on **every** axis (every delta ≤ 0 both times), halt and surface to the user.
- **Picked ticket was tier 1, 2, 3, or 6:** record the deltas in the iteration log for trend visibility, but do **not** count this iteration toward the flat-deltas streak. The next tier-4-or-5 iteration restarts the streak from its own baseline.
A single-axis improvement (e.g. tokens go down while pass-rate is flat) on a tier-4-or-5 iteration keeps the loop alive. The 8-iteration ceiling still applies as a hard cap regardless of tier mix.

Cross-check the rubric against the filesystem to catch stale entries:
```bash
ls openspec/changes/archive/ 2>/dev/null
ls openspec/changes/ 2>/dev/null
```

Archived directories carry a date prefix (e.g. `2026-04-25-implement-llm-client`); strip that when matching against ticket slugs. If a rubric entry's ticket number maps to an archived change, the rubric is stale — drop the entry as part of Step 11 of *this* run rather than blocking. If a P0 entry references an in-flight PR (`### In flight` subsection), skip it and pick the next-highest-urgency entry not in flight. If unsure, use the **AskUserQuestion** tool to confirm with the user before proceeding.

Derive a kebab-case change name from the ticket title. Convention: `implement-<short-slug>` for new behavior, `fix-<short-slug>` for audit/bug tickets that primarily change existing behavior. Examples:
- Ticket 3 "`locate.py` L1" → `implement-locate-l1`
- Ticket 7 "Locator cache" → `implement-locator-cache`
- Ticket 11 "`loop.py` silent-failure guard" → `implement-loop-silent-failure-guard`
- Ticket 32 "Audit ticket: investigate why mechanism-firing rates are 0/8" → `fix-mechanism-firings`

State the chosen ticket number, title, **urgency tag** (P0/P1/P2/P3), and derived change name in one line before continuing.

### 1a. Workflow-only fast path

If the picked ticket touches **only** files under `.claude/skills/**`, `.claude/commands/**`, or process docs (`task2/CLAUDE.md`, `openspec/AGENTS.md`, repo-root `CLAUDE.md` orchestration sections) — i.e. **no production code under `task2/`, no `openspec/specs/` deltas, no `task2/scripts/` changes** — switch to the fast path: skip Steps 3-7 entirely (no `/opsx:new`, no artifact subagent, no scaffold commit, no `/opsx:apply`, no `/opsx:verify`) and skip Phase 2 (`/review_task2`) of the wrapping `/full_task2`.

Detection rule, in order of authority:
1. The ticket body (or its `axes:` row) explicitly says `skill-doc-only`, `workflow-only`, `no production code changes`, or `touches only .claude/`.
2. The implied touch list derived from the ticket's acceptance criteria is wholly under `.claude/skills/**`, `.claude/commands/**`, or other process-doc paths.
3. Otherwise → **standard path** (run all 12 steps).

When in doubt, default to the standard path. The cost of an unnecessary scaffold is one wasted iteration; the cost of skipping verification on a real code change is a regression that the smoke test may or may not catch.

Fast-path execution after Step 1:
- **Step 2** (branch): use a `chore/skills-<slug>` branch, NOT `task2/<slug>`. Skill-update PRs land as `chore(skills):` commits; the `task2/` prefix is reserved for production-code branches that the auto-loop counts toward its iteration budget.
- **Skip Steps 3, 4, 5, 6, 7** entirely. There is no OpenSpec change, no `proposal.md`, no `tasks.md`, no `pytest` red-step, no `/opsx:apply`, no `/opsx:verify`. Why: workflow-only tickets have no executable test surface — the test surface IS "running each scenario through the skill produces the documented behavior." Forcing them through the OpenSpec/pytest pipeline produces empty scaffolds and review thrash. Confirmed in the iteration-3 course-correction on 2026-04-29 — ticket #77 (a five-lever skill-pipeline-speedup ticket) was awkwardly scaffolded into an `implement-*` change with no production code under `openspec/changes/<change>/specs/` until the user explicitly requested this fast path.
- **Make the skill edits directly** on the branch with `Edit` / `Write` tools. Reference the ticket body for the exact behavioral changes; use the existing skill prose's voice.
- **Step 8 (`/simplify`)**: still run it on the working tree. `/simplify` is markdown-aware and catches duplicated guidance / parameter sprawl in skill prose.
- **Step 9 (smoke test)**: run `bash task2/smoke_test.sh` — it should pass trivially because no `task2/` code changed. If it fails, that is independent infra noise; surface it but do not block the PR on it.
- **Step 10 (PR)**: title is `chore(skills): <ticket title>` (NOT `feat(task2):`). The PR template's "Task" field should still say `task2` if the skill being changed is in the task2 family, but the body's "Summary" should describe the workflow change rather than a behavioral one. Skip the "OpenSpec" section — leave it as `n/a (workflow-only ticket)`.
- **Step 11 (follow-ups)**: still applies — record any new tickets surfaced by the work.
- **Step 12 (final report)**: include a one-line note `Path: workflow-only fast path (skipped opsx scaffold + /opsx:apply + /opsx:verify + Phase-2 review per fast-path rule)`. Suggested next step is just `gh pr merge --squash --delete-branch` — there is no `/opsx:archive <change-name>` step because no change directory was created.

`/full_task2` Phase 2 (`/review_task2`) is also skipped under the fast path. The reviewer subagent reviews diffs through the lens of correctness / TDD / test coverage — none of those criteria apply to skill prose. `/done_pr` (Phase 3) still runs but its OpenSpec archive step (`/opsx:archive`) is a no-op since there is no active change directory; `/done_pr` should detect this (no `openspec/changes/<change>/` exists) and skip the archive substep, falling through to the merge / master-sync substeps.

### 2. Create a development branch

From the current branch, create and switch to a new branch:
```bash
git checkout -b task2/<change-name>
```

If the working tree is dirty, **stop and ask** the user how to proceed — do not stash or discard. Two known patterns:

- **New files in `task2/tickets/active/`** — leftover from a prior run's Step 11 (follow-up ticket files written but never committed/pushed). Typical answer: carry into the next branch as a `docs(task2):` commit.
- **`.claude/skills/<name>/SKILL.md` or `.claude/commands/<name>.md` modified** — a sibling skill update authored in a separate lessons-learned thread (e.g. tightening `/done_pr`). Typical answer: commit on master *before* branching, as a `chore(skills):` commit. These are unrelated to task2 and don't belong in the PR.

When in doubt, surface the diff and offer four options via **AskUserQuestion**: (a) commit on master and proceed, (b) carry into next branch, (c) discard, (d) pause for manual handling. Never silently stash or run `git restore`.

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
  - The ticket number, title, and full ticket text from the ticket file under `task2/tickets/`.
  - Instruction: "Invoke the `/opsx:ff` skill on `<change-name>`. Do not commit or push. Do not implement code — artifacts only."
  - Grounding sources to read before drafting:
    - The selected ticket file under `task2/tickets/` (ticket acceptance criteria; read via the `file` column in INDEX.md).
    - `task2/CLAUDE.md` and the rest of `task2/` for code conventions and existing structure.
    - Repo-root `CLAUDE.md` (TDD non-negotiable, `uv` + `ruff` tooling, no hardcoded LLM provider).
    - Existing main specs under `openspec/specs/` — `grep -rn "ticket #<N>" openspec/specs/` for the ticket number being implemented. If a prior change's spec contains a Note like "tracked under ticket #<N>" referring to *this* ticket, the MODIFIED delta MUST update that Note to drop the now-stale forward reference (the ticket is being implemented, not deferred). Missing this leaves the merged main spec pointing at a closed ticket.
  - **Delta-format requirement (mandatory, even for new capabilities):** every file written to `openspec/changes/<change-name>/specs/<capability>/spec.md` MUST use the OpenSpec delta format — top-level headers `## ADDED Requirements` / `## MODIFIED Requirements` / `## REMOVED Requirements` / `## RENAMED Requirements`, with `### Requirement: <title>` sub-sections under them. Do **not** author it as a full main-spec layout (top-level `# <Capability> Specification` + `## Purpose` + `## Requirements`), even when the capability is brand new and `openspec/specs/<capability>/` does not yet exist. The full main-spec is generated downstream by `/opsx:sync` from the `## ADDED Requirements` block. If the delta is authored as a main-spec, `openspec archive --yes --skip-specs` refuses with `No delta sections found. Add headers such as "## ADDED Requirements" or move non-delta notes outside specs/.` and the only unblock is a one-shot `--no-validate` on the archive call (see `/done_pr` step 1). Confirmed in PR #58's archive run on 2026-04-27 — the new `loop-step-id` capability shipped with a main-spec-shaped delta and blocked archive until `--no-validate` was added by hand.
  - **ADDED vs MODIFIED selection rule (mandatory):** the delta header MUST match whether the requirement title already exists in `openspec/specs/<capability>/spec.md`. If the requirement title is brand-new (regardless of whether the capability is new or pre-existing), use `## ADDED Requirements`. Use `## MODIFIED Requirements` only when an `### Requirement: <exact-title>` block already exists in the main spec and the delta tweaks its description or scenarios. Confirmed in PR #66 on 2026-04-27 — the artifact subagent wrote `## MODIFIED Requirements` for the new `_run_agent logs full traceback on internal error` requirement under the pre-existing `api-server` capability; the orchestrator had to flip the header to `## ADDED` before commit, otherwise `/opsx:sync` would silently fail to find a target requirement to modify (no error, just a no-op merge into the main spec). How to apply: before invoking `/opsx:ff`, the subagent SHALL `grep -F "### Requirement: <title>" openspec/specs/<capability>/spec.md` for each requirement it plans to author; missing → `ADDED`, present → `MODIFIED`.
  - **No fenced markdown blocks containing `##`/`###` headers inside requirement descriptions.** When a requirement's description needs to demonstrate the literal output structure of a generated artifact (e.g. "the file MUST contain `## Regressions` then `## Never Passed` then `## Stable`"), express that as a **bulleted list with inline backticks** (e.g. `- ` `` `## Regressions` `` ` — table with columns ...`), NOT as a fenced ` ``` markdown ... ``` ` block. The `openspec validate --strict` parser walks the spec by markdown headers and treats every `##`/`###` line *inside* a fenced block as if it were a real section header — this terminates the surrounding `### Requirement: <title>` block prematurely, drops subsequent `#### Scenario:` blocks out of scope, and the validator then reports `ADDED '<title>' must include at least one scenario` even though scenarios are present in the source. Why: confirmed in PR #77 on 2026-04-28 — the `Regression onset report schema` requirement embedded the literal section layout in a fenced block; strict validation refused the change and the unblock was to rewrite the demonstration as bullets (commit 55fb35e). How to apply: before returning artifacts, run `grep -nE '^```' openspec/changes/<change-name>/specs/**/*.md` and verify no fenced block in the file contains a line starting with `## ` or `### ` — if it does, refactor to bullets.
  - **Touch only files under `openspec/changes/<change-name>/`.** The artifact-generation subagent MUST NOT modify, create, or delete any file outside that directory tree. In particular, `prompts/`, `task2/`, `.claude/`, `openspec/specs/` (those are downstream of `/opsx:sync`), and any sibling change directories are off-limits. Why: confirmed in PR #77 on 2026-04-28 — the subagent silently edited `prompts/02_task2.md` while drafting `proposal.md`, producing a stray uncommitted diff the orchestrator had to `git restore` before continuing. How to apply: at the end of the subagent's work, run `git status --porcelain` and verify every modified or untracked path begins with `openspec/changes/<change-name>/`. If anything else appears, surface it in the report-back instead of committing or proceeding.
  - Required report back: list of files created under `openspec/changes/<change-name>/`, plus any open questions or assumptions made, and the output of `git status --porcelain` filtered for paths outside that directory (must be empty).

Wait for the subagent to return, then **verify the actual artifacts on disk** (`ls openspec/changes/<change-name>/`, spot-read `proposal.md` and `tasks.md`) before continuing. The subagent's summary describes intent, not necessarily what landed. Spot-check that each spec delta's top-level header (`## ADDED` vs `## MODIFIED`) actually matches whether the named requirement title exists in the corresponding `openspec/specs/<capability>/spec.md` — this is the most common artifact-subagent miscategorization.

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
  - Instruction: "Invoke the `/opsx:apply` skill on `<change-name>` and drive every task in `tasks.md` to completion under TDD discipline (red → green → refactor; tests live under `task2/tests/`). **As you complete each numbered task, edit `openspec/changes/<change-name>/tasks.md` to flip its `- [ ]` checkbox to `- [x]`** and stage that edit into the same commit that satisfies the task. Do not leave the file with all-unchecked boxes at the end and rely on a separate bookkeeping commit — that is a contract violation. Why: confirmed in PR #64 on 2026-04-27, the implementer reported 'all tasks complete' but every box was still `[ ]`, forcing a manual `sed` + extra `chore(task2): mark ... tasks complete` commit. How to apply: after each `feat(task2):` or `fix(task2):` commit, run `grep -c '\[ \]' openspec/changes/<change-name>/tasks.md` and confirm the count dropped by the number of tasks just satisfied."
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
  - **Renames / signature changes need a repo-wide grep.** When a task renames a symbol or changes a parameter shape (e.g. `last_action` → `last_actions`, or `dict | None` → `list[dict]`), the artifact `tasks.md` typically only enumerates the obvious touch points. After the migration step, `grep -rn '<old name>\|<old shape sentinel>' task2/` and update every remaining caller — including tests not listed in `tasks.md`. Python doesn't enforce type hints at runtime, so stale `None` arguments to a now-`list`-typed parameter pass tests but violate the new contract; the verify step (Step 7) will flag them otherwise.
  - **`Literal` over `str` whenever a field has a closed value set, and `frozenset(get_args(LiteralAlias))` over a hand-maintained set.** When the spec/proposal enumerates allowed values for a field (e.g. `skip_reason ∈ {"live_disabled", "infra_unavailable", "fixture_missing", "feature_not_implemented"}`, or `policy ∈ {"halt", "next_tier"}`), the dataclass field MUST be typed `Literal[...] | None` (or the `| None` half dropped if always-set). Do not type it `str | None` and validate at the boundary; the type is the contract. Then alias the literal once at module top-level and derive the runtime validator from it: `SkipReason = Literal["a", "b"]; _VALID: frozenset[str] = frozenset(get_args(SkipReason))` — this keeps the type and the `__post_init__` allow-set in lockstep, so adding a new literal value requires touching exactly one line. Why: confirmed in PR #73 on 2026-04-28 — implementer subagent typed `skip_reason: str | None` and hardcoded a parallel `_VALID_SKIP_REASONS = frozenset({...})`, requiring a verify-loop fix to introduce the alias and tighten the annotation. How to apply: when reading the spec/design before each `feat(task2):` commit, scan for "must be one of", "MUST be one of", "in the set", or "Literal" wording in the requirement text — those phrases are the trigger for the alias pattern.
  - **Tool-dispatch miss-path tests MUST assert on the trace, not just `RunResult.status`.** When a task adds a new tool to `_dispatch` (`click`, `type`, `select`, `wait_for`, …) and the spec contract is "all-tier locate miss → return error string, loop continues", the test for that path MUST open a trace writer (`_make_writer_with_run(run_id)`), pass `trace_writer=writer, run_id=run_id` to the `loop(...)` call, then collect events via `writer.iter_events(run_id)` and assert *something* about the trace shape — typically `len([e for e in events if isinstance(e, ActEvent) and e.tool == "<X>"]) == 0` (because the locate-miss path returns the error string *without* emitting an `ActEvent`). Asserting only `result.status == "succeeded"` is **insufficient**: the locate ladder may fuzz-match an unrelated element on the page, the action may silently succeed, and the LLM still emits `done` — the test passes despite never exercising the miss path. Why: confirmed in PR #91 on 2026-04-28 — `test_loop_type_l1_miss_returns_tool_error_loop_continues` asserted only on `RunResult.status`, and an iter-4 review correctly flagged that the test name's "tool error returned" claim was unverified. Required a test-strengthening commit. How to apply: when the spec scenario name contains "miss", "non-existent", "all tiers exhausted", or similar, the corresponding test MUST inspect the trace writer's events.
  - **Lock down spec-mandated kwargs (e.g. `timeout=5000`) via a stub recorder, not a discarded kwarg.** When the spec dictates a specific magic-number kwarg on a Playwright call (`Locator.click(timeout=5000)`, `Locator.fill(text, timeout=5000)`, …) and the dispatch test uses a stub `_StubLocator`, the stub MUST record the call (e.g. `self.fill_calls.append({"text": text, "timeout": timeout})`) and at least one test MUST assert the exact recorded dict, e.g. `assert stub_locator.fill_calls == [{"text": "foo", "timeout": 5000}]`. A stub that silently swallows the kwarg (`def fill(self, text, *, timeout): ...`) does not lock down the contract — production could regress to `timeout=1000` and tests still pass. Why: confirmed in PR #91 on 2026-04-28 — the iter-3 review flagged that no test pinned `timeout=5000` for the type tool, requiring a test-strengthening commit. How to apply: when reading spec.md before authoring stubs, grep for `timeout=\d+` or other literal-numeric kwargs in the requirement text — each one is a stub-recorder trigger.
  - If a task surfaces a design problem, **stop and report back** (per `/opsx:apply` guardrails) instead of papering over it. **Exception:** if the contradiction is purely in the literal `tasks.md` wording (e.g. "reset before X" when correct semantics is "reset after X") and the right behavior is unambiguous from the spec/tests, implement the correct behavior, note the divergence in the report-back, and continue. Don't block on prose drift in scaffold artifacts.
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

**Right-size the review.** The `/simplify` skill defaults to fanning out three parallel subagents (reuse / quality / efficiency). For small diffs (under ~150 changed lines, e.g. a single-module ticket like #23 CDP cache), the orchestrator can do the same review inline and apply fixes directly — skip the fan-out. For larger diffs (multi-module, eval changes, scoring overhauls) keep the three parallel agents, since the cost of missing a finding outweighs the subagent overhead.

**Watch for these specific patterns** that this loop has produced before:
- **Dead fallback branches.** When the ticket adds a new attribute to a class (`self._cdp_sessions`, `self._foo`) and you've already updated test fixtures / `SimpleNamespace` doubles to set it, any `getattr(obj, attr, None)` "fallback" branch is dead code. Drop the branch entirely; assume the attribute is present. Keep it only if a real, non-test caller exists.
- **Per-test boilerplate.** Three new tests building the same `data:text/html;base64,...` URL inline → hoist to a module-level constant (`_BUTTON_DATA_URL`) or fixture. Ditto duplicated `import base64 as _b64` shadowing a module-level `import base64`.
- **Branch-duplicated `try/finally`.** If two if/else branches both end in the same `cdp.send(...)` + `try: cdp.detach() except: pass` pattern, consolidate to one send + one finally below the if/else and gate the detach on a `transient` flag. (Then per the dead-branch rule above, often one branch can be removed entirely.)
- **Branch-duplicated `dict` builds.** Two if/else branches both build a dict that shares 3-of-4 keys (e.g. `last_actions.append({"tool": ..., "intent": ..., "outcome": "ok"})` vs. `... "outcome": "error", "error": tool_result`). Collapse to one dict literal with a ternary on the differing key, then conditionally `dict[extra_key] = value` for the error-only field. Reuse the boolean (`is_error = ...`) for any later branch that re-checks the same condition (e.g. supervisor halt detection two lines down).
- **Per-test scripted-LLM client classes.** When two new `loop.py` tests each define a near-identical `_FooClient` with `chat(messages, *, tools=...)` returning a different first-step `ChatResponse` and the same final `done` response, parameterize one shared `_ScriptedFirstStepClient(first_step_calls, done_evidence_url)` instead. The pattern is "first call returns scripted tool calls, second call returns `done`" — only the `tool_calls` list and the evidence URL vary.
- **Repeated observation-from-captures extraction.** The pattern `obs_msg = next(m for m in reversed(captures[N]) if m["role"] == "user" and "Current state:" in m.get("content", "")); obs = _extract_obs_json(obs_msg["content"])` repeats across multi-step loop tests. Hoist a `_step_observation(captures, step_index) -> dict` helper next to `_extract_obs_json`. Apply it to existing migrated assertions too (e.g. `test_second_step_last_action_populated`), not just the new tests, to keep the file consistent.

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
- **Summary** — 1–3 bullets describing what the ticket adds, grounded in the ticket text from the ticket file under `task2/tickets/`.
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

### 11. Capture outstanding follow-ups as ticket files

If any **outstanding follow-ups** surfaced during this run — design issues deferred from `/opsx:apply` or `/opsx:verify`, smoke-test gaps that pointed at adjacent code, scope-creep items consciously left out, or TODOs uncovered by `/simplify` — record them as new TDD ticket files so a future `/new_task2` invocation can pick them up. Do **not** carry them only in the PR description or the conversation; the durable record lives in `task2/tickets/`.

What counts as a follow-up worth recording:
- A concrete behavior gap with a plausible failing test (TDD-shaped).
- A refactor that was out of scope for this ticket but is now clearly worth doing.
- A design problem `/opsx:apply` flagged and stopped on, that you resolved by deferring rather than fixing in-scope.

What does **not** belong as a new ticket file:
- One-off chores already captured in commits.
- Speculative ideas without a test surface.
- Anything already covered by an existing active ticket — extend that ticket's file body instead of adding a duplicate.

Procedure for each follow-up:

1. Find the highest existing ticket number: `ls task2/tickets/active/ task2/tickets/archive/ | grep -oE '^[0-9]+' | sort -n | tail -1`. Assign the next number.
2. **Assign an urgency tag** (P0/P1/P2/P3) and **tier** (1-6) using the same rubric Step 1 reads:
   - **P0** — unblocks other tickets or removes recurring debug friction.
   - **P1** — observed bug or correctness gap blocking the brief's done bar.
   - **P2** — measurable improvement to eval / scoreboard / mechanisms.
   - **P3** — nice-to-have polish.
   - **Tier**: 1=process/standards, 2=measurement, 3=stop-the-bleeding, 4=diagnostic, 5=benchmark-impact, 6=hygiene.
3. Write `task2/tickets/active/<NNN>-<slug>.md` with all 14 required frontmatter fields:
   ```yaml
   ---
   id: <N>
   slug: <kebab-case-title>
   status: active
   tier: <1-6>
   urgency: <P0-P3>
   axes:
     pass_rate: <estimated int delta, 0 if unknown>
     tokens_pct: <estimated int delta, 0 if unknown>
     latency_pct: <estimated int delta, 0 if unknown>
   dependencies: [<list of int ids, or empty>]
   pre_flight_gates: [<list of gate strings, or empty>]
   evidence: []
   related: [<int ids of related tickets>]
   filed_pr: null
   merged_pr: null
   archived_at: null
   trigger: "<ISO date> — <workflow event that surfaced the ticket>"
   ---
   ```
   Body: the full ticket text (self-contained so a fresh `/new_task2` run can pick it up cold).
4. Run `uv run python task2/scripts/regen_tickets_index.py` to update `task2/tickets/INDEX.md`.
5. If a follow-up overlaps an existing ticket, edit that ticket file's body and update its `axes` / `urgency` if warranted instead of adding a duplicate.

Commit the new ticket files and the updated INDEX.md on the same branch, then push:

```bash
cd task2 && uv run ruff format . && uv run ruff check . && uv run pytest && cd ..
git add task2/tickets/active/<NNN>-<slug>.md task2/tickets/INDEX.md
git commit -m "$(cat <<'EOF'
docs(task2): file ticket #<N> — <short title>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

The pre-commit gate still applies — never `--no-verify`. If you also need to update the PR body to reference the new ticket numbers, do it with `gh pr edit --body-file ...` reusing the temp file from Step 10.

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
- Outstanding follow-ups: either "none" or the numbered list of new ticket files written to `task2/tickets/active/` in Step 11 (with their ids).
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
