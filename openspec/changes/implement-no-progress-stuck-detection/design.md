## Context

`agent/loop.py` already has two stuck-detection mechanisms:

1. `_stuck_buf` — rolling buffer of `_STUCK_REPEAT_K=3` canonical tool-call strings; fires when all entries are byte-identical.
2. `_consecutive_no_tool_call_steps` — counter that fires when the LLM emits `_NO_TOOL_CALL_K=3` consecutive responses with no tool calls.

Neither fires in the "thrash" pattern observed in `webvoyager-1` steps 13-20: the tool names and args vary per step (evading `_stuck_buf`) and there are tool calls every step (evading `_consecutive_no_tool_call_steps`), yet the page AX-tree is unchanged and no `click`/`type` succeeds.

The `ax_fingerprint` is already computed by `observe.build_observation()` at the **start** of each step. The post-dispatch fingerprint must be obtained cheaply; calling `build_observation()` a second time works since it only reads the live AX-tree (no LLM, no network round-trip).

## Goals / Non-Goals

**Goals:**

- Detect and bail from thrash loops where the AX-tree does not change AND no `click`/`type` succeeds for `_NO_PROGRESS_K=4` consecutive steps.
- Emit `RunResult(status="failed", reason="no_progress")` with a full step record (so cost and latency accounting are preserved).
- Extend `RunResultReason` Literal with `"no_progress"` — no free-text strings.
- Add three TDD-required test scenarios.

**Non-Goals:**

- Replace or weaken `_stuck_buf` / `_consecutive_no_tool_call_steps` — both remain unchanged.
- React to partial-page updates that don't change the AX digest (those are already progress from the loop's perspective; the fingerprint unchanged case is the signal).
- Track per-tool-call latency of the extra `build_observation` call (it goes into `dispatch_ms` with no separate accounting).

## Decisions

**Decision 1 — Parallel buffer, not replacement**

Whichever guard trips first wins. This is the simplest model and matches the existing `_stuck_buf` design. The `_no_progress_buf` fires at step 4 minimum (needs 4 filled entries); `_stuck_buf` fires at step 3 minimum. In pathological cases both could be satisfied at the same step — the code checks `_stuck_buf` first (existing order), then checks `_no_progress_buf` after the per-tool-call `_stuck_buf` check passes.

Actually: `_stuck_buf` is checked per-tool-call inside the `for tool_call in response.tool_calls` loop. `_no_progress_buf` is checked once per step after all tool calls finish. This keeps the hot path for `_stuck_buf` unchanged.

**Decision 2 — Post-dispatch fingerprint via a second `observe.build_observation()` call**

Alternative considered: cache the pre-step fingerprint from the previous iteration (i.e., use what will become step N+1's start fingerprint as step N's post-dispatch fingerprint). This avoids an extra call but requires storing state across iterations. Since #91 (observation caching) is not yet landed, the simple approach is a second `build_observation()` call at the end of the step's tool-call loop. This call is cheap (no LLM, no navigation) and goes untracked — its time folds into `dispatch_ms`.

When #91 lands, this can be replaced by reading the cached fingerprint without a separate call. The interface is unchanged.

**Decision 3 — `any_action_succeeded` is per-step, not per-tool-call**

`any_action_succeeded = True` iff at least one `click` or `type` tool call in the step returned a result that does **not** start with `"Error:"` (which is consistent with how `_prior_act_outcomes` already tracks this). A single successful `click` in a step with 3 other failing reads is enough to count the step as progress. This matches the ticket spec and the existing semantics.

**Decision 4 — Buffer check placement**

After all tool calls in a step have been dispatched (the `for tool_call in response.tool_calls` loop finishes without an early `_stuck_buf` bail), the implementation:

1. Captures `post_fp = observe.build_observation(browser, []).get("ax_fingerprint")`.
2. Appends `(post_fp, any_action_succeeded_this_step)` to `_no_progress_buf`.
3. Trims to last `_NO_PROGRESS_K` entries.
4. Checks: if `len(_no_progress_buf) == _NO_PROGRESS_K` and all fingerprints equal and all `any_action_succeeded == False` → bail.

The bail path calls `_record_step(...)` (preserving metrics) then returns `RunResult(status="failed", reason="no_progress", ...)`.

**Decision 5 — `_no_progress_buf` initialization and reset**

Initialized to `[]` at the start of `loop()`. Not reset between steps (rolling window). No reset on supervisor involvement (unlike `_stuck_buf`) — supervisor-mediated outcomes are already counted via `any_action_succeeded` (if supervisor caused a successful `click`, the step is not stuck).

## Risks / Trade-offs

- **False positive: page unchanged but task is legitimately read-only.** If the task requires reading 4+ consecutive pages that are all identical (same AX-tree digest), the guard could fire incorrectly. Mitigation: `any_action_succeeded` only counts `click`/`type`; `goto` to a new URL would change the fingerprint. The `_EMPTY_FINGERPRINT` case (no page loaded) always has the same fingerprint — but that would also mean zero `click`/`type` success, so a bail there is correct.
- **Extra `build_observation()` cost per step.** On a step-20 run this is 20 extra AX-tree reads. Each is ~5-20 ms. Acceptable overhead vs. the ~30 s per LLM call. When #91 lands the cost disappears entirely.
- **`_no_progress_buf` scope is per-step, checked after the inner tool-call loop.** Steps with multiple tool calls in one LLM response share a single buffer append. This is intentional — "a step" is the unit of observation.

## Migration Plan

1. Extend `RunResultReason` Literal (one-line change).
2. Add `_NO_PROGRESS_K` constant.
3. Add `_no_progress_buf: list[tuple[str, bool]]` init.
4. After the tool-call loop, add fingerprint capture, buf append, and bail check.
5. Run red tests first (TDD), then implement, then green.
6. `ruff check` + `ruff format` must be clean.

No migration or rollback needed — this is a purely additive change. Existing callers see no behavior change unless a run enters the thrash pattern.

## Open Questions

- **When #91 (observation caching) lands**: the post-dispatch fingerprint should read from the cache rather than calling `build_observation()` again. This design's interface supports that swap without a spec change.
