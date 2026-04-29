## 1. Red — Write failing tests

- [x] 1.1 Write `task2/tests/test_archive_workflow_only_ticket.py::test_archives_ticket_successfully`: using a `tmp_path`-rooted fixture with a valid `active/<NNN>-<slug>.md` ticket file (minimal but valid YAML frontmatter with all 14 required fields), assert that after calling `archive_workflow_only_ticket(slug, ticket_number, pr_number, iso_date, repo_root=tmp_path)` — (a) the file exists at `archive/<NNN>-<slug>.md`, (b) frontmatter has `merged_pr == pr_number`, `archived_at == iso_date`, `status == "archived"`, and (c) `INDEX.md` has been written (stub: just assert it exists or contains the archive header).
- [x] 1.2 Write `test_archives_ticket_idempotently`: call `archive_workflow_only_ticket(...)` twice on the same fixture; assert the second call does not raise and the file is still at `archive/<NNN>-<slug>.md` with unchanged frontmatter.
- [x] 1.3 Write `test_rejects_missing_ticket_file`: with no file at `active/` or `archive/`, assert `FileNotFoundError` is raised.
- [x] 1.4 Write `test_rejects_mismatched_ticket_number`: with `active/082-fast-path-ticket-archival-hygiene.md` present, call with `ticket_number=99`; assert `ValueError` is raised before any mutation (check `archive/` is empty).
- [x] 1.5 Run `(cd task2 && uv run pytest tests/test_archive_workflow_only_ticket.py -x)` and confirm all four tests fail with `ModuleNotFoundError` or `ImportError` (module does not exist yet — expected red reason).

## 2. Green — Minimal implementation

- [x] 2.1 Create `task2/scripts/archive_workflow_only_ticket.py` with the function `archive_workflow_only_ticket(slug: str, ticket_number: int, pr_number: int, iso_date: str, repo_root: Path) -> None` and a `main()` entry point that accepts `--slug`, `--ticket-number`, `--pr-number`, `--date`, and `--repo-root` CLI args.
- [x] 2.2 Implement input validation: construct `active_path = repo_root / "task2/tickets/active" / f"{ticket_number:03d}-{slug}.md"` and `archive_path = repo_root / "task2/tickets/archive" / f"{ticket_number:03d}-{slug}.md"`. Raise `FileNotFoundError` if neither exists. Raise `ValueError` if the filename's leading digits do not equal `ticket_number`.
- [x] 2.3 Implement idempotency guard: if `archive_path` already exists and its frontmatter has non-null `merged_pr`, return immediately.
- [x] 2.4 Implement frontmatter edit using pyyaml round-trip: parse the `---`-delimited block with `yaml.safe_load`, set `status = "archived"`, `merged_pr = pr_number`, `archived_at = iso_date`, re-serialize with `yaml.dump(..., allow_unicode=True, sort_keys=False)`, write back to `active_path`.
- [x] 2.5 Implement `git mv active_path archive_path` via `subprocess.run(["git", "mv", str(active_path), str(archive_path)], cwd=str(repo_root), check=True)`.
- [x] 2.6 Invoke `regen_tickets_index.py` via subprocess: `subprocess.run(["uv", "run", "python", "scripts/regen_tickets_index.py"], cwd=str(repo_root / "task2"), check=True)`.
- [x] 2.7 Run `(cd task2 && uv run pytest tests/test_archive_workflow_only_ticket.py -x)` and confirm all four tests pass (green). Note: tests for `git mv` and INDEX regen may need to mock `subprocess.run` or use a real git repo fixture — design the fixture accordingly in step 1.1.

## 3. Integration — skill prose

- [x] 3.1 Update `.claude/skills/full_task2/SKILL.md` Phase 3 workflow-only branch: replace the current 2-command block (`gh pr merge ... && git checkout master && git pull --ff-only`) with the 5-step post-merge sequence documented in `design.md`.
- [x] 3.2 The updated prose should: (a) note the PR-title parse rule (`re.search(r'\(#(\d+)\)\s*$', pr_title)`), (b) show the subprocess invocation (`(cd task2 && uv run python scripts/archive_workflow_only_ticket.py --slug ... --ticket-number ... --pr-number ... --date ...)`), (c) show the `chore/archive-ticket-<NN>` branch + commit + `gh pr create` + `gh pr merge --squash --delete-branch --auto` + `git pull --ff-only` sequence, and (d) cite `/auto_task2` step 5's `chore/skills-lessons-*` pattern as prior art.
- [x] 3.3 Add a warning-on-parse-failure note: if `re.search` returns `None`, print a warning with the manual invocation command and skip the archival sequence without failing Phase 3.

## 4. Quality gates

- [x] 4.1 `(cd task2 && uv run ruff check .)` clean — no new lint errors.
- [x] 4.2 `(cd task2 && uv run ruff format .)` — apply formatting, then confirm clean.
- [x] 4.3 `(cd task2 && uv run pytest)` clean — full suite passes, no regressions.
- [x] 4.4 Confirm `git diff task2/` touches only `scripts/archive_workflow_only_ticket.py` and `tests/test_archive_workflow_only_ticket.py` (no accidental changes to other modules).
