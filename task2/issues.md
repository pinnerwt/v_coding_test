# Open Issues — Live Agent

Round-10 evidence: `task2/benchmark/feat-task2-sessions-ask-user-http/ask_user_smoke/round10/{A1,A3,A6,U1,U4}.json`.

## Round-10 verdicts

| case | task                              | expected ask | asked | terminal           | result quality                | t (s) |
|------|-----------------------------------|--------------|-------|--------------------|-------------------------------|-------|
| A1   | Book Inparadise (旭集) Saturday   | yes          | yes   | **null** (no SSE)  | partial→halted, then leaked   | 364.7 |
| A3   | Cheapest TPE→NRT flight           | yes          | yes   | **null**           | bundled-Q + bare-task plan    | 369.4 |
| A6   | Best ramen Tokyo on Maps          | yes          | yes   | **null**           | F19 trivial-overlap miss      | 371.5 |
| U1   | 2018 Turing Award                 | no           | no    | done               | correct (Bengio/Hinton/LeCun) | 205.9 |
| U4   | "Attention Is All You Need"       | no           | no    | failed (agent fail)| null (clean fail)             | 182.1 |

### A1 — Book Inparadise — FAIL (post-halt leak)
- **Thinking:** 7-step plan correctly bakes in `天母店` and `Saturday, May 9, 2026`. F19 satisfied. Single focused ask.
- **Action:** `goto google → goto inparadise.com.tw → click 網路訂位 (nav) → click 網路訂位 menu (error) → click 網路訂位 (ok) → click → click Taipei → read → click Branch textbox (4 errors in a row, steps 12–15) → done halted_by_supervisor (F21 fired with status=partial) → click step-17 fired AFTER halt`. The dispatch loop kept advancing past the halt.
- **Answer:** terminal=null. Runner SSE stream timed out at 364 s with no final `terminal` event ever emitted, even though the loop reached a halt at step-16.

### A3 — Cheapest TPE→NRT flight — FAIL (bundled question + answer dropped)
- **Thinking:** ask_user fired but **bundled**: `What are your departure AND return dates for the Taipei to Tokyo round-trip flight?` — two slots in one question, and silently assumed round-trip when the task says "return the cheapest fare" (return = return-the-result). Initial plan after the answer is **1-step bare task verbatim**: `["Book a flight from Taipei to Tokyo and return the cheapest fare."]`. F19/F28 retries did not save it. Replan at step-14 finally produced a real 8-step plan, too late.
- **Action:** `goto flights.google.com → type Where from? (error) → type combobox ok → type Tokyo ok → 5 clicks/timeouts on origin/dest dropdown → read → click Tokyo (error×3, timeout×1) → replan → read`. Agent floundered inside the date/airport widget.
- **Answer:** terminal=null. Runner hard-timeout at 369 s.

### A6 — Best ramen Tokyo on Maps — FAIL (F19 trivial-overlap false positive)
- **Thinking:** Single focused ask, well-formed. Initial plan after the answer is again **1-step bare task**: `["Find the best ramen restaurant in Tokyo on Google Maps."]`. F19's any-token check passed because the answer `highest-rated by Google reviews, in Shinjuku` shares the token `google` with the task ("Google Maps"). The discriminating token `Shinjuku` never made it into the plan.
- **Action:** `goto maps.google.com → type "best ramen restaurant in Tokyo"` (no "Shinjuku") → `read → click Jikasei MENSHO → read → replan → read → click Menya NOBUNAGA timeout → click ok → read`. The agent never restricted to Shinjuku.
- **Answer:** terminal=null. Runner hard-timeout at 371 s. Even if it had completed, neither restaurant clicked is in Shinjuku.

### U1 — 2018 Turing Award — PASS
- **Thinking:** No ask (correct). Plan coherent.
- **Action:** `goto google → type query → read → goto Wikipedia/Turing_Award → read find=2018 → done`.
- **Answer:** Bengio/Hinton/LeCun for 2018 ✓ (factually correct). Evidence is the Wikipedia table row and supports the result.

### U4 — "Attention Is All You Need" abstract — FAIL (locator/interaction)
- **Thinking:** No ask (correct). Plan coherent (6 steps).
- **Action:** `goto arxiv.org → click "the search textbox..." (error) → click (timeout) → type (error) → type (error) → fail`. Locator surfaces a `[textbox] "Search term or terms"` element in `ax_tree_digest`; both `click` and `type` fail against it. Agent emits a clean `fail` with that exact diagnosis.
- **Answer:** null (clean fail, agent self-reported).

---

## I2 — F19 trivial-overlap: answer tokens that already appear in the task should not count

**Severity:** P1.

**Evidence:**
- A6 round-10: plan `["Find the best ramen restaurant in Tokyo on Google Maps."]` after answer `highest-rated by Google reviews, in Shinjuku`. F19 saw token `google` in the plan and skipped retry. Discriminating token `shinjuku` never made it in.
- Precision bug in `_plan_references_answer` at `agent/plan.py:146` — checks "any answer token in plan" but doesn't exclude tokens trivially carried over from the original task.

**Diagnosis:** F19's any-token rule is too lax when the answer contains words that are already in the task ("Google" here echoes "Google Maps"). The numeric/digit path (F28) is unaffected because digit tokens almost never appear in tasks; the lexical path is where the false-positive lives.

