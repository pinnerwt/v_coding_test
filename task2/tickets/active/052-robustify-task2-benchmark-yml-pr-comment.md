---
id: 52
slug: robustify-task2-benchmark-yml-pr-comment
status: active
tier: 2
urgency: P0
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 76
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced by review subagent on PR #76 (iteration 1); urgency bumped P2→P0
  by user directive on 2026-04-29 ("Add a ticket with high urgency to fix the CI workflow")
  during /auto_task2 iteration 2.'
---

52. **Robustify `task2-benchmark.yml` PR-comment posting against transient `gh` failures.** `.github/workflows/task2-benchmark.yml` posts the `diff.md` via `gh pr comment --edit-last --body-file ... 2>/dev/null || gh pr comment --body-file ...`. The `2>/dev/null || ...` swallows real `gh` failures (auth, rate limit, network, GitHub 5xx) and falls through to a fresh comment, which on subsequent runs will edit the wrong comment and may double-post on transient failures. Decision needed: (a) detect existing bot comment via `gh api repos/<o>/<r>/issues/<n>/comments --jq '.[] | select(.user.login == "github-actions[bot]") | .id' | tail -1` and use `gh api --method PATCH /repos/.../issues/comments/<id>` to update by id (true idempotency by author+id), or (b) parse stderr text to distinguish "no prior comment" from real errors before falling through. Tests: workflow dry-run / actionlint clean; ideally a synthetic harness that exercises the fallback path against a mocked `gh` (probably overkill — accept that this is YAML and lives uncovered until it bites). *Why useful:* current behavior masks errors (silent CI failures) and may break the "edit-last" idempotency the spec implies. *Trigger:* surfaced by review subagent on PR #76 (iteration 1).
