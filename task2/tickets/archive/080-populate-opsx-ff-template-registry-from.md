---
id: 80
slug: populate-opsx-ff-template-registry-from-archived-patterns
status: archived
tier: 1
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies:
- 79
pre_flight_gates: []
evidence: []
related:
- 77
- 79
filed_pr: null
merged_pr: 124
archived_at: '2026-04-29'
trigger: 'split out from ticket #79 during PR #122 on 2026-04-29 — the registry infrastructure
  shipped empty so the format/contract lands before any starter content; this ticket
  does the archive-driven population pass.'
---

80. **Populate the `/opsx:ff` template registry from archived patterns.** Deferred from ticket #79's MVP. PR #122 shipped `.claude/skills/opsx/templates/` with `README.md` (format docs), `INDEX.md` (empty registry), and the `/new_task2` step 4.0 lookup hook — but zero entries, so every ticket still falls through to from-scratch generation. This ticket does the actual archive-driven population: survey the 60+ changes under `openspec/changes/archive/`, cluster by signature `(tier, primary_axis, first_touched_file_pattern)`, and ship templates for the 2–3 most common clusters. Concrete deliverables: (1) Cluster the archived changes — dump each archived change's frontmatter-equivalents (its source ticket's tier and axes; the first inline-backticked file path in `proposal.md`) and group by signature triple. Aim for clusters of size ≥3 — anything thinner is one-off, not template-worthy. (2) For each cluster ≥3, extract the common skeleton: bullets that appear in every archived `proposal.md` become skeleton lines; per-ticket specifics become `{{placeholders}}`. Same procedure for `design.md`, `tasks.md`, and `specs/<capability>/spec.md`. (3) Write `META.yaml` with `version: 1` and a precise `when_not_to_use` distinguishing the template from neighboring patterns. (4) Add the entry to `INDEX.md`. (5) **Retroactive validation pass**: for each archived change in the cluster, run the templated path against its frontmatter and confirm the resulting four files (a) pass `openspec validate --strict` and (b) structurally match the archived artifacts (every `## ADDED Requirements` block and every `### Requirement: <title>` is present). At least 2 archived signature-matching changes per template MUST validate clean before the template is approved. (6) **Live forward test**: run `/new_task2` once with the new template active against the next viable signature-matching ticket and confirm the artifact subagent's wall-clock time drops vs the prior baseline. Acceptance: `INDEX.md` contains ≥2 active templates; the retroactive validation pass is logged in the PR description; one live forward test confirms wall-clock reduction. *Why useful:* PR #122's empty registry is the contract; without this follow-up the cache is decorative — every ticket still pays the from-scratch cost. The 30–60s/iteration savings ticket #79 estimates only materializes once the registry has entries. *Risks:* (a) over-fitting templates to specific archived changes, producing skeletons that fit those tickets exactly but no future ones — mitigation is the cluster-size-≥3 rule and the precise `when_not_to_use` drafting; (b) template-drift over time as `/opsx:ff` itself evolves — mitigation is the version-tag mechanism already shipped in #79 (a stale template's version mismatch is an explicit subagent error, not silent corruption). *Trigger:* split out from ticket #79 during PR #122 on 2026-04-29 — the MVP shipped infrastructure-only so the format/contract lands before any content.
