---
id: 83
slug: archive-helper-edge-cases-and-logging
status: active
tier: 6
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies:
- 82
pre_flight_gates: []
evidence: []
related:
- 82
filed_pr: null
merged_pr: null
archived_at: null
trigger: '/review_task2 iter 1 on 2026-04-29 against PR #126 (ticket #82) — reviewer
  surfaced four valid-but-out-of-scope edge cases and a logging gap on the new archive_workflow_only_ticket
  helper.'
---

83. **Edge cases and logging in `archive_workflow_only_ticket`.** Four refinements surfaced during PR #126 review that are valid but outside the scope of the initial ticket #82 land:
    1. **Half-archived recovery path.** If a prior partial run left the ticket file in `task2/tickets/archive/<NNN>-<slug>.md` with `merged_pr: null` (e.g. `git mv` succeeded but the helper crashed before the frontmatter rewrite committed), re-running the helper falls through to the slug-glob, finds the archive copy, validates the leading int, then raises `FileNotFoundError` because `active_path` no longer exists. The helper should recover by detecting "archive exists with null merged_pr → finish the rewrite at the archive path."
    2. **Robust frontmatter parser.** `text.index("---", 3)` substring scan would mis-identify a Markdown horizontal rule (`---` on its own line) inside frontmatter as the closing fence. Switch to a line-based parser: split on `\n---\n` boundaries, or iterate lines and detect `^---$`. Same change should be applied to `task2/scripts/regen_tickets_index.py` so the two helpers stay aligned.
    3. **End-to-end INDEX regen integration test.** `test_archives_ticket_*` mocks the regen subprocess, so the spec scenario "INDEX.md is regenerated and no longer lists the ticket in the Active section" is asserted only at the call-was-made level. Add an integration test that runs the real `regen_tickets_index.py` against a tmp fixture with a multi-ticket dir, then asserts the resulting INDEX content.
    4. **Logging on no-op CLI invocation.** Direct CLI invocations that hit the idempotent-already-archived branch silently exit 0 with no output, making manual auditing hard. Add a `print()` line on the no-op return path naming the ticket and the stored merged_pr.
    *Tests:* one new test per item: half-archived recovery (write file directly into archive/ with null merged_pr; assert post-call frontmatter and INDEX correctness), HR-in-frontmatter parser (write a ticket whose trigger string contains `\n---\n`; assert no parser corruption), real regen integration (don't mock subprocess.run for the regen call; assert INDEX.md contents after the call), CLI no-op logging (capsys.readouterr() asserts a stdout line).
    *Why useful:* none of these are reachable on the happy path so they don't gate ticket #82's land, but each is a real correctness or auditability improvement and should be tracked rather than forgotten.
    *Trigger:* /review_task2 iter 1 on 2026-04-29 against PR #126 (ticket #82).
