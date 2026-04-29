## Context

`archive_workflow_only_ticket` (task2/scripts/archive_workflow_only_ticket.py) is a small helper invoked by `/full_task2` to atomically rename a ticket from `active/` to `archive/` and stamp its frontmatter. The current order is:

1. `active_path.write_text(new_text)` — mutates working tree only (not index)
2. `subprocess.run(["git", "mv", active_path, archive_path])` — stages the rename, but `git mv` stages the INDEX entry of the source as it was _before_ `write_text`, so only the rename lands; the frontmatter edits stay in the working tree.

The result: every archive commit contains the move but not the content update; `git status` after the helper shows the archive file as `M` (unstaged modification).

## Goals / Non-Goals

**Goals:**

- Ensure a single `archive_workflow_only_ticket` call leaves both the rename AND the updated frontmatter fully staged in the git index.
- Provide regression tests that catch any future re-introduction of this bug by asserting index state (not just working-tree content).

**Non-Goals:**

- Changing any public interface (function signature, CLI flags, return type).
- Modifying behavior for idempotent re-runs, error paths, or `regen_tickets_index`.
- Adding logging, error messages, or documentation.

## Decisions

### Decision: Use swap-order approach (A) rather than keep-order + extra `git add` (B)

Both approaches are equivalent in git outcome. Approach A (swap order: `git mv` → `write_text` at `archive_path` → `git add archive_path`) is chosen because:

- It is semantically cleaner: `git mv` operates on the index entry of the file as it exists in the index (old content = committed state), then `write_text` mutates only the destination in the working tree, and `git add` stages that mutation. No intermediate state where the active file has been written-to but not yet moved.
- Approach B (keep old order, add trailing `git add`) stages the modified content _before_ the rename, which relies on `git mv` then updating the index entry for the destination over what was just staged — that works but is less obvious.

### Decision: Real `subprocess.run` for git assertions in tests

The `_make_fake_run` helper already passes through all non-`regen_tickets_index` subprocess calls to the real `subprocess.run`. New test assertions (`git diff --staged --stat`, `git diff --name-only`) are real git invocations on the tmp-path repo — not mocked — because mocking them would defeat the purpose of the regression test.

## Risks / Trade-offs

- [Risk: `archive_path.write_text` fails after `git mv`] → The rename is already staged; the write failure leaves the working tree in a partial state. Mitigation: this is the same risk as the current code (which writes before mv); the helper has no transactional guarantee and the caller is expected to abort on exception. No change to error-handling posture is required.
- [Risk: tmp-path git repo in tests interferes with host repo config] → Mitigated by the existing `_setup_git_repo` which sets `user.email` and `user.name` locally; no hooks or sign-off settings are inherited.

## Migration Plan

No deployment steps needed. The helper is called in-process by `/full_task2`; updating the file is sufficient. No rollback strategy required — the fix is a 3-line reorder with an appended `subprocess.run`.
