# Ask-User Smoke — Remaining Issues

Round-1: `task2/benchmark/feat-task2-sessions-ask-user-http/ask_user_smoke/{A1,A3,A6,U1,U4}.json`.
Round-2 / round-3 / round-4: `…/round{2,3,4}/`.
**Round-5 (this pass):** `…/round5/{A1,A3,A6,U1,U4}.json` — first run after F9–F14 landed.

## Status of prior tickets

F9, F10, F11, F12, F13, F14 are all implemented and unit-tested
(commits `a2422aa`, `fbabff9`, `69ceaef`, `042e9bd`). Round-5 verdicts
below validate the wiring against the deployed surface and surface
the remaining (and one regressed) issue families.

## Round-5 verdicts

| case | task                              | expected ask | asked | terminal               | result quality          | t (s) |
|------|-----------------------------------|--------------|-------|------------------------|-------------------------|-------|
| A1   | Book Inparadise (旭集) Saturday   | yes          | yes   | failed (agent `fail`)  | null (clean fail)       | 408.7 |
| A3   | Cheapest TPE→NRT flight           | yes          | yes   | failed (`no_progress`) | null (premature halt)   | 140.0 |
| A6   | Best ramen Tokyo on Maps          | yes          | yes   | failed (`no_progress`) | null (locator stalled)  | 106.4 |
| U1   | 2018 Turing Award                 | no           | no    | failed (agent `fail`)  | null (locator stalled)  | 69.1  |
| U4   | "Attention Is All You Need"       | no           | no    | done                   | correct (verbatim)      | 104.8 |

### A1 — Book Inparadise (旭集) — PARTIAL
- **Thinking:** F11 worked (6-step plan, not 1). Single focused ask: `Which Inparadise (旭集) location…`. F12/F10 confirmed live: `read intent=…fallback=body` ok, then `act done outcome=halted_by_supervisor` with seq=5 then `supervisor premature_done trigger_event_seq=5` (F10 closed the seq=0 gap).
- **Action:** `goto google` → `goto inparadise.com.tw` → `click intent="網路訂位 link"` **timeout** → step-6 `click intent="the 網路訂位 link"` **timeout** → premature `done` halted → `read fallback=body` → `goto /reservation` → `goto google search` → `goto opentable` **error** → replan → `fail`. Two click-timeouts on a CJK link the agent could see in `ax_tree_digest`.
- **Answer:** null with clean reasoning. Locator landed the link but Playwright click timed out — overlay/intercept on inparadise.com.tw not handled.

### A3 — Cheapest TPE→NRT flight — FAIL
- **Thinking:** Single focused ask `What date…`. F11 worked (10-step plan). Plan is detailed: navigate, enter origin/dest, set date, click search, sort, identify cheapest.
- **Action:** `goto flights.google.com` → **step_id jumps step-1 → step-6 with zero events** → `done` halted (F10 fires) → terminal `no_progress`. Four full steps (~64 s wall time) emit nothing — the LLM was likely producing tool calls that fell into a no-emit code path (no_tool_call_repeat threshold or text-only response).
- **Answer:** null. The proposed `done` carried `cheapest_fare="NT$6,344"` from the homepage promo banner with `evaluation_previous_action="failed"` — supervisor correctly halted, F9 grounding check was empty (no `read` had happened), `no_progress` then fired prematurely.

### A6 — Best ramen Tokyo on Maps — FAIL
- **Thinking:** Single focused ask. F11-compliant plan.
- **Action:** `goto maps.google.com` → step-5 `locate intent="the search button"` **L1_ax/L2_dom/L_textmatch all miss** → step-7 `locate intent="the search textbox"` **L1_ax/L2_dom/L_textmatch all miss** → terminal `no_progress`. F13's combobox alias did not save the intent because the page's accessible name is non-English and the agent's intent name token is `search`.
- **Answer:** null. Catastrophic locator miss on a page that visibly exposes a search input — the bridge between English intent name and CJK accessible name is broken.

