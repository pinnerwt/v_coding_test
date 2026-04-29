## Context

`agent/loop.py` `_dispatch` handles `click` and `type` tool calls by wrapping a single playwright call in a `try/except` block that catches `playwright.sync_api.TimeoutError` and `playwright.sync_api.Error`, classifies the outcome, and emits an `ActEvent` via `_emit_act_event(...)` with a hard-coded `diff={}`. When the case fails, `scripts/eval.py:_classify_failure` looks at the `ActEvent.diff` for an `"error"` key and falls back to the literal string `"unknown error"` when the key is absent — which is always, today.

The `failure-classification` spec already documents that `ActEvent` should carry an `"error"` key in `diff` for the `tool_error` failure_class — this is producer-side drift, not a spec gap.

## Goals / Non-Goals

**Goals:**
- Surface the underlying playwright exception class and message in `ActEvent.diff["error"]` for click and type dispatch when the outcome is `"timeout"` or `"error"`.
- Keep the change a producer-side fix: do not modify `scripts/eval.py`'s classifier, do not touch the `ActEvent` schema in `agent/trace.py`.
- Preserve the existing fallback `"unknown error"` so trace-synthesised tests in `test_eval.py` (which build `ActEvent` directly with a known `diff`) still pass.

**Non-Goals:**
- Fix webvoyager-2's underlying click failure. This change only makes the failure observable; the actual fix (or a follow-up classification) is the next ticket's job once we can read what the exception was.
- Add diagnostic info to other tools (`goto`, `read`, `screenshot`, `done`). They have separate failure paths handled elsewhere; expanding scope here would conflict with the one-character spec changes the proposal narrows to.
- Truncate or sanitise the exception message. Playwright error messages are bounded; if a future log shows them growing unboundedly we can cap then.

## Decisions

**Decision 1 — Pass exception detail via the existing `diff` dict.**

The `ActEvent` already has a `diff: dict[str, Any]` field; the failure-classification spec already reads `diff["error"]`. Adding a new field to `ActEvent` would require a schema migration. Reusing `diff["error"]` is the smallest blast-radius change and keeps the producer/consumer contract symmetric.

Alternatives considered:
- Adding a new `error: str | None` field to `ActEvent` — rejected: schema change, requires `trace.py` and replay updates.
- Logging the exception and leaving `diff={}` — rejected: classifier still reads `"unknown error"`; logs are not part of the result file the next ticket sees.

**Decision 2 — Format `diff["error"]` as `f"{exc.__class__.__name__}: {exc}"`.**

The string `<Class>: <message>` is the same shape `repr(exc)` would give (minus the surrounding parens) and is what the failure-classification spec scenarios already model (`"TimeoutError"`, `"TimeoutError on selector X"`). It is short, round-trips through JSON, and is human-readable in the result file.

Alternatives considered:
- `repr(exc)` — works but adds parens and quoting noise (`"TimeoutError('Locator.click: Timeout 5000ms exceeded.')"`); the explicit `f"{cls}: {msg}"` form is what scoreboards prefer.
- Full traceback — rejected: large, noisy, and the underlying exception class+message is enough for classification.

**Decision 3 — Make `_emit_act_event` accept an optional `diff` arg defaulting to `None`.**

`_emit_act_event` is private to `loop.py` and called from exactly two places (click, type). A new keyword-only `diff` parameter that defaults to `None` and is normalised to `{}` inside the function preserves the existing call sites' behaviour (they pass nothing and get `diff={}`) while letting the error/timeout branches pass a populated dict.

Alternatives considered:
- Inline the `ActEvent` construction in the dispatch branches and skip `_emit_act_event` — rejected: duplicates the seq/ts/run_id boilerplate.
- A separate `_emit_act_event_with_error` helper — rejected: two functions doing the same thing differ only in a parameter, which is a parameter-sprawl smell.

## Risks / Trade-offs

[Risk] Playwright exception messages may include unstable details (selectors, timing) that make per-case `failure_detail` strings noisy across runs and trip flake detection in `/done_pr` step 1b's cross-run recurrence check.
→ Mitigation: the cross-run check in `/done_pr` already compares only the first 80 characters of `failure_detail`. The exception class name (`TimeoutError`, `Locator.click`) is deterministic; selector text in the message body may vary but the first 80 chars usually stabilise on the class+method prefix. If post-merge the check becomes too strict, narrow it to `failure_class + exception_class_name` in a follow-up ticket.

[Risk] Existing `test_loop.py` / `test_eval.py` tests that construct `ActEvent(diff={})` manually still classify as `("tool_error", "unknown error")` — that string is now an indicator of "trace was synthetic, no real exception". This is fine for unit tests but means real runs and synthetic runs are distinguishable in the result file.
→ Mitigation: this is a *feature*, not a risk. Treat the literal `"unknown error"` in a live result file as a regression signal that the producer drift returned.

[Risk] The dispatch branches currently catch `PlaywrightError` (parent of `PlaywrightTimeoutError`); reordering or losing the `except PlaywrightTimeoutError` first would silently classify timeouts as generic errors.
→ Mitigation: the existing `except PlaywrightTimeoutError` -> `except PlaywrightError` order is preserved; the new `as exc` binding doesn't change the dispatch order.

## Migration Plan

No migration. The change is a semantic widening of `ActEvent.diff` (was effectively `{}`, now optionally `{"error": str}`). Old result files have `diff={}` and continue to classify as `("tool_error", "unknown error")` exactly as before. New result files surface real detail.

## Open Questions

None.
