# Subagent prompt — opsx:apply (TDD implementation)

Pass this verbatim to a `general-purpose` subagent (`model: sonnet`) at Step 6 of `/new_task2`. The orchestrator substitutes the placeholders (`{{...}}`) before sending.

Description for the Agent call: `Apply opsx change {{change-name}}`.

Rationale for `sonnet`: TDD implementation is the canonical Sonnet workhorse task (Anthropic Advisor Strategy: Opus plans/reviews, Sonnet executes). Cheaper, faster, and benchmark-comparable on code-gen following an existing plan.

---

You are implementing OpenSpec change `{{change-name}}` in the `vici` repo, located at `openspec/changes/{{change-name}}/`. You have no prior conversation context — everything you need is below.

**Branch and scope**

Stay on the current branch `{{branch}}`. Do not switch branches, rebase, push, or open a PR — those are handled outside this subagent.

**Task**

Invoke the `/opsx:apply` skill on `{{change-name}}` and drive every task in `tasks.md` to completion under TDD discipline (red → green → refactor; tests live under `task2/tests/`).

**Tooling — every command runs from the `task2/` directory**

- One-time setup if not already done: `uv sync && uv run playwright install chromium`.
- Tests: `uv run pytest`.
- Lint: `uv run ruff check .` (auto-fix with `uv run ruff check --fix .` only when safe).
- Format: `uv run ruff format .`.

**Per red-green-refactor cycle**

1. **Red** — write the failing test, run `uv run pytest <path-to-new-test>`, confirm it fails for the expected reason. Commit: `test(task2): <what the new failing test covers>`.
2. **Green** — minimal implementation. Run `uv run pytest` until green. Commit: `feat(task2): <what now works>`.
3. **Refactor** (optional, only while green). Re-run `uv run pytest` after each meaningful edit. Commit: `refactor(task2): <what changed>`.

**No comments or docstrings in production code.** Write zero `#` comments and zero docstrings (module, class, or function) in any file under `task2/` that is not a test. Tests may have a single-line docstring only when it materially clarifies intent. Rationale: the `/simplify` pass strips them anyway, so writing them burns tokens for no kept output. Rely on clear naming. The only exception is a one-line comment explaining a non-obvious *why* (hidden constraint, workaround, surprising invariant) — never *what* the code does.

**Pre-commit gate (mandatory before every commit)**

```bash
cd task2
uv run ruff format .
uv run ruff check .
uv run pytest
```

All three must be clean. Stage any `ruff format` rewrites into the same commit. Never commit with failing tests or ruff errors. Never use `--no-verify`.

**Other rules**

- Keep commits small enough that the diff matches the message. Do not bundle unrelated changes.
- **Renames / signature changes need a repo-wide grep.** When a task renames a symbol or changes a parameter shape (e.g. `last_action` → `last_actions`, or `dict | None` → `list[dict]`), the artifact `tasks.md` typically only enumerates the obvious touch points. After the migration step, `grep -rn '<old name>\|<old shape sentinel>' task2/` and update every remaining caller — including tests not listed in `tasks.md`. Python doesn't enforce type hints at runtime, so stale `None` arguments to a now-`list`-typed parameter pass tests but violate the new contract; the verify step (Step 7 of `/new_task2`) will flag them otherwise.
- If a task surfaces a design problem, **stop and report back** (per `/opsx:apply` guardrails) instead of papering over it. **Exception:** if the contradiction is purely in the literal `tasks.md` wording (e.g. "reset before X" when correct semantics is "reset after X") and the right behavior is unambiguous from the spec/tests, implement the correct behavior, note the divergence in the report-back, and continue. Don't block on prose drift in scaffold artifacts.
- Honor `task2/CLAUDE.md` and the repo-root `CLAUDE.md` (TDD, `uv`, `ruff`, configurable LLM base URL).

**Report back**

- List of commits made (sha + subject).
- Final `pytest` / `ruff` status.
- Any tasks left unchecked in `tasks.md`.
- Any design questions that surfaced.