### U1 — 2018 Turing Award — FAIL (regression vs round-4)
- **Thinking:** 3-step plan, no ask, coherent.
- **Action:** `goto google.com` (Taiwan locale renders the search input as `[combobox] "搜尋"`) → `locate intent="the search textbox"` **L1_ax miss → L2_dom miss → L_textmatch miss** → agent emits `fail` with reason explicitly naming the issue: "ax_tree_digest shows a [combobox] '搜尋' element exists but locator pipeline keeps failing due to role token issues".
- **Answer:** null. Agent's self-diagnosis is correct: F13 added the `combobox` role alias at L1, but `get_by_role("combobox", name="search")` still misses because the live accessible name is `搜尋`. The 1-element-on-page singleton fallback never fires.

### U4 — "Attention Is All You Need" abstract — PASS
- **Thinking:** 4-step plan, no ask.
- **Action:** `goto arxiv.org` → `type intent="the Search term or terms textbox"` (works on arxiv's plain `<input>`) → `read intent…fallback=body` (F12 wiring used) → `read find="Vaswani"` ok → `goto /abs/1706.03762` → `read intent…fallback=body` → `done`.
- **Answer:** Verbatim abstract, URL + evidence both correct. Cleanest run (0 halts, 105 s). Confirms F12 path is healthy on English-name inputs.

---

## F15 — Locator name-token misses non-English accessible names

**Severity:** P1.

**Evidence:**
- U1 (`…/round5/U1.json` seq 4–7): `intent="the search textbox"` → L1_ax/L2_dom/L_textmatch all miss; agent emits `fail` citing `[combobox] "搜尋"` visible in ax_tree.
- A6 (`…/round5/A6.json` seq 5–12): same pattern on Google Maps for `search button` and `search textbox`.
- A1 not directly affected because the agent already used the CJK token (`網路訂位 link`) — but the symmetric problem (agent uses page-language token, locator misses if the page is English) is the same shape.

**Diagnosis:** `parse_intent` splits the intent into `(role, name)`; `locate_l1` then calls `page.get_by_role(role, name=name, exact=False)` which requires `name` to substring-match the *accessible name* (case-insensitive). When the page is in a different language than the intent token, the name match silently returns 0. F13 added a *role* alias (textbox→combobox) but does not address the *name* mismatch. L_textmatch matches by visible text, which is the same string as the accessible name on these sites.

**Fix:**
1. In `agent/locate.py:locate_l1`, if `(role, name)` returns 0 matches *and* the role alone (no name filter) returns exactly 1 element, use that singleton. Mark `confidence=0.7` and stamp `tier="L1_ax"` with a `name_fallback=role_singleton` flag in the LocateResult so traces remain auditable.
2. Apply the same singleton-fallback after the F13 role-alias loop: try each role with name; if none match, fall back to the union over alias roles without name and accept if the union has exactly 1 candidate.
3. Do **not** preseed any locale-specific names. The rule is page-shape: "if the agent's name token doesn't match, but the role is unambiguous on this page, use it" — this generalises to any language, not just CJK.

**TDD shape:**
- Unit fixture: a page with one `[role=combobox]` whose accessible name is `搜尋`. `locate(page, "the search textbox")` resolves to that combobox (L1_ax with name_fallback flag).
- Negative: a page with two comboboxes both unnamed; `locate(page, "the search textbox")` raises `LocatorMiss(reason="ambiguous", match_count=2)`. The singleton fallback only kicks in for unique-role pages.
- Replay: A6 round-5 trace, with a Maps fixture that mirrors the live ax-tree shape; assert `locate intent="the search button"` resolves at L1_ax, not L_textmatch miss.

**Expected impact:** unblocks U1 and A6 entirely (~2 of 5 cases in this smoke); estimated +20–25 % pass-rate on the broader ambiguous suite for non-en-US pages. No latency change on hits; small reduction on misses (skips L2/L_textmatch).

---

## F16 — Trace gap: step_id increments without any events

**Severity:** P2 (no functional impact; major debuggability impact — supersedes prior F10 once landed).

**Evidence:**
- A3 (`…/round5/A3.json`): step-1 `goto` → next event is step-6 `done`. Four LLM round-trips (~64 s wall time) emit zero `act`/`locate`/`supervisor` events.
- A6 (`…/round5/A6.json`): step-1 → step-5 (3-step gap), step-5 → step-7 (1-step gap).
- F10 closed the gap *for halted `done`* but other no-emit branches remain: text-only LLM responses, tool calls rejected at JSON-parse / arg-validate, `_consecutive_no_tool_call_steps` increments.

**Diagnosis:** `agent/loop.py` increments `step_id` once per LLM call, but the act/locate emit sites assume a tool was dispatched. When the LLM returns no tool calls or returns malformed args, the loop continues without writing to the trace. Reviewers can't tell what the agent did during the gap. F10's pattern (emit an act event for the rejected case) needs to be generalised: every step should emit *something* before moving on.

**Fix:**
1. Add a single `step_advance` event kind (or reuse `act` with a dedicated `tool="_no_tool_call"`) emitted whenever an LLM iteration completes without dispatching a tool. Include `reason ∈ {"no_tool_call", "parse_error", "arg_validate_error"}` and the raw assistant `content` truncated to 256 chars.
2. Wire it from the existing branches in `agent/loop.py` that currently `continue` silently after `_consecutive_no_tool_call_steps += 1` and after JSON-decode/validate failures on `tool_calls`.

**TDD shape:**
- Unit: a `_FakeLLMClient` that returns a text-only response with no tool calls. Loop emits exactly one trace event for that step (`step_advance` or equivalent) with non-empty `step_id` matching the LLM call.
- Unit: malformed `args` JSON in a tool call emits a `step_advance` with `reason="parse_error"` and is not silent.
- Replay: A3 round-5 trace becomes contiguous (no `step_id` gaps).

**Expected impact:** zero pass-rate change. Cuts post-mortem time by ~50 % when a run regresses — the next round of update_agent2 won't have to guess what happened in steps 2–5.

---

## F17 — Click-timeout on a located element should retry via JS-click before `done`-halt

**Severity:** P2.

**Evidence:**
- A1 (`…/round5/A1.json` step-3, step-6): `click intent="網路訂位 link"` → `outcome=timeout`, retried verbatim with `the 網路訂位 link` → `outcome=timeout` again. Locator clearly resolved (no LocatorMiss event), so the element was found but Playwright's auto-wait click timed out. Most likely cause on a marketing site: cookie/age consent banner overlay intercepting the click.
- The agent's only recourse is to give up and `done` (which then gets halted) or wander into other URLs — both wasted hops we can avoid.

**Diagnosis:** `agent/browser.py:click` calls Playwright's `locator.click(timeout=…)` which is interception-aware: if a paint-blocking overlay sits over the target, Playwright reports `timeout`. We currently surface this as a tool error and let the LLM decide. Cheap recovery: on the second timeout for the same located element in a window, try `locator.evaluate("el => el.click()")` (force JS-click) before bubbling the failure.

**Fix:**
1. In `agent/browser.py:click` (or a thin wrapper in `loop._dispatch`), when a click times out and the located fingerprint matches a previous timeout in the rolling outcome buffer, retry once via JS dispatch: `locator.evaluate("(el) => el.click()")`. Annotate the act event with `outcome="ok"` and `meta={"retry":"js_click"}`.
2. Do **not** dismiss banners — that is site-specific. JS-click bypasses interception generically.

**TDD shape:**
- Unit fixture: a page with a transparent fixed-position div covering a clickable button. First Playwright click times out; second attempt with `js_click` succeeds. Assert exactly two attempts and the trace records `meta.retry="js_click"`.
- Regression: same intent issued twice in a row with both `outcome=timeout` should fire JS-click on the second; assert `_recent_outcomes` does not gate `done` because the JS-click succeeded.

**Expected impact:** unblocks A1 (the only failure mode there is the click-timeout cascade). Estimated +1 case in the ambiguous smoke. Minimal latency hit (one extra click only on the actual failure path).

---

## F18 — `done` after a goto-only sequence with no `read` should require an intervening read

**Severity:** P2.

**Evidence:**
- A3 (`…/round5/A3.json`): `goto flights.google.com` → 4 silent steps → `done` with `result.cheapest_fare="NT$6,344"` taken from the homepage promo banner. Supervisor correctly halts as `premature_done`, F9 grounding check is empty (no `read` content), and the loop falls through to `no_progress`.
- The LLM had no opportunity to extract grounded data because no `read` ever ran. The current premature heuristics catch *some* of this (T1 `no_action_yet` at step 1) but not the goto-then-done-after-N-silent-steps shape.

**Diagnosis:** The "is the proposed answer grounded?" check (F9) is gated on `_latest_read_content`. When the agent leaps to `done` having only done a `goto`, `_latest_read_content` is empty, F9 short-circuits to "not grounded" → premature_done, but the agent has already committed and the recovery path is brittle. Better: refuse to consider any `done` premature-or-not until at least one `read` has happened in the run.

**Fix:**
1. Add a precondition in the done-handling branch of `agent/loop.py`: if no `read` event has been emitted in this run, treat the done as `premature_done` with reason `"no_read_yet — call read() to ground the answer in page content"`. This is a precondition, evaluated *before* the existing T1/F2/F7 heuristics.
2. Counter-example to keep behaviour sane: tasks like "navigate to the login page" that legitimately don't need a read should still pass — but those return `done` with empty `result.value` and current verifier already flags as low-quality. The precondition only fires when `result` carries a non-empty answer field.

**TDD shape:**
- Unit: a stub LLM that emits `goto` then `done` with non-empty result. Loop classifies as `premature_done` with reason `no_read_yet`; F10's act event still fires.
- Unit: the same trace, but with `read` between `goto` and `done`, accepts the done (preserves U4 behaviour).
- Negative: `done` with empty `result` after a goto-only sequence is *not* gated by F18 (lets the verifier handle no-answer cases).

**Expected impact:** A3 fails earlier and cleaner (no fabricated promo-banner answer). Marginal improvement in extraction-task latency by short-circuiting one wasted halt round.

---

## Lower-severity observations (track, do not file)

- **A1 `goto opentable.com.tw/r/Inparadise-天母` outcome=error** — the URL was synthesised by the LLM. Worth one log line in the goto handler when the URL 404s, distinguishable from a network error.
- **U1 plan step "Search Google" then `goto google` then immediate `fail`** — agent's self-fail reason explicitly accuses the locator pipeline. The fix is F15; the meta-issue is that the agent already understands what's wrong but can't escape. Consider exposing a `try_role_singleton` argument the LLM could request explicitly when it sees this shape.
- **A3 LLM emits `done` at step-6 with `evaluation_previous_action="failed"`** — the agent correctly self-reports failure, but proposes `done` anyway. Tighten the system prompt: "if `evaluation_previous_action='failed'`, you must call `fail` not `done`".
- **U4 succeeds with `read intent=…fallback=body` (F12 path) twice** — confirms the F12 fallback is the dominant `read` shape on real sites. No bug; worth keeping in mind that L1_ax often misses on real article pages and the fallback is doing the work.
- **`_summary.json` PASS/FAIL flag is misleading** — it only reports whether `ask_user` fired-as-expected, not result quality. Would mistake A1/A3/A6 for passes. The next runner version should fold `terminal.status` and a result-non-null check into the summary line.

## Cross-cutting note on the smoke harness

Round-5 stresses a real gap: the SSE/trace contract works, but the trace is incomplete enough that `update_agent2` had to guess what happened during step gaps. F16 closes that gap. Until F16 lands, every diagnostic pass needs to compare `step_id` deltas against event counts to know whether the trace is showing the full story.
