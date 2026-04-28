## Context

`task2/scripts/eval.py` contains `_classify_failure`, a pure function that maps a trace event list and validator results to a `(failure_class, failure_detail)` pair. It was introduced in ticket #31 (archived). Rule 2.c at line 200-203 currently reads:

```
for ev in events:
    if isinstance(ev, ActEvent) and ev.outcome == "error":
        detail = ev.diff.get("error", "unknown error")
        return "tool_error", str(detail)
```

`ActEvent.outcome` is typed as `Literal["ok", "no_effect", "nav", "timeout", "error"]` (`agent/trace.py:69`). The `"timeout"` variant is emitted when a Playwright `wait_for` call exhausts its deadline. Because rule 2.c only tests `== "error"`, a trace whose only signal is a `timeout` outcome falls through to rule 2.f (`no_done_emitted`) or rule 2.g (`other`), losing the more specific browser-stall signal.

## Goals / Non-Goals

**Goals:**

- `_classify_failure` returns `("tool_error", <non-empty string>)` for any `ActEvent` with `outcome in {"error", "timeout"}`.
- The existing `outcome="error"` behaviour is preserved exactly.
- Spec rule 2.c is updated to match the widened predicate.
- A new TDD test covers the `outcome="timeout"` path.

**Non-Goals:**

- Introducing a new `failure_class` literal (e.g. `"tool_timeout"`): the ticket explicitly chose option (a).
- Changing the scoreboard schema or adding new columns.
- Touching the `_run_case` exception path at line 253, which already hard-codes `failure_class="tool_error"` and is unrelated.

## Decisions

**Decision: inline `in ("error", "timeout")` check, no named constant**

Option A — inline: `ev.outcome in ("error", "timeout")`.
Option B — module-level frozenset: `_TOOL_ERROR_OUTCOMES = frozenset({"error", "timeout"})`.

Chose option A (inline). The predicate is a single two-element membership test used exactly once. A named constant adds indirection without clarity gain; CLAUDE.md prohibits adding abstractions for hypothetical second callers. The inline form matches the pattern used in the rest of `_classify_failure`.

**Decision: implementation site is line 201 only**

The fix is the single equality check on line 201. The `_run_case` exception catch-all at line 253 already sets `failure_class="tool_error"` directly and covers Python-level exceptions (not Playwright-level timeouts surfaced as `ActEvent`). Those two paths are independent; touching line 253 is out of scope.

## Risks / Trade-offs

- **Broadening** — any future `outcome` value added to the `Literal` that should NOT be `tool_error` would be unaffected (it isn't listed in the tuple). Low risk.
- **Detail field** — `ActEvent.diff.get("error", "unknown error")` is the current detail source. For `outcome="timeout"` the same `diff` field is used; callers already populate it with the error message (e.g. `"TimeoutError on selector X"`). If a caller leaves `diff={}`, the fallback `"unknown error"` is still a non-empty string, satisfying the spec.

## Migration Plan

1. Write the failing test (Red): `test_classify_failure_tool_error_timeout` in `task2/tests/test_eval.py`.
2. Change `ev.outcome == "error"` to `ev.outcome in ("error", "timeout")` on line 201 of `task2/scripts/eval.py` (Green).
3. Run `uv run pytest` and `uv run ruff check .` from `task2/` — both must be clean.
4. Archive the change after all tests green.

Rollback: revert the single-line predicate change; no data migration needed.
