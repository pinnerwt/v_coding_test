---
id: 81
slug: tune-opsx-ff-template-skeleton-depth
status: active
tier: 1
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: [80]
pre_flight_gates: []
evidence: []
related:
- 79
- 80
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'authored during PR #124 (ticket #80) on 2026-04-29 — retroactive validation showed the seeded 2-requirement spec.md skeletons in `tier5-agent-module` and `tier2-scoreboard-math` are a *lower bound*, not a target: the `observe-ax-tree` archive validates clean against a 2/9 requirement count match because the rendered output is a valid superset shape, but the artifact subagent must extend coverage from 2 to 9 at fill time. After 2-3 live forward tests have flowed through the registry, evaluate whether seeding 3-4 requirements would tighten convergence.'
---

81. **Tune `/opsx:ff` template skeleton depth based on live-forward-test data.** Retroactive validation in PR #124 (ticket #80) confirmed both `tier5-agent-module` and `tier2-scoreboard-math` skeletons pass `openspec validate --strict` against representative archived members, but the requirement-count comparison was lopsided on large archives: `implement-observe-ax-tree` has 9 requirements / 14 scenarios in its archived `spec.md`, while the rendered template seeded only 2 / 4. Validation passes (the rendered output is a valid superset shape), but the artifact subagent must extend coverage at fill time. The `META.yaml.when_to_use` already documents this — "the subagent should add requirements until coverage matches the ticket scope" — but extending from 2 → 9 at template-use time is most of the from-scratch effort the cache was meant to save. **Acceptance:** after at least 3 live forward tests through the registry have completed (i.e. 3 PRs whose `/new_task2` step 4.0 hit a template), inspect each rendered `spec.md`'s final requirement count vs the seeded skeleton. If the median final count is ≥4 across both clusters, increment each template's seeded skeleton from 2 to 4 requirement blocks (with new `{{requirement_title_3}}` / `{{requirement_title_4}}` placeholders) and bump `META.yaml.version` from 1 to 2. The version bump triggers `/new_task2` step 4.1's mismatch check; rendered outputs against version 1 still validate clean (additive change), so the bump is safe even if a stale subagent prompt embeds the old version. Tests: a `pytest` over a fixture corpus of 3 rendered `spec.md` files with ≥4 requirements each, asserting the seeded skeleton's `### Requirement:` block count matches, plus the existing `openspec validate --strict` retroactive validation against ≥2 archived members per template (re-run with the new skeleton). *Why useful:* the registry's value is "subagent edits placeholders rather than authoring from a blank page" — if the subagent still authors 7 of 9 requirements from scratch on every tier-5 hit, the cache saved only ~20% of the artifact-pass time, not the 30-60s/iteration #79 estimated. Right-sizing the skeleton depth is what unlocks the full saving. *Risks:* (a) over-fitting to early live-forward tests if the first 3 are biased (e.g. all came from one archived cluster's shape) — mitigation is to require the 3 tests span both `tier5-agent-module` and `tier2-scoreboard-math` before any version bump; (b) version bumps that introduce new placeholders the subagent prompt doesn't yet enumerate — mitigation is to keep new placeholders to the existing naming scheme (`{{requirement_title_N}}`, `{{scenario_title_NM}}`) and rely on the artifact subagent's `grep '{{' rendered_files` final-pass check (already in `/new_task2` step 4.1) to catch any unfilled new placeholder. *Trigger:* authored during PR #124 (ticket #80) on 2026-04-29 — the retroactive validation made the lower-bound nature of the seeded depth explicit.
