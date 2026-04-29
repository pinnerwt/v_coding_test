## 1. Red — failing YAML-shape test

- [ ] 1.1 Create `task2/tests/test_workflow_pr_comment.py`. The test SHALL:
  - Load `.github/workflows/task2-benchmark.yml` relative to the repo root using `pathlib.Path` and `yaml.safe_load`.
  - Navigate to `workflow["jobs"]["verify"]["steps"]` and find the step whose `name` equals `"Post diff as PR comment"`.
  - Assert the step's `run` string contains `gh api` and `/comments` (the detection call shape — env-var-based, since the workflow uses `$REPO`/`$PR_NUMBER` not `${{ ... }}` literals inside `run:`).
  - Assert the step's `run` string contains `select(.user.login == "github-actions[bot]")` (the `--jq` filter pinning detection by author identity).
  - Assert the step's `run` string contains `gh api --method PATCH` (the update call).
  - Assert the step's `run` string contains `-F "body=@` (typed-field form so `gh api` reads file contents; `-f` would send the literal `@<filename>` string).
  - Assert the step's `run` string does NOT contain `--edit-last` (the deprecated path) or `2>/dev/null` (the silent-swallow pattern).
  - Assert the `workflow["permissions"]["issues"]` equals `"write"`.
- [ ] 1.2 Run `uv run pytest task2/tests/test_workflow_pr_comment.py -x` from `task2/` and confirm every assertion **fails** — the current YAML uses `--edit-last` and has no `issues: write` permission, so all three asserts fail for the expected reason.
- [ ] 1.3 Commit the new test file as `test(task2): red YAML-shape test for idempotent PR comment step (#52)`.

## 2. Green — edit the workflow YAML

- [ ] 2.1 Open `.github/workflows/task2-benchmark.yml` and add `issues: write` to the `permissions:` block alongside the existing `pull-requests: write`.
- [ ] 2.2 Replace the `run:` body of the "Post diff as PR comment" step with the following multi-line script (preserve `set -euo pipefail` and the existing `SAFE_BRANCH` / `DIFF_FILE` guard):

  ```
  set -euo pipefail
  SAFE_BRANCH=$(uv run python -c "import sys; from scripts.benchmark import sanitize_branch; print(sanitize_branch(sys.argv[1]))" "$HEAD_REF")
  DIFF_FILE="$WORKSPACE/task2/benchmark/${SAFE_BRANCH}/diff.md"
  if [ ! -f "$DIFF_FILE" ] || [ ! -s "$DIFF_FILE" ]; then
    echo "No diff.md found for branch ${SAFE_BRANCH}; skipping PR comment"
    exit 0
  fi
  COMMENT_ID=$(gh api "repos/$REPO/issues/$PR_NUMBER/comments" \
    --jq '.[] | select(.user.login == "github-actions[bot]") | .id' \
    | tail -1)
  if [ -n "$COMMENT_ID" ]; then
    gh api --method PATCH "repos/$REPO/issues/comments/$COMMENT_ID" \
      -F "body=@$DIFF_FILE"
  else
    gh pr comment "$PR_NUMBER" --body-file "$DIFF_FILE" --repo "$REPO"
  fi
  ```

  Key constraints:
  - Do NOT add `2>/dev/null` anywhere.
  - Do NOT use `--edit-last`.
  - The detection `gh api` call runs inside `set -e`; any non-zero exit propagates immediately.
  - `-F "body=@$DIFF_FILE"` (typed-field form, capital F) is used for the PATCH body so that `@<filename>` is interpreted as "read file contents" — the `-f`/`--raw-field` flag does NOT interpret `@<filename>` and would send the literal string `@/path/...` as the comment body.
  - Both `gh api` URLs use the `repos/...` form (no leading slash) for consistency.

- [ ] 2.3 Run `uv run pytest task2/tests/test_workflow_pr_comment.py -x` from `task2/` and confirm all assertions **pass**.
- [ ] 2.4 Run `uv run pytest task2/` to confirm no existing tests are broken.
- [ ] 2.5 Commit the YAML edit as `fix(ci): idempotent PR comment via gh api detect+patch (#52)`.

## 3. Linting and format check

- [ ] 3.1 Run `uv run ruff check .` from `task2/` — must be clean (the new test file must pass lint).
- [ ] 3.2 Run `uv run ruff format .` from `task2/` and commit any formatting-only changes as `chore(task2): ruff format`.
- [ ] 3.3 (Optional, manual) Run `actionlint .github/workflows/task2-benchmark.yml` locally if `actionlint` is available (`brew install actionlint` on macOS or `go install github.com/rhysd/actionlint/cmd/actionlint@latest`). Actionlint is NOT added as a hard CI dependency — the Python YAML-shape test is the load-bearing gate. If actionlint reports a finding, fix it and fold the fix into the YAML-edit commit.

## 4. Final validation

- [ ] 4.1 Run the full `task2/` test suite one final time: `uv run pytest` from `task2/` — green bar required.
- [ ] 4.2 Verify `git diff HEAD .github/workflows/task2-benchmark.yml` shows: `issues: write` added to `permissions:`, `--edit-last` removed, `2>/dev/null` removed, `gh api` detection call present, `gh api --method PATCH` update call present.
- [ ] 4.3 Stage commits in conventional-commit style preserving real history (no squash-the-world).
