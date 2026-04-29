---
id: 84
slug: archive-helper-stages-frontmatter-updates
status: archived
tier: 1
urgency: P1
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/scripts/archive_workflow_only_ticket.py
- task2/tests/test_archive_workflow_only_ticket.py
related:
- 82
filed_pr: null
merged_pr: 130
archived_at: '2026-04-29'
trigger: 'discovered during retroactive archival of tickets #79 and #80 on 2026-04-29 — `git status` after running the helper showed both archive files as `M` (unstaged frontmatter updates), and a fresh commit had to be added to land them. The helper writes frontmatter to `active_path` then runs `git mv active archive`. `git mv` only re-stages the rename based on the INDEX entry of the source — it does NOT re-stage post-write content. Result: the rename lands in the commit, but the `status: archived` / `merged_pr: <PR>` / `archived_at: <date>` edits are silently left in the working tree.'
---

84. **`archive_workflow_only_ticket` helper does not stage the frontmatter updates it writes; only the rename lands in the commit.** Confirmed on 2026-04-29 during the retroactive cleanup of tickets #79 and #80 (PR-after-#126). The helper's order is: (a) `active_path.write_text(new_text)` with updated frontmatter, then (b) `subprocess.run(["git", "mv", str(active_path), str(archive_path)], ...)`. `git mv` is `git rm --cached <src> + git add <dst>` over the INDEX, but the INDEX entry for `<src>` is the OLD content; `write_text` mutated the working tree but did not stage. So `git add <dst>` re-stages the rename with the OLD content. The frontmatter updates remain in the working tree as unstaged modifications. Confirmed via `git show HEAD:<archive_path>` returning the pre-helper content even though the working tree showed the post-helper content. **Concrete fix:** swap the order — first `subprocess.run(["git", "mv", str(active_path), str(archive_path)], ...)` (stages the rename of the OLD content), then `archive_path.write_text(new_text)` (mutates the renamed file in the working tree), then `subprocess.run(["git", "add", str(archive_path)], ...)` (stages the content update on top of the rename). Alternative: keep the current order but add `subprocess.run(["git", "add", str(archive_path)], ...)` after the `git mv`, which re-stages the working-tree content over the index entry. Both are equivalent in result; the latter is a smaller diff. **Tests:** extend `task2/tests/test_archive_workflow_only_ticket.py::test_archives_ticket_successfully` to assert `subprocess.run(["git", "diff", "--staged", "--stat"], cwd=repo_root, capture_output=True)` exit succeeds and the staged diff includes BOTH the rename AND the frontmatter content change for the moved file. The current test only inspects the file content on disk, which masks the staging bug. Add a second test `test_archives_ticket_stages_content_change` that, after the helper runs, asserts `subprocess.run(["git", "diff", "--name-only"], cwd=repo_root, capture_output=True)` (working-tree-vs-index) returns NO entries for the archived file — i.e. the working tree matches the index. **Acceptance:** when the next workflow-only PR merges via `/full_task2`, the auto-generated `chore/archive-ticket-<NN>` PR contains the rename AND the frontmatter updates in a single commit; `git status` is clean immediately after the helper invocation. *Why useful:* without this, every workflow-only `/full_task2` iteration's archive commit half-archives the ticket — the file moves to `archive/` but its `status` / `merged_pr` / `archived_at` stay null, defeating the very thing #82 was supposed to fix. The retroactive cleanup of #79/#80 had to add a follow-up commit to repair this; every future iteration will need the same workaround until this lands. *Risks:* (a) the test must use a real `subprocess.run` for `git diff` — mocking it would defeat the purpose; the existing `_make_fake_run` in the test file already passes through non-`regen_tickets_index` calls to the real `subprocess.run`, so the path is already there. (b) if the swap-order fix is chosen, ensure the post-mv `archive_path.write_text` is wrapped in idempotency — a re-run on an already-archived ticket must be a no-op (the existing `if archive_path.exists(): ... return` early-out handles this). *Trigger:* `/auto_task2` iteration 8 on 2026-04-29 — retroactive cleanup of #79 and #80 surfaced the staging bug.
