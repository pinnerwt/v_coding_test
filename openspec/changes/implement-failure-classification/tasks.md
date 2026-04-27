## 1. Red — CaseResult new fields test

- [ ] 1.1 In `task2/tests/test_eval.py`, add `test_case_result_failure_class_defaults_to_none`: construct `CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])` and assert `failure_class is None` and `failure_detail is None`.
- [ ] 1.2 Add `test_case_result_failure_fields_serialise_to_json`: construct a `CaseResult` with `status="failed"`, `failure_class="no_done_emitted"`, `failure_detail=None`, call `asdict()` then `json.dumps`, assert `"failure_class": "no_done_emitted"` and `"failure_detail": null` appear in the JSON.
- [ ] 1.3 Run `uv run pytest task2/tests/test_eval.py -k "failure_class or failure_detail or failure_fields"` from `task2/` — confirm both tests fail with `TypeError` (fields do not exist yet).

## 2. Red — _classify_failure synthetic trace tests

- [ ] 2.1 Add `test_classify_failure_passing_status_returns_none`: call `_classify_failure([], [], "succeeded")`, `_classify_failure([], [], "unverified")`, `_classify_failure([], [], "skipped")` — each SHALL return `(None, None)`.
- [ ] 2.2 Add `test_classify_failure_supervisor_halt`: build a minimal synthetic `SupervisorEvent(policy="halt", classified_as="Blocked", ...)` (all required `EventBase` fields filled), pass `events=[ev]`, `status="failed"` — assert result `== ("supervisor_halt", ...)` where second element contains `"Blocked"`.
- [ ] 2.3 Add `test_classify_failure_locator_miss`: build a `SupervisorEvent(policy="next_tier")` with a `step_id`, plus a subsequent `LocateEvent(outcome="miss", step_id=same)` with no following `hit` — assert `failure_class == "locator_miss"`.
- [ ] 2.4 Add `test_classify_failure_tool_error`: build an `ActEvent(outcome="error", diff={"error": "TimeoutError"}, ...)` with no `SupervisorEvent` — assert `failure_class == "tool_error"` and second element contains `"TimeoutError"`.
- [ ] 2.5 Add `test_classify_failure_validator_fail`: pass `events=[DoneEvent(verifier={"ok": True}, ...)]`, `validators=[{"name": "title.nonempty", "ok": False}]`, `status="failed"` — assert `failure_class == "validator_fail"` and second element contains `"title.nonempty"`.
- [ ] 2.6 Add `test_classify_failure_schema_error`: pass `events=[DoneEvent(verifier={"ok": False, "reasons": ["missing field: title"]}, ...)]`, `validators=[]`, `status="failed"` — assert `failure_class == "schema_error"` and second element contains `"missing field"`.
- [ ] 2.7 Add `test_classify_failure_no_done_emitted`: pass `events=[]`, `validators=[]`, `status="failed"` — this case should hit `no_done_emitted` since there is no `DoneEvent` — assert `failure_class == "no_done_emitted"`.
- [ ] 2.8 Add `test_classify_failure_other`: construct an event list that has a `DoneEvent(verifier={"ok": True})` and all validators passing but status is still `"failed"` (unusual edge case) — assert `failure_class == "other"`.
- [ ] 2.9 Add `test_classify_failure_supervisor_halt_beats_tool_error`: events list has both `SupervisorEvent(policy="halt")` and `ActEvent(outcome="error")` — assert `failure_class == "supervisor_halt"` (priority ordering).
- [ ] 2.10 Run `uv run pytest task2/tests/test_eval.py -k "classify_failure"` — confirm all 9 tests fail with `ImportError` or `AttributeError` (`_classify_failure` does not exist yet).

## 3. Red — scoreboard failure_class column test

