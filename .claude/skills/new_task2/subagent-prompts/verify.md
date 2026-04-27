# Subagent prompt — opsx:verify (verification pass)

Pass this verbatim to a `general-purpose` subagent (`model: sonnet`) at Step 7 of `/new_task2`. The orchestrator substitutes the placeholders (`{{...}}`) before sending.

Description for the Agent call: `Verify opsx change {{change-name}}`.

Rationale for `sonnet`: verification follows a defined rubric (`/opsx:verify` output → close gap → re-run). The orchestrator re-runs the verifier itself in the main thread for the final judgment call.

---

You are verifying OpenSpec change `{{change-name}}` in the `vici` repo, located at `openspec/changes/{{change-name}}/`. You have no prior conversation context — everything you need is below.

**Branch and scope**

Stay on the current branch `{{branch}}`. Do not switch branches, push, or open a PR.

**Task**

Invoke `/opsx:verify` on `{{change-name}}`. Address every gap it reports — **extend tests first** when behavior is missing, then code. Re-run `/opsx:verify` until it is clean.

**Commit conventions for fixes**

- `fix(task2): address verify feedback for {{change-name}}` for code fixes.
- `test(task2): <what the new test covers>` if the change is purely additional tests.

**Pre-commit gate (mandatory before every commit)**

```bash
cd task2
uv run ruff format .
uv run ruff check .
uv run pytest
```

All three must be clean. Never `--no-verify`.

**No comments or docstrings** in any non-test file. If `/opsx:verify` flags a missing comment/docstring, push back — close the gap with a clearer name or a test, not a comment. Same rule as the apply step: `/simplify` will strip them, so don't write them in the first place.

**Report back**

- Final `/opsx:verify` output.
- List of commits added.
- Confirmation that the verifier reports zero gaps.
