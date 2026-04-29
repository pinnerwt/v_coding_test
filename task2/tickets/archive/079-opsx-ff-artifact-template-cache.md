---
id: 79
slug: opsx-ff-artifact-template-cache
status: active
tier: 1
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 77
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'split out from ticket #77 lever 4 during PR #113 on 2026-04-29 — the four other levers (1, 2, 3, 5) shipped together; this one needs its own design pass and validate-against-archive test discipline.'
---

79. **Cache `/opsx:ff` artifact templates for ticket-shape patterns.** Deferred from ticket #77 lever 4. Many tickets generate near-identical proposal/tasks structures ("fix bug in script X", "add tool Y to agent", "tighten validator Z"). The sonnet subagent in `/new_task2` step 4 currently regenerates these from scratch each iteration — ~30-60s of sonnet runtime per artifact pass that compounds across `/auto_task2`'s 8-iteration ceiling. Concrete fix: introduce a small template directory at `.claude/skills/opsx/templates/` (or `task2/scripts/opsx_ff_templates/`) keyed on ticket signature `(tier, primary_axis, first_touched_file_pattern)` — e.g. tier-2 + tokens_pct-led + `task2/scripts/score.py` matches a "scoreboard math tweak" template. The artifact subagent in `/new_task2` step 4 receives the matching template path in its prompt as a starting point; if no template matches, fall back to from-scratch generation (current behavior). Tests: (a) for each archived change under `openspec/changes/archive/`, derive its retroactive template and assert that re-running `/opsx:ff` with the template produces artifacts that pass `openspec validate --strict`. (b) Snapshot test: a synthetic tier-2 score.py ticket runs through the templated path and the resulting `proposal.md` / `tasks.md` validate clean. (c) Regression test: a ticket whose signature does NOT match any template still produces clean artifacts (fallback path). *Why useful:* combined with ticket #77 levers 1-3+5 (PR #113), this closes the per-iteration-overhead loop — review and simplify dispatches are digest-gated, the WebVoyager run is path-gated, and now artifact generation is cache-warmed. Estimated wall-clock saving: 30-60s per iteration that hits a template, so ~3-8 minutes across a typical 8-iteration `/auto_task2` run. *Risks:* (a) the template cache silently produces wrong-shape artifacts when the template assumption breaks for a similar-but-not-identical ticket — mitigation is to treat `openspec validate --strict` as a blocking gate on every templated artifact before commit; (b) template drift over time as `/opsx:ff` itself evolves — mitigation is to version-tag templates and bake the tag into the subagent's prompt so a stale template produces an explicit mismatch error rather than corrupted output. *Trigger:* split out from ticket #77 lever 4 during PR #113 on 2026-04-29 — the four other levers (1, 2, 3, 5) shipped together; this one needs its own design pass and validate-against-archive test discipline.
