## MODIFIED Requirements

### Requirement: CI workflow posts diff.md as a PR comment

`.github/workflows/task2-benchmark.yml` SHALL contain a step named "Post diff as PR comment" with the following behaviour:

1. The step is conditional on `always() && github.event_name == 'pull_request'`.
2. The step reads `task2/benchmark/${{ github.head_ref }}/diff.md` (using the sanitized branch name).
3. If the file does not exist or is empty, the step exits 0 with a notice and skips posting.
4. Otherwise, the step detects any prior bot comment by calling `gh api "repos/$REPO/issues/$PR_NUMBER/comments"` with `--jq '.[] | select(.user.login == "github-actions[bot]") | .id'` and piping the result through `tail -1` to obtain the last bot comment id (or empty string if none exists). The detection call runs under `set -euo pipefail`; a non-zero exit from the detection call propagates immediately — the step MUST NOT fall through to the create path on detection failure.
5. When a prior bot comment id is found (non-empty detection result), the step updates it via `gh api --method PATCH "repos/$REPO/issues/comments/$COMMENT_ID"` passing the diff file content as the `body` field using `-F "body=@$DIFF_FILE"` (typed field, capital F) so that `@<filename>` reads file contents — `-f` would send the literal `@<filename>` string, not the file's contents.
6. When no prior bot comment exists (detection returned empty stdout, exit 0), the step creates a new comment via `gh pr comment "$PR_NUMBER" --body-file "$DIFF_FILE" --repo "$REPO"`.
7. The step MUST NOT use `--edit-last` with `2>/dev/null` — that pattern is replaced by the detection+update logic above.
8. The workflow `permissions:` block SHALL include both `pull-requests: write` and `issues: write`. The `issues: write` scope is required because GitHub's REST API routes PR comment updates through the Issues endpoint (`PATCH /repos/:owner/:repo/issues/comments/:id`), and `pull-requests: write` alone does not grant write access to that endpoint.

#### Scenario: CI detects prior bot comment and updates it via PATCH

- **GIVEN** a PR build where branch != master
- **AND** `task2/benchmark/<branch>/diff.md` exists and is non-empty
- **AND** `gh api .../issues/<n>/comments` filtered by `user.login == "github-actions[bot]"` returns a non-empty comment id
- **WHEN** the comment step runs
- **THEN** the step calls `gh api --method PATCH /repos/.../issues/comments/<id>` with the diff file content
- **AND** the step does NOT call `gh pr comment --edit-last`
- **AND** the step exits 0

#### Scenario: CI creates new comment when no prior bot comment exists

- **GIVEN** a PR build where branch != master
- **AND** `task2/benchmark/<branch>/diff.md` exists and is non-empty
- **AND** the detection call returns empty stdout (no prior bot comment), exit 0
- **WHEN** the comment step runs
- **THEN** the step calls `gh pr comment "$PR_NUMBER" --body-file "$DIFF_FILE" --repo "$REPO"` to create a fresh comment
- **AND** the step exits 0

#### Scenario: Detection call failure propagates — step does not silently fall through

- **GIVEN** a PR build where branch != master
- **AND** `task2/benchmark/<branch>/diff.md` exists and is non-empty
- **AND** the `gh api` detection call exits non-zero (e.g. auth error, network error, API 5xx)
- **WHEN** the comment step runs under `set -euo pipefail`
- **THEN** the step exits non-zero immediately after the detection call
- **AND** the step MUST NOT proceed to call `gh pr comment` or `gh api --method PATCH`

#### Scenario: CI skips comment when diff.md is absent

- **GIVEN** a PR build where `task2/benchmark/<branch>/diff.md` does NOT exist
- **WHEN** the comment step runs
- **THEN** the step exits 0 without calling any `gh` comment command

#### Scenario: CI skips comment on push to master (not a PR)

- **GIVEN** `github.event_name != 'pull_request'`
- **WHEN** the comment step is evaluated
- **THEN** the step is skipped entirely (conditional is false)

#### Scenario: YAML-shape test validates detection and update call presence

- **GIVEN** `.github/workflows/task2-benchmark.yml` has been edited with the idempotent comment logic
- **WHEN** `task2/tests/test_workflow_pr_comment.py` is run via `uv run pytest`
- **THEN** the test asserts the step's `run:` body contains `gh api` and `/comments`
- **AND** the test asserts the step's `run:` body contains `select(.user.login == "github-actions[bot]")` (the `--jq` filter)
- **AND** the test asserts the step's `run:` body contains `gh api --method PATCH`
- **AND** the test asserts the step's `run:` body contains `-F "body=@`
- **AND** the test asserts the step's `run:` body does NOT contain `--edit-last` or `2>/dev/null`
- **AND** the test asserts the workflow `permissions["issues"]` equals `"write"`
- **AND** the test passes (green)

## ADDED Requirements

### Requirement: workflow permissions include issues write for comment PATCH

The `permissions:` block at the top level of `.github/workflows/task2-benchmark.yml` SHALL include:

- `pull-requests: write` (already present; required for `gh pr comment`)
- `issues: write` (new; required for `gh api --method PATCH /repos/.../issues/comments/<id>`)

#### Scenario: permissions block contains both pull-requests and issues write

- **GIVEN** `.github/workflows/task2-benchmark.yml` is loaded via `yaml.safe_load`
- **WHEN** the `permissions` key is accessed
- **THEN** `permissions["pull-requests"]` equals `"write"`
- **AND** `permissions["issues"]` equals `"write"`
