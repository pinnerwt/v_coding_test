## Why

WebVoyager-2 fails at step 4 with `failure_class=tool_error` and `failure_detail='unknown error'` (run `task2/benchmark/task2-fix-trim-history-preserve-first-group/webvoyager/20260429_225802.json`). The literal string "unknown error" comes from `scripts/eval.py:233` where `ev.diff.get("error", "unknown error")` falls back because `agent/loop.py`'s click and type dispatch always emit `ActEvent` with `diff={}`, dropping the underlying playwright exception. This leaves the next iteration with no actionable signal — there is no way to tell whether the click failed because the element was detached, the page crashed, the locator returned a stale handle, or anything else. Per ticket #99, the next iteration cannot make progress on webvoyager-2 without a concrete classified failure_detail. The `failure-classification` spec already promises that `ActEvent.diff` carries a meaningful `error` field; the producer just doesn't populate it.

## What Changes

- `agent/loop.py` `_dispatch` click branch: capture the playwright exception (timeout or generic error) and pass `diff={"error": "<ExceptionClass>: <message>"}` to `_emit_act_event` when outcome is `"timeout"` or `"error"`. Successful outcomes still emit `diff={}`.
- `agent/loop.py` `_dispatch` type branch: same treatment.
- `agent/loop.py` `_emit_act_event`: accept an optional `diff: dict[str, Any] | None = None` argument so the caller can pass a populated dict; default behaviour (`diff={}`) is preserved.
- No change to `scripts/eval.py` — `_classify_failure` already reads `ev.diff.get("error", ...)`; the existing fallback string is kept so trace-only tests that don't populate `diff` still classify, but live runs will surface the real exception.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `agent-loop`: the `click tool dispatch in loop` and `type tool dispatch in loop` requirements MODIFIED to require `diff={"error": "<class>: <message>"}` (the exception's `__class__.__name__` followed by `": "` followed by `str(exc)`) on `outcome` in `{"error", "timeout"}` (was `diff={}` unconditionally).

## Impact

- `task2/agent/loop.py`: ~10 lines of change across the click branch, type branch, and `_emit_act_event` signature.
- `task2/tests/agent/test_loop.py` (or wherever click/type dispatch is tested): one new red test asserting `diff["error"]` carries the exception class+message on a forced playwright failure.
- Downstream WebVoyager benchmark: webvoyager-2 (and any other live case that hits a click/type error) will now surface a real `failure_detail` in `results.json`. Pass-rate is unchanged by this fix alone — it converts an opaque failure into a classified one so the *next* iteration can target the underlying error.
- No API change visible to the LLM; no schema change to `ActEvent` (the `diff: dict[str, Any]` field already exists and is JSON-serialised via `TraceWriter`).
