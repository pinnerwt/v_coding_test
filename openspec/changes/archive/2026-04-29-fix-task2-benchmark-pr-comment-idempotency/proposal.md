## Why

`.github/workflows/task2-benchmark.yml` posts the WebVoyager `diff.md` as a PR comment with:

```
gh pr comment "$PR_NUMBER" --edit-last --body-file "$DIFF_FILE" --repo "$REPO" 2>/dev/null \
|| gh pr comment "$PR_NUMBER" --body-file "$DIFF_FILE" --repo "$REPO"
```

`2>/dev/null` silently discards all stderr from the `--edit-last` call, including real failures (auth errors, rate limits, network timeouts, GitHub 5xx). When a transient failure occurs, the fallback `gh pr comment` creates a fresh comment. On the next run `--edit-last` finds that new comment as the "last" one and updates it — silently abandoning the original comment. Over multiple transient failures the PR accumulates duplicate bot comments and the update chain drifts to whichever comment happens to be last. CI gives no signal that any of this went wrong.

The correct fix is idempotency by comment-author identity: detect the existing bot comment by filtering `GET /issues/<n>/comments` to `user.login == "github-actions[bot]"`, then `PATCH` that comment by id. If no prior comment exists (empty detection result, exit 0), fall through to create. Any non-zero exit from the detection call propagates immediately — `set -e` ensures the workflow fails loudly rather than silently double-posting.

## What Changes

- The "Post diff as PR comment" step in `.github/workflows/task2-benchmark.yml` is rewritten to use `gh api` for detection and update, with `gh pr comment` reserved only for the first-ever post.
- The `permissions:` block in the workflow gains `issues: write` (required for `PATCH /repos/.../issues/comments/<id>`; GitHub REST routes PR comments through the Issues API even though they appear on a PR).
- A Python test (`task2/tests/test_workflow_pr_comment.py`) asserts on the YAML structure of the step before the YAML is edited (red), then passes after the edit (green). This is the load-bearing test; `actionlint` is a recommended manual check, not a CI gate.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `baseline-diff`: The requirement "CI workflow posts diff.md as a PR comment" is refined to mandate idempotent update-by-bot-comment-id semantics, correct permissions, and non-swallowed error propagation.

## Impact

- **`.github/workflows/task2-benchmark.yml`** — "Post diff as PR comment" step `run:` body; `permissions:` block (add `issues: write`).
- **`task2/tests/test_workflow_pr_comment.py`** — new test file asserting YAML shape of the step.
- No Python production code changes, no dependency additions, no schema changes.
- Deployment: no Zeabur impact; this is a CI-only change.