---

## I3 — Session worker doesn't emit `terminal` SSE event on supervisor halt

**Severity:** P1.

**Evidence:**
- A1 round-10: trace contains `act done outcome=halted_by_supervisor` at step-16, but the runner SSE stream never receives a `type=terminal` event. Runner times out at 364 s with `terminal=null`. Three of the five round-10 cases (A1, A3, A6) have null terminals — for A1 it is specifically because of the halt path.
- Symmetric round-9 A1 had a clean `terminal=failed` because the loop reached `tool=fail` (different code path).

**Diagnosis:** The terminal-event emit is gated on the loop returning normally with `LoopResult.status ∈ {succeeded, failed}`. When the supervisor halts mid-dispatch, the loop continues in a degraded state (see I4) and never reaches the terminal-emit code path. From the SSE consumer's perspective the run silently stalls.

---

## I4 — Loop dispatches further tool calls after `done halted_by_supervisor` (FIXED)

**Severity:** P1 (same root cause as I3).

**Evidence:**
- A1 round-10 events 16 & 17: `act done halted_by_supervisor (step-16)` is followed by `act click error (step-17)`. The loop emitted another tool call after a halt that should have been terminal.

**Diagnosis:** F10 (premature_done) and F20 (unsupported_superlative) ran *before* F21 (self-status downgrade), so when the agent's own `done` payload self-reported `status=partial`, the heuristic halt fired anyway and the LLM was given another turn — leaking a follow-up click. Fix: when `result.status` is in `_SELF_FAILURE_STATUSES ∪ _SELF_SOFT_FAILURE_STATUSES`, bypass F10 + F20 and let F21 convert the run to `failed` / `unverified` directly. Regression: `tests/agent/test_fix_md.py::test_i4_done_with_partial_status_terminates_even_after_two_failures`.

---

## I5 — Locator finds element in a11y tree but interaction repeatedly fails

**Severity:** P2.

**Evidence:**
- U4 round-10: `[textbox] "Search term or terms"` is visible in `ax_tree_digest`; `click` (×2) and `type` (×2) all fail with `outcome=error/timeout`. Agent's self-fail message names the issue verbatim.
- F25/F27 fixed single-attempt locator issues; this is the post-locator interaction stage failing repeatedly on a positively-located element.

**Diagnosis:** The locator returned a Playwright handle; `click()`/`fill()` then time out or error. F17/F25 added a JS-click fallback for click-timeout. There is no equivalent fallback for `type` failures, and the agent has no signal that it should switch strategies (e.g. focus + dispatch input event) rather than re-issue the same `type`.

---

## I6 — Planner produces 1-step bare-task plans even after F11+F19+F28 retries (deferred from round-9 F30)

**Severity:** P2.

**Evidence:**
- A3 round-10: final emitted plan is `["Book a flight from Taipei to Tokyo and return the cheapest fare."]` after the answer `December 15, 2026, one-way`. F19/F28 retries should have triggered (digit tokens missing); we have no observability into what happened on each retry attempt.
- A6 round-10: same shape — `["Find the best ramen restaurant in Tokyo on Google Maps."]` after the answer `highest-rated by Google reviews, in Shinjuku`.
- A6 round-9 also surfaced the symmetric "plan-step → tool-arg drift" issue (Shinjuku appears in plan step 2, but the actual `type` call drops it).

**Diagnosis:** Two distinct sub-cases in the same family:
1. **Retry visibility:** when F11/F19/F28 retries fire, the trace only shows the final accepted plan — we cannot tell whether the LLM kept regenerating the same 1-step plan, or whether the retry didn't fire at all.
2. **Plan→tool-arg drift:** even when a multi-step plan correctly references the answer (`Search for ramen in Shinjuku`), the per-step LLM call may compress `text` to `"ramen in Tokyo"` and silently drop the constraint.

Both manifest as "user answer goes in, never comes out at the action stage". Best tackled after I2 lands — it may resolve sub-case 1 by getting the plan right earlier.

---

## Lower-severity observations (track, do not file)

- **All three ambiguous cases hit runner hard timeout (360 s).** Loop's internal step budget did not abort earlier. I3 will partially fix A1; I2 will partially fix A6 by getting the plan right earlier. Re-measure after those land — if cases still hit 360 s, tighten the budget.
- **`_summary.json` PASS flag is misleading** — re-flagged from rounds 5/8/9. All 5 marked PASS though A1/A3/A6 had no terminal and U4 failed. Runner heuristic is `saw_ask_user == ambiguous_expected` only.

## Cross-cutting note

Round-10 is **less clean than round-9**. Newly-surfaced failures are concentrated and not regressions of prior fixes:
- F21 fired correctly on A1 (`halted_by_supervisor`) but the loop didn't stop and the SSE pipeline didn't emit terminal — I3+I4 close out F21's wiring on the partial-status path.
- F19/F28 are working on their unit-test cases but A6 surfaced a precision hole (I2) and A3 surfaced a depth hole (I6).
- F11 short-plan retry is firing in A3/A6 but the LLM is returning the same 1-step task on retry, hitting the F11 cap.

Recommended priority: **I3+I4 first** (closes F21, removes the "null terminal" diagnostic ambiguity), then **I2** (small precision tweak that unblocks A6), then **I5** (robustness add-on).
