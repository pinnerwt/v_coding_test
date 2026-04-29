## Context

`.github/workflows/task2-benchmark.yml` has a "Post diff as PR comment" step that uses `gh pr comment --edit-last` with `2>/dev/null` to suppress errors from the "no prior comment" path. The suppression is too broad: it hides auth failures, rate-limit responses, and GitHub 5xx errors, all of which cause the fallback `gh pr comment` to create a redundant comment. Subsequent runs then edit the wrong comment, drifting the update chain and potentially leaving multiple bot comments on the PR.

The current step (lines 55–76 of the workflow at time of ticket filing):

```yaml
- name: Post diff as PR comment
  if: always() && github.event_name == 'pull_request'
  env:
    GH_TOKEN: ${{ github.token }}
    HEAD_REF: ${{ github.head_ref }}
    PR_NUMBER: ${{ github.event.pull_request.number }}
    REPO: ${{ github.repository }}
    WORKSPACE: ${{ github.workspace }}
  run: |
    set -euo pipefail
    SAFE_BRANCH=$(...)
    DIFF_FILE="$WORKSPACE/task2/benchmark/${SAFE_BRANCH}/diff.md"
    if [ ! -f "$DIFF_FILE" ] || [ ! -s "$DIFF_FILE" ]; then
      echo "No diff.md found for branch ${SAFE_BRANCH}; skipping PR comment"
      exit 0
    fi
    gh pr comment "$PR_NUMBER" \
      --edit-last --body-file "$DIFF_FILE" \
      --repo "$REPO" 2>/dev/null \
    || gh pr comment "$PR_NUMBER" \
      --body-file "$DIFF_FILE" \
      --repo "$REPO"
```

## Goals / Non-Goals

**Goals:**
- True idempotency: detect the prior bot comment by `user.login == "github-actions[bot]"` and update it by id.
- Error propagation: detection failures exit non-zero; only "no prior comment" (empty stdout, exit 0) falls through to create.
- Correct `permissions:` block including `issues: write`.
- A Python YAML-shape test that goes red before the edit and green after.

**Non-Goals:**
- Multiple bot comments (only the latest by id is updated; prior duplicates are not deleted — that's out of scope).
- Replacing `gh` with a Python script or a custom GitHub Action.
- Adding `actionlint` as a hard CI dependency (document it as a manual verification step only).
- Any changes to `task2/scripts/`, `task2/agent/`, or other Python modules.

## Decisions

### Detection via `gh api` + `--jq` + `tail -1`

`gh api "repos/$REPO/issues/$PR_NUMBER/comments" --jq '.[] | select(.user.login == "github-actions[bot]") | .id' | tail -1`

This returns the numeric id of the last bot comment, or empty string if none exists. The `tail -1` ensures we handle the case where prior failures left multiple bot comments: we always update whichever is last. Alternative considered: iterate over all bot comment ids and delete extras. Rejected — out of scope; updating the last one is sufficient for correctness.

### Update via `gh api --method PATCH` with `-f body=@<file>`

`gh api --method PATCH "/repos/$REPO/issues/comments/$COMMENT_ID" -f "body=@$DIFF_FILE"`

The `-f body=@<file>` form reads the file and passes it as the field value, correctly handling multi-line Markdown with embedded quotes and backticks. Alternative considered: `-F body="$(cat $DIFF_FILE)"`. Rejected — command substitution strips trailing newlines and can exceed shell argument length limits on large diffs.

Note: `gh api PATCH /repos/.../issues/comments/<id>` requires the `issues` write scope even though the comment is on a pull request. GitHub's REST API routes all PR review comments and PR issue comments through the Issues endpoint (`/repos/:owner/:repo/issues/:issue_number/comments`). The `pull-requests: write` permission covers `gh pr comment` but NOT `gh api PATCH /issues/comments/<id>`. Both permissions are therefore required.

### `set -euo pipefail` governs the whole `run:` block

`set -e` ensures that if the detection `gh api` call returns non-zero (auth error, network error, API error), the step fails immediately without falling through to the create branch. Only two outcomes reach the conditional:
- exit 0, empty stdout → no prior comment → create
- exit 0, non-empty stdout → prior comment found → update

### Python YAML-shape test as the load-bearing red/green

The test loads `.github/workflows/task2-benchmark.yml` via `yaml.safe_load`, navigates to the job's steps list, finds the step named "Post diff as PR comment", and asserts the `run:` string contains:
- the detection `gh api repos/${{ github.repository }}/issues/${{ github.event.pull_request.number }}/comments` call
- `gh api --method PATCH` for the update path

This test fails before the YAML edit (red) and passes after (green), satisfying the TDD discipline from CLAUDE.md. `actionlint` is documented as a recommended local verification step but is not added as a CI dependency or a `uv` dev dep.

## Risks / Trade-offs

- **`issues: write` is broader than strictly needed** — it grants write access to all issues, not just comments. This is unavoidable; GitHub does not offer a finer-grained scope for updating a single comment. Risk is low: the workflow only calls the update-comment endpoint, and the `GH_TOKEN` is the default GITHUB_TOKEN scoped to the repository.
- **`tail -1` picks the last bot comment, not the "canonical" one** — if multiple bot comments exist (from prior failures), we update the last one. The others remain as noise. This is acceptable for P0 correctness; a cleanup sweep is out of scope.
- **The Python test is a YAML-shape test, not a live integration test** — it cannot verify that the `gh` commands actually succeed against the GitHub API. That is acceptable per the ticket's explicit acknowledgement that "this is YAML and lives uncovered until it bites."
- **`gh api` with `--jq` requires `gh` ≥ 2.x and `jq`** — both are available on `ubuntu-latest` GitHub-hosted runners. No version pinning is needed.