- [ ] 3.1 In `task2/tests/test_score.py` (or the existing score test file), add `test_scoreboard_shows_failure_class`: build a minimal results dict with one failed case that has `"failure_class": "no_done_emitted"`, call `generate_scoreboard(data)`, assert `"no_done_emitted"` appears in the output.
- [ ] 3.2 Add `test_scoreboard_shows_dash_for_none_failure_class`: build a results dict with one succeeded case (`"failure_class": null`), assert the table contains `| - |` or similar dash rendering in the Failure class column.
- [ ] 3.3 Add `test_scoreboard_missing_failure_class_key_shows_dash`: build a results dict where the case dict has no `"failure_class"` key at all (old format), assert no exception and the dash is shown.
- [ ] 3.4 Run `uv run pytest task2/tests/test_score.py -k "failure_class"` — confirm all 3 tests fail.

## 4. Green — add CaseResult fields

- [ ] 4.1 In `task2/scripts/eval.py`, add two new fields to `CaseResult` dataclass after `cache_events`: `failure_class: str | None = None` and `failure_detail: str | None = None`.
- [ ] 4.2 Run `uv run pytest task2/tests/test_eval.py -k "failure_class or failure_fields"` — confirm the `test_case_result_*` tests now pass.
- [ ] 4.3 Run `uv run ruff check task2/scripts/eval.py` — clean.

## 5. Green — implement _classify_failure

- [ ] 5.1 In `task2/scripts/eval.py`, add the import `from agent.trace import ActEvent, DoneEvent` to the existing trace import block (if not already imported).
- [ ] 5.2 Add the `_classify_failure(events: list[AnyEvent], validators: list[dict], status: str) -> tuple[str | None, str | None]` function immediately above `_run_case`, implementing the priority order: `None` early return for non-failed statuses, then `supervisor_halt`, `locator_miss`, `tool_error`, `validator_fail`, `schema_error`, `no_done_emitted`, `other`.
- [ ] 5.3 Run `uv run pytest task2/tests/test_eval.py -k "classify_failure"` — confirm all 9 synthetic-trace tests pass.
- [ ] 5.4 Run `uv run ruff check task2/scripts/eval.py` — clean.

## 6. Green — wire _classify_failure into _run_case

- [ ] 6.1 In `_run_case`, after `_aggregate_diagnostics` is called and `events` is materialised (or re-use the materialised list), call `failure_class, failure_detail = _classify_failure(events, validator_results, run_result.status)`.
- [ ] 6.2 Pass `failure_class=failure_class` and `failure_detail=failure_detail` when constructing the returned `CaseResult`.
- [ ] 6.3 Also update the exception-path `CaseResult` (the `except Exception` branch) to set `failure_class="tool_error"` and `failure_detail=repr(exc)`.
- [ ] 6.4 Run `uv run pytest task2/tests/test_eval.py -k "_run_case or failure_class"` — confirm both the new `_run_case` tests and synthetic tests pass.
- [ ] 6.5 Run full `uv run pytest task2/tests/test_eval.py` — no regressions.

## 7. Green — scoreboard column

- [ ] 7.1 In `task2/scripts/score.py`, add `"Failure class"` to the header row string and add a corresponding `|` separator in the separator row.
- [ ] 7.2 In the per-case loop, read `fc = case.get("failure_class") or "-"` and append it as the new column value in the row string.
- [ ] 7.3 Run `uv run pytest task2/tests/test_score.py -k "failure_class"` — confirm all 3 scoreboard tests pass.
- [ ] 7.4 Run `uv run pytest task2/tests/test_score.py` — no regressions in existing scoreboard tests (the golden snapshot test, if any, must be updated to include the new column header).
- [ ] 7.5 Run `uv run ruff check task2/scripts/score.py` — clean.

## 8. Refactor and full verification

- [ ] 8.1 Run `uv run ruff format task2/` and confirm no uncommitted diff remains (or apply and re-check).
- [ ] 8.2 Run full test suite: `uv run pytest task2/` — green bar with no skips that weren't already skipped before this change.
- [ ] 8.3 Spot-check: run `uv run python scripts/eval.py` from `task2/` against fixture cases and confirm the JSON output now contains `"failure_class"` and `"failure_detail"` keys on every case entry.
- [ ] 8.4 Spot-check: run `uv run python scripts/score.py` and confirm the Markdown table has a "Failure class" column with values for failed cases and `-` for passing/skipped ones.
