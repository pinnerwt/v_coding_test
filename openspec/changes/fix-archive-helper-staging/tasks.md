## 1. Regression Tests (Red Phase)

- [ ] 1.1 In `task2/tests/test_archive_workflow_only_ticket.py`, extend `test_archives_ticket_successfully` to call `subprocess.run(["git", "diff", "--staged", "--stat"], cwd=str(repo_root), capture_output=True, check=True)` after the helper runs and assert the output contains both the archive filename (rename) and a `+` line indicating content changes (frontmatter diff). The test must use the real `subprocess.run` for this assertion — do not wrap it in the mock patch.
- [ ] 1.2 Add `test_archives_ticket_stages_content_change` in the same file: set up a real tmp-path git repo, commit the active ticket, run the helper (with `regen_tickets_index` mocked out), then assert that `subprocess.run(["git", "diff", "--name-only"], cwd=str(repo_root), capture_output=True, check=True).stdout.strip()` is empty (working tree matches index for all files).
- [ ] 1.3 Run `uv run pytest task2/tests/test_archive_workflow_only_ticket.py -x` from repo root and confirm the two new assertions fail (red bar for the right reason).

## 2. Production Fix

- [ ] 2.1 In `task2/scripts/archive_workflow_only_ticket.py`, reorder the sequence after frontmatter computation: first call `subprocess.run(["git", "mv", str(active_path), str(archive_path)], cwd=str(repo_root), check=True)`, then call `archive_path.write_text(new_text)`, then call `subprocess.run(["git", "add", str(archive_path)], cwd=str(repo_root), check=True)`. Remove the existing `active_path.write_text(new_text)` call that preceded `git mv`.
- [ ] 2.2 Run `uv run pytest task2/tests/test_archive_workflow_only_ticket.py -x` and confirm all tests pass (green bar).

## 3. Linting

- [ ] 3.1 Run `uv run ruff check task2/scripts/archive_workflow_only_ticket.py task2/tests/test_archive_workflow_only_ticket.py` and fix any issues.
- [ ] 3.2 Run `uv run ruff format task2/scripts/archive_workflow_only_ticket.py task2/tests/test_archive_workflow_only_ticket.py` and confirm no diffs.
