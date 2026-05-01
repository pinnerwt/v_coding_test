# Ask-User Smoke — Remaining Issues

Round-1: `task2/benchmark/feat-task2-sessions-ask-user-http/ask_user_smoke/{A1,A3,A6,U1,U4}.json`.
Round-2 / round-3 / round-4: `…/round{2,3,4}/`.
Round-5: `…/round5/{A1,A3,A6,U1,U4}.json` — first run after F9–F14 landed.
**Round-6 (this pass):** `…/round6/{A1,A3,A6,U1,U4}.json` — after the de-bench-maxx prompt cleanup and F17 click-timeout retry landed.

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

**Status:** DEFERRED (attempted, reverted).

**Severity:** P2.

**Evidence:**
- A3 (`…/round5/A3.json`): `goto flights.google.com` → 4 silent steps → `done` with `result.cheapest_fare="NT$6,344"` taken from the homepage promo banner. Supervisor correctly halts as `premature_done`, F9 grounding check is empty (no `read` content), and the loop falls through to `no_progress`.

**Diagnosis:** The structural rule "no done before any read" is too coarse for the variety of legitimate flows in the existing test suite. A first-pass implementation (TDD red→green for the three F18 cases) caused 11 unrelated regressions: many `test_loop.py` happy-paths legitimately do `goto → done` with the answer visible in the AX-tree digest (no `read` needed), and the `test_replay.py` fixtures encode specific LLM-call counts that an extra premature-halt round breaks. Even with an AX-tree grounding escape hatch, the rule still pre-empts F9's substring grounding and the LLM-judge premature path.

**Why deferred:** The desired effect (rejecting A3-style fabricated-from-promo-banner answers) is largely already covered by F9 (substring grounding) and the supervisor's existing `premature_done` classification. A3's specific failure is a *grounding* failure, not a *no-read-yet* failure — F9 caught it already; the loop just didn't recover well. A nuanced version of F18 would need to be a soft gate (LLM-judge only) or be conditioned on "the answer field is unfindable in any prior observation, AX tree included," which is closer to F9's territory than a structural precondition.

**Recommended next step:** Phrase by shape, not by case. The follow-up ticket is post-`premature_done` recovery: when the supervisor downgrades a `done` (because its result is ungrounded in any prior `read` content), the loop should be able to re-prompt the planner for a `read` step rather than fall through to `no_progress`. This is independent of which task tripped it.

---

## Lower-severity observations (track, do not file)

- **A1 `goto opentable.com.tw/r/Inparadise-天母` outcome=error** — the URL was synthesised by the LLM. Worth one log line in the goto handler when the URL 404s, distinguishable from a network error.
- **U1 plan step "Search Google" then `goto google` then immediate `fail`** — agent's self-fail reason explicitly accuses the locator pipeline. The fix is F15; the meta-issue is that the agent already understands what's wrong but can't escape. Consider exposing a `try_role_singleton` argument the LLM could request explicitly when it sees this shape.
- **`done` emitted with `evaluation_previous_action="failed"`** — the agent self-reports its last action failed but still proposes `done`. Enforce structurally in the supervisor classifier (treat the combination as `premature_done`) rather than by adding another prescriptive rule to the system prompt — keeps the prompt-cleanup direction consistent.
- **U4 succeeds with `read intent=…fallback=body` (F12 path) twice** — confirms the F12 fallback is the dominant `read` shape on real sites. No bug; worth keeping in mind that L1_ax often misses on real article pages and the fallback is doing the work.
- **`_summary.json` PASS/FAIL flag is misleading** — it only reports whether `ask_user` fired-as-expected, not result quality. Would mistake A1/A3/A6 for passes. The next runner version should fold `terminal.status` and a result-non-null check into the summary line.

## Cross-cutting note on the smoke harness

Round-5 stresses a real gap: the SSE/trace contract works, but the trace is incomplete enough that `update_agent2` had to guess what happened during step gaps. F16 closes that gap. Until F16 lands, every diagnostic pass needs to compare `step_id` deltas against event counts to know whether the trace is showing the full story.

---

## Round-6 verdicts

| case | task                              | expected ask | asked | terminal               | result quality              | t (s) |
|------|-----------------------------------|--------------|-------|------------------------|-----------------------------|-------|
| A1   | Book Inparadise (旭集) Saturday   | yes          | yes   | unverified             | grounded partial (correct)  | 532.3 |
| A3   | Cheapest TPE→NRT flight           | yes          | yes   | unverified             | wrong dates, banner-scraped | 382.8 |
| A6   | Best ramen Tokyo on Maps          | yes          | yes   | done                   | first-of-list, not compared | 206.3 |
| U1   | 2018 Turing Award                 | no           | no    | done                   | correct (verbatim)          | 252.1 |
| U4   | "Attention Is All You Need"       | no           | no    | done                   | correct (verbatim)          | 95.6  |

### A1 — Book Inparadise (旭集) — PARTIAL (improved vs. round-5)
- **Thinking:** Single focused ask, 7-step plan with the Tianmu answer baked into step 2 ("filter/select the Tianmu (天母店) location").
- **Action:** `goto opentable` (error) → google search → `goto inparadise.com.tw` → `click intent="網路訂位 link"` succeeds via **`diff.retry="js_click"`** — F17 confirmed firing in production. Read booking page → replan → click reservation link → final read → `done` with grounded partial.
- **Answer:** Status=`partial` with factually correct content: "only Taipei Breeze and Xinzhuang locations are visible … Tianmu may require phone reservation." Evidence text snippet matches result. No bench-maxxing concern here — this is honest reporting of a page where the requested slot isn't available.
- **Trace gap:** seq 9 → seq 10 has a 3-minute silence (steps 7–10 emit nothing). F16 still relevant.

### A3 — Cheapest TPE→NRT flight — FAIL (new failure shape)
- **Thinking:** Single focused ask. **But:** the answer-weaving is broken — `plan (initial)` after the answer arrives is a degenerate 1-step plan: `["Book a flight from Taipei to Tokyo and return the cheapest fare."]`. F11's `_MIN_PLAN_STEPS` retry runs once, second response was likewise short, loop accepted. The user's "December 15, 2026, one-way" answer is nowhere in the plan; the planner never saw it materialise into steps.
- **Action:** `goto flights.google.com` → `read` form → locator misses `"the Find flights from Taipei City to Tokyo button"` at all 3 tiers → `unsupported_done` replan → 8-step plan listing form fields → next iteration also classifies `unsupported_done` → loop emits `done` anyway with status=`unverified`.
- **Answer:** `cheapest_fare="NT$6,356"` and `dates="May 2 — May 8"` lifted verbatim from the homepage promo banner snippet. Dates are wrong (user said Dec 15 2026 one-way). Evidence snippet shows `"from NT$6,356"` — `from` is a price floor, not an actual fare for the user's route/date. This is exactly the F18-deferred shape: ungrounded numeric answer scraped from a marketing surface.

### A6 — Best ramen Tokyo on Maps — PASS-with-caveat (silent failure mode)
- **Thinking:** Single focused ask, 5-step plan that explicitly includes "Apply filter or sort by rating to show highest-rated first" as step 3.
- **Action:** `goto maps.google.com` → `type "ramen restaurants in Shinjuku, Tokyo" submit=true` → step 3 ("sort by rating") **skipped** — agent immediately `click intent="the HALAL WAGYU RAMEN SHINJUKU-TEI Tokyo Shinjuku link"` (the first organic result in Maps' default ranking, *not* a rating-sorted list) → `read` details → `done`.
- **Answer:** Result is grounded in *this single restaurant's* page (rating 4.8 confirmed there), but the `done` payload's `evaluation_reason` claims it is the "highest rating … among all ramen restaurants in the search results" — a claim the agent never verified by reading the list. Maps' default sort is relevance, not rating; the actual highest-rated ramen in Shinjuku may be a different shop. This is a silent superlative-comparison failure: looks like a `done`, plumbs through as terminal=`done`, but the comparison the task implied was never performed.

### U1 — 2018 Turing Award — PASS (regression resolved)
- **Thinking:** 3-step plan, no ask, coherent.
- **Action:** `goto google.com` → `type intent="the search textbox"` succeeds (round-5 failed here — F13/F15 wiring on google.com is now healthy) → wandering reads through Wikipedia Turing_Award and ACM amturing → `goto en.wikipedia.org/wiki/Yoshua_Bengio` → `read` Awards section → `done`.
- **Answer:** All three names (Bengio, Hinton, LeCun) plus the "for foundational work on deep learning" citation, evidence text snippet verbatim from Bengio's page. Factually correct against world knowledge.

### U4 — "Attention Is All You Need" — PASS (unchanged)
- **Thinking:** 4-step plan, no ask.
- **Action:** `goto arxiv.org` → `type` search → `read` results → `goto /abs/1706.03762` → `read` body → `done`.
- **Answer:** Verbatim abstract, URL grounded. Cleanest run of the suite.

---

## F19 — User-supplied `ask_user` answer is not woven into the resulting initial plan

**Severity:** P1.

**Evidence:**
- A3 (`…/round6/A3.json` seq 3): after the user answers `"December 15, 2026, one-way"`, the very next `plan` event with `reason="initial"` carries `steps=["Book a flight from Taipei to Tokyo and return the cheapest fare."]` — a single-step plan that is verbatim the original task. Neither the date nor the one-way constraint appears anywhere in the plan, and the run never enters those values into the form.
- A1, A6 (same round) do not exhibit this — there the planner did weave the answer in (Tianmu, Shinjuku) and the resulting step list referenced the slot.
- F11 protects against degenerate 1-step plans by retrying once; the retry can return another short or answer-less plan and still be accepted.

**Diagnosis:** `agent/plan.py:plan()` builds the planner's user prompt with `Task: {task}\n\nCurrent state: {observation}` and routes the answer through the `ask_user` tool message. After the tool message returns, the LLM's next response becomes the final plan. Whether the answer survives into `Plan.steps` depends entirely on the LLM choosing to incorporate it — there is no run-state check that the produced plan actually mentions the answer text. When the LLM produces a degenerate plan (or one that ignores the answer), the loop proceeds, and downstream steps execute against a plan that has lost the user-supplied constraint.

**Fix:**
1. After parsing the final plan, if any `ask_user` answer was received during this `plan()` call, run a generic substring containment check: does at least one of `Plan.steps + [Plan.expected_end_state]` contain a non-stopword token from the answer text? If not, retry the planner with one extra system note: "The user's answer must be incorporated into the plan; the plan you just produced does not reference it."
2. The check is structural, not topical — split the answer on whitespace, drop a tiny stopword set (`a/an/the/of/in/on/and/or/for/to/at/by`), and require ≥1 surviving token to appear (case-insensitive substring) somewhere in the joined plan text. No domain keywords, no case-shape gating.
3. Cap the retry at one attempt (mirror F11's pattern); accept whatever comes back the second time to avoid loops. The loop also retains its existing replan budget downstream.

**TDD shape:**
- Unit: `_FakeLLMClient` returns (a) a tool call to `ask_user`, (b) a 1-step plan that does not mention the canned answer, (c) a multi-step plan that does. Assert `plan()` retries once after (b) and accepts (c). The fake records 3 LLM calls.
- Unit: `_FakeLLMClient` whose first non-tool response already mentions the answer — assert no retry, exactly 2 LLM calls.
- Unit: stopword-only answer ("the one") — degrade gracefully to "no enforceable token" and accept the first plan to avoid pathological retries.

**Expected impact:** unblocks A3-shape failures wherever the planner drops a user constraint. Generalises to any task that uses `ask_user`. Roughly +1 case in the ambiguous smoke; downstream value depends on how often the planner silently drops answers (the round-6 hit rate is 1/3 of asked cases). Adds at most one extra planning call per ambiguous run. Not a prompt rule — purely structural.

---

## F20 — `done` whose result references a single candidate while prior `read` content listed many

**Severity:** P2.

**Evidence:**
- A6 (`…/round6/A6.json`): `read` at seq 10 returns the Maps results page (a list of multiple ramen restaurants with ratings); agent then clicks one entry without comparing, calls `done` with a result that names that single restaurant, and the supervisor accepts. The plan's own step 3 ("Apply filter or sort by rating") was skipped between search and click. Terminal status = `done`.
- A3 (same round) shares part of the shape — `read` returned a flight search form (multi-candidate results not yet visible), agent calls `done` from a banner. Different surface, same root: `done` is committed to a specific value while the comparison context that would justify it has not been observed.

**Diagnosis:** The supervisor's existing `unsupported_done` classifier checks for grounding (F9 substring match between result fields and observations). It does **not** check for *coverage*: did the agent observe the alternatives that a comparison superlative implies? When the task uses a comparison adjective (best/cheapest/highest/most/largest, etc.) and the prior `read` content contained ≥2 candidate-shaped entries with the same numeric or rank field, but the `done` result references only one of them and never read further, the agent is committing on a list it never traversed.

**Fix:**
1. In `agent/supervisor.py`, add a `unsupported_superlative` classification:
   - Trigger: task text contains a comparison superlative token (small fixed list: best/cheapest/most/highest/lowest/largest/smallest/top/nearest/fastest — *language-shape*, not domain-shape). AND the most recent `read` observation's text contained ≥2 candidates that share a regex-extractable numeric field (rating like `4\.\d`, price like `\$\d`/`NT\$\d`, count like `\d+\s*reviews`). AND `done.result` references exactly one of those candidates by name.
   - Policy: `replan` with the failure reason: "Task asks for the {superlative} of a list; you observed N candidates but only inspected one. Read the list and compare before committing."
2. Place this check after F9's grounding test, before the success-emit branch.
3. **Why this is page-shape, not benchmax:** the trigger is a generic detector — "list-shape page + numeric field + comparison superlative + single-candidate done" — not a per-domain recipe. It says nothing about Maps, Flights, restaurants, or any specific surface. Any future task with the same page shape (e.g. "the lowest-priced laptop on this listing page") would trip the same classification. No prompt addition; the prompt direction stays cleanup-oriented.

**TDD shape:**
- Unit: a `_FakeBrowser` whose last `read` returns a synthetic list of 4 entries each with a `4.\d` rating; `done` with a single restaurant name; task containing "best". Assert supervisor classifies `unsupported_superlative` and triggers replan once.
- Unit: same setup but `read` returned a single candidate page (no list). Assert no `unsupported_superlative` classification — the comparison-context guard prevents over-firing.
- Unit: same task but no superlative token in the task text. Assert no classification — prevents false-positives on plain "find X" tasks.
- Replay: A6 round-6 trace; assert it now emits an `unsupported_superlative` supervisor event after the first `done` and goes to replan instead of straight to terminal.

**Expected impact:** catches a class of silent failures that pass through as `terminal=done` today. On the smoke set, A6 flips from PASS-with-caveat to a more honest replan. On a broader generalised eval, this is the difference between "first plausible answer" and "answer with comparison evidence" — likely small numeric impact on pass-rate (these silent passes were counted as passes), but a real correctness improvement that holds up under inspection.

---

## Lower-severity round-6 observations (track, do not file)

- **Supervisor `unsupported_done` classification leaks through as `terminal.status="unverified"`.** A3 round-6 has the supervisor classify `unsupported_done` twice (seq 10 and seq 12), but the second classification is followed by `done` emission with `status=unverified` — no third replan. The user-visible status `unverified` is misleading: the supervisor explicitly judged it unsupported, not merely unverified. Smallest fix: when `terminal.status` is set after the replan budget is exhausted on `unsupported_done`, carry `terminal.reason="unsupported_done_budget_exhausted"` (or similar) so the deployed surface tells the user what actually happened. No prompt change needed.
- **`read` calls with empty `args={}`.** U1 has three `read {}` calls in a row. The agent is asking for "everything on this page" with no intent or fallback. This produces large observations and burns tokens. Worth a prompt-independent guard: if two consecutive `read` calls have empty args and the URL hasn't changed, the second is a no-op — surface as `act outcome="redundant"` and skip.
- **`plan (started)` placeholder is still emitted as the first plan event with `steps=["Planning..."]`.** This is a UI-only stub; harmless, but it makes auto-counting of plan steps in scripts brittle. Filter it out at the trace-writer or document the convention.

## Round-6 cross-cutting note

The de-bench-maxx pass on the system prompts (commit `104e152`) was healthy: U1 went from regression to PASS with no case-specific scaffolding, A6 reached `done` from a Shinjuku-specific page without the prompt naming Maps or restaurants, and U4 stayed clean. The remaining failures (A3 answer-drop, A6 single-candidate superlative) are both structural — not prompt-shaped — which is exactly the direction the cleanup pointed. F19 and F20 keep us on that direction: every fix lives in `plan.py` / `supervisor.py`, not in the system prompt.

---

## Round-8 verdicts

Round-8 is the first run after the truncated-ladder removal landed (loop and `agent/locate.py` now share one ladder; L3_rerank and L4_vision are reachable from the served agent). Traces: `task2/benchmark/feat-task2-sessions-ask-user-http/ask_user_smoke/round8/{A1,A3,A6,U1,U4}.json`.

| case | task                              | expected ask | asked | terminal               | result quality                | t (s) |
|------|-----------------------------------|--------------|-------|------------------------|-------------------------------|-------|
| A1   | Book Inparadise (旭集) Saturday   | yes          | yes   | done                   | partial (silent mismatch)     | 291.1 |
| A3   | Cheapest TPE→NRT flight           | yes          | yes   | none (harness 360 s)   | n/a (no terminal)             | 372.1 |
| A6   | Best ramen Tokyo on Maps          | yes          | yes   | none (harness 360 s)   | n/a (no terminal)             | 362.9 |
| U1   | 2018 Turing Award                 | no           | no    | none (harness 360 s)   | n/a (no terminal)             | 374.6 |
| U4   | "Attention Is All You Need"       | no           | no    | done                   | correct (verbatim)            | 174.1 |

`_summary.json` shows `PASS` for all five — that flag only checks `ask_user fired-as-expected`, not result quality. The actual qualitative count is **1 PASS / 1 PARTIAL / 3 timeouts**.

### A1 — Book Inparadise (旭集) — PARTIAL (silent done/partial mismatch)
- **Thinking:** Single focused ask `Which city or location…`. Plan after answer is 6 steps including search → date/time → confirm.
- **Action:** `goto opentable.com` (error) → `goto resy.com` ok → `read` → `type "Inparadise 旭集"` → `click "Location Hong Kong"` → `type "Taipei"` → `read` (4 wasted hops on a US-only platform that returned no results — agent never read the empty-results state) → `goto inparadise.com.tw` → `click "網路訂位 link"` (succeeded via `diff.retry="js_click"` — F17 firing in production) → close announcements popup → re-read nav → `done`. 25 events, 291 s.
- **Answer:** `terminal.status="done"` while `result.status="partial"` and message reads *"unable to complete booking … Could not locate the specific Tianmu branch or access the reservation interface."* Evidence is a verbatim CJK menu snippet — grounded. The agent self-reports failure cleanly; the loop ignores it and emits `done`.

### A3 — Cheapest TPE→NRT flight — FAIL (no terminal in 360 s)
- **Thinking:** Single focused ask. **F19 worked** — plan after answer is 10 steps and explicitly names "Set departure date to December 15, 2026" and "Set trip type to one-way". Answer-weaving fix from round-6 confirmed in production.
- **Action:** `goto google.com/flights` → click "Where from?" → `locate "Taiwan Taoyuan International Airport (TPE) listitem"` **misses at L1_ax/L2_dom/L_textmatch/L4_vision** (full ladder, 4 tiers — confirms truncated-ladder removal landed) → second attempt under same intent: same 4-tier miss → recovers with shorter intent `"the Taiwan Taoyuan International Airport button"` which hits at L_textmatch → fills "Where to?" with "Tokyo" → `locate "the Tokyo button"` ambiguous at L1_ax → L3_rerank picks `nth=0` → `click "the Tokyo button"` **35 s timeout** → harness 360 s wall budget exhausted, no terminal.
- **Answer:** No terminal event. Two structural costs: (1) `L4_vision` returns miss on a visibly-rendered Maps autocomplete listitem — capture or vision prompt is failing on that surface; (2) the new L3_rerank tier on `"Tokyo button"` resolved to `role=button >> nth=0` (ambiguous → first match), which Playwright then click-timed-out on for 35 s. F17's js-click retry only fires on the *second* timeout for the same fingerprint, so a single 35 s timeout silently consumed budget.

### A6 — Best ramen Tokyo on Maps — FAIL (stale prompt, no terminal in 360 s)
- **Thinking:** Single focused ask, 5-step plan with "Apply filter or sort by rating" as step 3.
- **Action:** `goto maps.google.com` (Maps redirected to Taiwan locale, page in CJK with `[combobox] "搜尋 Google 地圖"`) → 100 s of silent steps (step_id 1 → 6 with no events, F16 still relevant) → emits `done` with `result.status="incomplete"` and `evaluation_reason="All attempts to type into the search bar failed due to unsupported role token 'combobox' - only button/checkbox/heading/link/list/listitem/textbox are supported"` → supervisor halts as `premature_done` → replan → `locate "the search button"` 4-tier miss → next step's intent collapses to `"the button"` → L3_rerank obeys with `role=button >> nth=0` → `click` ok on whatever button was first → harness 360 s budget exhausted.
- **Answer:** No terminal. Two structural bugs surfaced: (1) the agent's prompt-internal whitelist of role tokens excludes `combobox` even though F13 added combobox as a textbox alias inside the locator. The agent self-disqualifies a legitimate input; (2) when the locator ladder reaches L3_rerank with a too-vague intent (e.g. `"the button"`), it picks `nth=0` rather than treating the request as ambiguous-to-the-rerank-also and refusing.

### U1 — 2018 Turing Award — FAIL (read-find error masks usable observation)
- **Thinking:** No ask, 4-step plan, coherent.
- **Action:** `goto google.com/search?q=...` → `goto en.wikipedia.org/wiki/Turing_Award` → `read find="2018"` **outcome=error** (the page text contains "2018 — Yoshua Bengio, Geoffrey Hinton, Yann LeCun" verbatim) → `read intent=…fallback=body` ok (long observation, agent did not extract) → `read find="Recipients"` ok → `click "Recipients heading"` ok → `read` table → `goto amturing.acm.org` → `goto en.wikipedia.org/wiki/List_of_Turing_Award_recipients` → `read` ok → `read find="2018"` **outcome=error** again → `click "List of Turing Award recipients link"` (already on that page!) → `read` → `goto duckduckgo.com/?q=...` → `read`. Run timed out at 374 s with no `done`.
- **Answer:** No terminal. Agent had the answer in two separate `read fallback=body` observations and never converted them into `done`. Two coupled bugs: (1) `read find=<substring>` returns `outcome=error` even when the substring is present on page (the find-mode read either does a strict-match that fails on whitespace/encoding, or its `error` outcome is overloaded with "no match" — agent treats it as "page unreachable" and re-routes); (2) once the agent gets a useful `read fallback=body` observation, it does not synthesize `done` from it — the wandering goto loop keeps replanning because no signal says "you have enough."

### U4 — "Attention Is All You Need" — PASS (clean)
- **Thinking:** No ask, 6-step plan.
- **Action:** `goto arxiv.org` → `type "Attention Is All You Need" submit=true` (F12/F13 path on arxiv's clean role=textbox) → `read` results → `goto /abs/1706.03762` → `read` body → `done` after 174 s.
- **Answer:** Verbatim abstract; URL and evidence both grounded. Cleanest run; no halts, no replans, no locator misses.

---

## F21 — Honor agent's self-reported `result.status` when emitting terminal status

**Severity:** P1.

**Evidence:**
- A1 (`…/round8/A1.json` seq 22 → terminal): `done` payload has `result.status="partial"` and message "unable to complete booking … Could not access the reservation interface." Terminal event is emitted with `status="done"`. The user-visible status disagrees with the agent's own assessment.
- Same shape was named in update_agent2's failure-mode table months ago ("done with self-failed result"); the trace shows it is still live in production.

**Diagnosis:** `agent/loop.py`'s `_handle_done` (or wherever the `done` tool call is converted to a terminal event) reads only the tool-call's outcome, not the structured `result.status` the agent fills in. When the agent self-reports `partial`, `incomplete`, `unable_to_complete`, `failed`, or `blocked`, the terminal event should reflect that — not paper over it as `done`. This is a generic envelope rule, not a domain rule.

**Fix:**
1. In `agent/loop.py:_handle_done` (or the equivalent terminal-emit path), inspect `result.get("status")` if `result` is a dict. If it ∈ {`partial`, `incomplete`, `unable_to_complete`, `failed`, `blocked`} (case-insensitive, exact match — keep the set tight to avoid over-firing), set `terminal.status` to a downgraded value (`"unverified"` if a status field is already in use, else `"partial"`) and copy the agent's status into `terminal.reason`.
2. If `result` is a flat string (no status field), keep current behavior.
3. The set of downgrade tokens is finite and lexical, not domain-specific — it is the language any reasonable agent would use to self-report failure. No prompt change.

**TDD shape:**
- Unit: `_FakeLLMClient` returns a `done` tool call with `result={"status":"partial","message":"…"}`. Assert `terminal.status="partial"` (or `"unverified"`) and `terminal.reason` contains "partial".
- Unit: `done` with `result={"answer":"42"}` (no status field). Assert `terminal.status="done"` (current behavior preserved).
- Replay: A1 round-8 trace; assert terminal.status flips from `done` to `partial`/`unverified` after re-running the loop on the recorded events.

**Expected impact:** Closes the most-cited silent-false-positive class. Pure surface change — A1's run becomes accurately labeled rather than "passing" the deployed-surface inspection. No latency, no token impact.

---

## F22 — Locator role-whitelist in prompt is stale relative to the runtime alias table

**Severity:** P1.

**Evidence:**
- A6 (`…/round8/A6.json` seq 5): agent emits `done` with `evaluation_reason="…unsupported role token 'combobox' - only button/checkbox/heading/link/list/listitem/textbox are supported"`. Combobox IS supported at runtime — F13 added it as a textbox alias. The prompt and the locator disagree, the agent trusts the prompt, and a 100-second self-disqualification ensues.
- Generalises to: any future role alias added to the locator (treerole, switch, tabpanel, etc.) will reach the same dead end unless the prompt is regenerated alongside.

**Diagnosis:** The system prompt's enumerated list of supported roles (or the few-shot examples that mention them) is hand-maintained, not derived from the same source as `parse_intent` / `agent/locate.py`'s alias table. When the runtime adds a role-name alias, the prompt does not learn about it.

**Fix:**
1. Move the canonical role-token list to a single Python constant (e.g. `agent/locate.py:SUPPORTED_INTENT_ROLES = (...)`), inclusive of all aliases.
2. The system-prompt builder reads that constant and renders it into the prompt at startup. No more hand-edits to the prompt's role list.
3. Re-emit the prompt template via the existing prompt-build pipeline so the ZH/EN copies stay in sync.

**TDD shape:**
- Unit: `agent/prompts.py` (or wherever the system prompt is composed) reads `SUPPORTED_INTENT_ROLES` and embeds each token in the rendered prompt. Test asserts `combobox` appears in the rendered prompt.
- Unit: adding a new alias to `SUPPORTED_INTENT_ROLES` changes the rendered prompt without code edits to the prompt module.
- Replay: A6 round-8 trace; with the patched prompt the agent does not emit the "unsupported role token" reasoning and proceeds to the typing step.

**Expected impact:** Unblocks the entire class of "agent self-fails on a role the locator already supports." Specifically, A6's first 100 s of dead time disappears and the run reaches the search input. No prompt cleanup direction violated — it is a single auto-rendered list, not a prescriptive recipe.

---

## F23 — `read find=<substring>` only searches the first 2000 chars of the page

**Severity:** P1.

**Evidence:**
- U1 (`…/round8/U1.json` seq 5 ms=7, seq 14 ms=4): `read find="2018"` returns `outcome=error` on Wikipedia's `Turing_Award` and `List_of_Turing_Award_recipients`. Both pages contain "2018" verbatim in the recipients table, located ~10 KB below the page top. The 4–7 ms tool latency confirms this is a deterministic Python path, not an LLM call — the substring genuinely is not seen.
- Agent treats the `error` outcome as "this page is unusable" and re-routes through ACM and DuckDuckGo, never converting the answer (which it had in `read fallback=body` observations) into `done`.

**Diagnosis (root cause confirmed in code):** `agent/loop.py:45` defines `_BODY_TEXT_LIMIT = 2000`. `_body_text()` at `agent/loop.py:881` does `page.evaluate("() => document.body.innerText")[:_BODY_TEXT_LIMIT]` — it truncates the page text to 2 KB **before** the find search runs. The `read find` branch (`agent/loop.py:1195–1203`) calls `_window_around(_body_text(page), query)`, so the window is selected from a pre-truncated string. Wikipedia's Turing_Award lead paragraph + infobox alone exceed 2 KB; the year-keyed recipients table starts past the cutoff and is invisible to `find`. Same root cause also produces `outcome=error` whenever the LLM does the right thing (use `find` as a deterministic substring scan over a long page) — which is exactly the affordance the prompt advertises.

**Fix:**
1. Split the two `read` modes around the truncation. For `read intent=...`, keep the 2 KB cap (the LLM-extraction path can't afford a larger prompt). For `read find=<substr>`, search the **full** `document.body.innerText` (no upfront slice), then return a 2 KB window centered on the first match. Truncation moves to *after* the substring is located, not before. Concrete edits land in `agent/loop.py:_body_text` (parameterise `limit`, default 2000) and `_window_around` (compute `idx` against full text, then slice the window).
2. Distinguish outcomes: match found → `outcome="ok"` + window; substring genuinely absent in the full text → `outcome="ok"` with body `"no match for <query>"` and `match_count=0` (not `error`); true page failure (page closed, evaluate threw) → `outcome="error"`. The agent learns to read "ok with 0 matches" as "look elsewhere on this page," distinct from "page is broken."
3. While here: include `total_chars` and `match_count` in the find result so the agent can tell "found in a long ordered list" vs "found in a short page" without a second call (this is what the user proposed when triaging — verify it really is a long list before committing).

**TDD shape:**
- Unit: stub `Page.evaluate` returns a 50 KB innerText with "2018" at offset ~12 000. `read(find="2018")` returns `outcome="ok"` with a 2 KB window centered on offset 12 000 and `match_count=1`. Fails today (truncation discards offset > 2000).
- Unit: stub returns 50 KB innerText that does not contain "absent". `read(find="absent")` returns `outcome="ok"`, `match_count=0`, body says `"no match for 'absent'"`. Fails today (returns `error`).
- Unit: `Page.evaluate` raises. `read(find="x")` returns `outcome="error"`. Preserves existing semantics for real page failures.

**Expected impact:** Unblocks U1-shape failures (long pages where the answer is past the first 2 KB). Estimated +1 case in unambiguous smoke. Removes the perverse incentive for the agent to keep navigating when `read find` was supposed to be the cheap deterministic shortcut.

---

## F24 — L3_rerank should refuse when the intent text is too generic

**Severity:** P2.

**Evidence:**
- A6 (`…/round8/A6.json` seq 12–15): L1_ax `ambiguous` on `intent="the button"` → L3_rerank returns `chosen={"role":"button","selector":"role=button >> nth=0"}` → agent clicks an arbitrary first button. The intent text has no name token at all; L3_rerank picked the first candidate by ranking, which is functionally a coin flip.
- A3 (`…/round8/A3.json` seq 28–31): similar shape with `"the Tokyo button"` resolving to `nth=0` of multiple Tokyo airport candidates, then click-timing-out.

**Diagnosis:** `agent/locate.py:locate_l3` accepts the intent verbatim and lets the LLM rerank candidates. When the intent is "the button" / "the link" / "the textbox" with no distinguishing name, the LLM has nothing to rank against and a uniform-prior pick masquerades as a confident choice. The locator should detect this shape and treat it as `ambiguous` upstream of L3 — letting the supervisor either ask the agent for a more specific intent or give up.

**Fix:**
1. In `agent/locate.py:_resolve_via_ladder` (the ambiguous branch), before calling `locate_l3`, parse the intent: if `parse_intent(intent).name` is empty *or* is a stopword/pronoun (`the`, `a`, `that`), raise `LocatorMiss(reason="ambiguous", match_count=N, hint="intent_lacks_specificity")` instead of escalating to L3.
2. Surface the `hint` in the supervisor event so the loop can replan with a structured complaint: "your last `click intent` was too generic; restate with a name attribute."
3. Keep the page-shape framing: this is "intent is too generic," not "task is X type." Applies to any future task where the LLM emits a degenerate intent.

**TDD shape:**
- Unit: `_FakeBrowser` page with 5 `role=button`s; `locate(page, "the button")` raises `LocatorMiss(reason="ambiguous", hint="intent_lacks_specificity")` without invoking the L3 rerank LLM call.
- Unit: same page; `locate(page, "the Save changes button")` proceeds through L3_rerank as today (parse_intent has a name).
- Replay: A6 round-8 trace; assert L3_rerank is *not* called for `intent="the button"` and the supervisor gets a structured reason to replan.

**Expected impact:** Cuts wasted-click hops on degenerate-intent runs. On the smoke set, A6's flailing post-replan stops earlier. Saves the L3-rerank LLM round-trip cost (~10–20 s on Qwen3.5-27B) when the intent is a coin flip anyway.

---

## F25 — Click timeout on a single-candidate L3 hit should JS-click on the first attempt, not the second

**Severity:** P2.

**Evidence:**
- A3 (`…/round8/A3.json` seq 31): `click "the Tokyo button"` outcome=`timeout` after 35 002 ms. F17's two-strikes rule means the JS-click retry doesn't fire until the *next* identical-fingerprint timeout. Run hit harness 360 s budget before that next attempt.
- The element behind the timeout is an autocomplete dropdown item — a class of UI that frequently has interception layers (the dropdown's own click handler vs the underlying input). JS-click bypasses interception generically.

**Diagnosis:** F17's "retry once after the second identical timeout" was tuned to avoid retry-storms but doesn't budget for the case where the first 35 s timeout consumes most of the wall budget. For elements that resolved via L3_rerank or L_textmatch (i.e. tiers that already imply the agent is past the easy path), retrying immediately on the first timeout is justifiable.

**Fix:**
1. In `agent/browser.py:click` (or `loop._dispatch`'s click branch): when the located fingerprint came from `tier ∈ {L3_rerank, L_textmatch, L4_vision}` AND the click times out, retry with `locator.evaluate("(el) => el.click()")` immediately. Annotate trace with `meta={"retry":"js_click", "tier":"<source>"}`.
2. For L1_ax / L2_dom hits (where the element is canonically named), keep the existing two-strikes rule — these are the cases where a real interception bug would loop pathologically, and the cost of waiting one more attempt is acceptable.
3. Lower the click timeout on these "deep-tier" attempts (e.g. 15 s instead of 30 s default) so the retry happens inside the wall budget regardless.

**TDD shape:**
- Unit: page where a button is intercepted by a transparent overlay, located via L_textmatch. First click times out at 15 s, JS-click immediately follows and succeeds. Trace shows `meta.retry="js_click"`, `meta.tier="L_textmatch"`.
- Unit: same intercepted button but located via L1_ax. First click times out, no immediate retry — second timeout triggers the existing F17 path. Preserves the conservative path for canonical tiers.
- Replay: A3 round-8 trace; assert the seq-31 timeout is followed by an immediate JS-click attempt rather than a 35 s wait + budget exhaustion.

**Expected impact:** Reduces wall time on dropdown-item clicks by ~20 s per occurrence. On the smoke set, A3 likely reaches a terminal within budget. Generalises to any autocomplete UI without naming one.

---

## F26 — `done` after sufficient `read fallback=body` observations should be triggered structurally

**Severity:** P2.

**Evidence:**
- U1 (`…/round8/U1.json` seq 6, 10, 13, 17, 19): five separate `read intent=…fallback=body` observations on Wikipedia recipients table content (which contains the answer). Agent never emits `done`. Run times out at 374 s. The information was acquired multiple times; the planner kept replanning rather than concluding.
- A1 round-8 (seq 18, 21): same shape — multiple `read fallback=body` returns from the booking site, then `done` came eventually but with `partial` (this is at least correctly reported, but the trigger to *try* `done` was the agent's own decision, not a structural cue).

**Diagnosis:** The loop's continue/done decision is delegated entirely to the LLM. When the agent gets stuck in a "have I read enough?" reflexive loop, there is no structural pressure to commit. F9 is the inverse rule (block ungrounded `done`); the missing complement is a "you have read N times, the latest observation overlaps the task's expected-answer keywords, propose `done`" hint. *Crucially this is not the same as info-sufficiency for ambiguity (which gates `ask_user`)* — this is a continue-vs-conclude signal, downstream of plan execution.

**Fix:**
1. Introduce a `should_propose_done` heuristic in `agent/loop.py` (or a small classifier in `agent/supervisor.py`): if ≥3 `read` calls have occurred on the same URL host AND the most recent observation contains ≥1 token from the task text (after stopword removal, generic), inject a system note into the next planner prompt: "You have observed sufficient content from `<host>`. Propose `done` if the answer is present, else navigate elsewhere."
2. Keep the rule prompt-injection-only; do not auto-emit `done` from the loop. The LLM still decides.
3. The trigger is structural (read count + host + token overlap), not domain. Any task where the agent re-reads the same page exhibits the same shape.

**TDD shape:**
- Unit: replay a synthetic trace where `read fallback=body` is called 4× on `en.wikipedia.org/wiki/X` and the observation contains "Bengio". The next planner call's system prompt contains the "propose done" injection.
- Unit: same trace but only 2 reads on the same host — no injection (under threshold).
- Unit: 4 reads but observations contain none of the task tokens — no injection (relevance gate).

**Expected impact:** Unblocks U1-shape "had the answer, kept reading" failures. Estimated +1 case in unambiguous smoke. No prompt cleanup violated — the injection is structural and conditional on observed-state, not on task category.

---

## F27 — L4_vision reports miss on visibly-rendered elements

**Severity:** P2.

**Evidence:**
- A3 (`…/round8/A3.json` seq 11, seq 18): `locate "the Taiwan Taoyuan International Airport (TPE) listitem"` reaches L4_vision and returns `outcome="miss"` both times. The autocomplete dropdown was visible on screen (the agent had typed "Taipei" and Google Flights' dropdown was open).
- A6 (`…/round8/A6.json` seq 11): `locate "the search button"` L4_vision miss on Maps' search bar.

**Diagnosis:** Either (a) the screenshot capture in `agent/locate.py:locate_l4` is grabbing a stale frame, or (b) the vision-LLM prompt + Qwen3.5-27B's vision capability is not strong enough to consistently localize from a screenshot. If (a), the fix is in capture timing (`page.wait_for_load_state("networkidle")` before screenshot, or trigger a re-paint via `page.evaluate("document.body.offsetHeight")`). If (b), L4_vision becomes a cost without a benefit and the policy should de-prioritize it.

**Fix:**
1. Instrument L4_vision to dump the screenshot and the LLM's raw response to `task2/.smoke/vision_misses/<run_id>_<seq>.{png,json}` whenever it returns miss. One round of hand-inspection determines whether the screenshot was wrong (capture bug) or the LLM was wrong (model capacity bug).
2. If capture bug: add `await page.wait_for_load_state("domcontentloaded")` then a 200 ms throttle before `page.screenshot()`, since autocomplete dropdowns paint async after `networkidle`.
3. If model bug: lower L4_vision's role in the ladder — only invoke it when the prior tier was `L3_rerank` and the rerank itself returned `low_confidence` (separate signal from L3's current binary hit/miss). For now this is a research action, not a fix.

**TDD shape:**
- Unit: a synthetic page with an `<input>` and an autocomplete `<ul>` that appears 100 ms after typing. With the wait fix, the screenshot captures the open dropdown; L4_vision is called with that screenshot and returns hit (using a stub vision LLM that asserts the dropdown is visible).
- Replay: A3 round-8 traces with the screenshot dumps; manual confirm whether the captured PNG shows the dropdown.

**Expected impact:** If capture bug, unblocks dropdown-pick failures in A3-class tasks. If model bug, the instrumentation tells us so and we de-rank L4_vision rather than continuing to pay its latency cost. Either way, the dump is the cheap first move.

---

## Lower-severity round-8 observations (track, do not file)

- **`_summary.json`'s PASS flag is misleading.** All 5 cases marked PASS though only U4 actually returned a useful answer. The summary line should fold `terminal is not None`, `terminal.status not in {None, "unverified", "partial"}`, AND `result_quality_check_passed` into the verdict — not just the ask_user expectation. Re-flagged from round-5; still uncorrected because the runner is in `/tmp/`. If the runner ever moves in-repo, fix this in the same PR.
- **F16 still pending.** A6 round-8 has step_id 1 → 6 with no events between (100 s of LLM round-trips silent). Trace gap closure is independent of any pass-rate fix and should land before the next round of update_agent2.
- **Plan-after-answer grew significantly between rounds.** A3 round-8 plan is 10 steps including the user's date and one-way constraint — F19 visibly working. A6 round-8 plan is 5 steps and includes "Apply filter or sort by rating". A1 plan is 6 steps including Tianmu. The single-step-degenerate plan from round-6 is gone.
- **Wasted Resy hops in A1.** Agent took 4 actions on resy.com (a US-only platform) for a Taiwanese restaurant before bailing. Generic shape: post-search "no results" detection on the candidate platform should trigger an immediate `read` of the post-search state and a replan, not a free-form "click around the locale switcher." Not severe enough to be its own ticket; fold into F26's structural-replan triggers if convenient.
- **Read with empty `args={}`** (round-6 observation) does not appear in round-8 — agent now always supplies `intent` and/or `find`. Carrying over only as confirmation that the round-6 prompt cleanup held.

## Round-8 cross-cutting note

Round-8 confirms the truncated-ladder removal landed: every locate event now traverses the full L1/L2/L_textmatch/L3_rerank/L4_vision ladder, and L3_rerank successfully resolved the ambiguous "Tokyo button" / "the button" cases rather than failing silently. F19 is also in production — A3 and A6 plans now weave the user's answer into the steps. The new failures (4/5 timeouts) are not regressions of the truncated-ladder fix; they are second-order: deeper ladder traversals cost ~10–20 s each on Qwen3.5-27B, and one full-ladder miss (A3 seq 7–11) consumed 20+ seconds before the agent could try a different intent. F24 (refuse-degenerate-intent) and F25 (immediate-JS-click on deep-tier hits) directly address the budget knock-on. F21–F23 (silent done/partial, stale prompt whitelist, read-find error semantics) are independent correctness fixes — none of them are prompt-shape recipes; all of them live in `agent/loop.py`, `agent/locate.py`, or the prompt-rendering pipeline. The de-bench-maxx direction is intact.

---

## Round-9 verdicts

Round-9 is the first run after the F19–F27 implementations landed (uncommitted at time of run; see `git diff --stat` against `104e152`). Traces: `task2/benchmark/feat-task2-sessions-ask-user-http/ask_user_smoke/round9/{A1,A3,A6,U1,U4}.json`.

| case | task                              | expected ask | asked | terminal               | result quality                              | t (s) |
|------|-----------------------------------|--------------|-------|------------------------|---------------------------------------------|-------|
| A1   | Book Inparadise (旭集) Saturday   | yes          | yes   | failed                 | clean self-fail (agent emitted `tool=fail`) | 296.5 |
| A3   | Cheapest TPE→NRT flight           | yes          | yes   | none (harness 360 s)   | F19 regressed back to 1-step plan           | 365.8 |
| A6   | Best ramen Tokyo on Maps          | yes          | yes   | done                   | 3 tied at 4.8★, but Shinjuku constraint dropped from `type` call | 281.8 |
| U1   | 2018 Turing Award                 | no           | no    | done                   | correct (all 3 names + citation, 43 s)      | 43.1  |
| U4   | "Attention Is All You Need"       | no           | no    | done                   | correct (verbatim abstract, 8 authors)      | 119.5 |

`_summary.json` shows PASS for all five (the round-8 caveat still holds — that flag tracks ask_user-fired-as-expected only, not result quality). Qualitative count: **3 PASS / 1 PARTIAL / 1 FAIL**.

Confirmed shipped vs round-8:
- **F23 (`read find` full-text scan)** — U1 wins on the first try (`outcome=ok, match_count=1`); U4 correctly distinguishes "absent" (`match_count=0`) from "page broken." U1 went from 374 s timeout → 43 s pass. Largest correctness win of the round.
- **F21 partial-status downgrade** — A1 event 22 emits `done {result.status:"partial"}` and gets `outcome=halted_by_supervisor` rather than passing through to terminal.done; agent then ends with a clean `tool=fail`. Round-8's silent done/partial mismatch is closed.
- **L3_rerank end-to-end** — A1 event 26 resolves an ambiguous `網路訂位 link` at L3_rerank; full ladder reachable on real CJK pages.

### A1 — Book Inparadise (旭集) — FAIL (improved error envelope vs round-8)
- **Thinking:** Single focused ask `Which city or location of Inparadise (旭集) would you like to book a table at?`. Plan after answer is 7 steps including `Select the Tianmu (天母) location` and `Saturday, May 9, 2026` — F19 woven correctly here (date answer in plan).
- **Action:** `goto google` → `goto inparadise.com.tw` → `click "網路訂位 link"` (5 times across steps 3, 6, 8, 10, 16) interspersed with `click "Close button"` and re-reads of the booking interface; agent emits `done {status:"partial"}` at step 15 → supervisor halts → L3_rerank resolves ambiguous link → final `read` → `tool=fail` with grounded reason.
- **Answer:** `terminal.status="failed"`, no result, no evidence. Honest reporting; better than round-8's "done with self-failed result." The substantive failure is that the booking site's reservation modal does not progress despite repeated successful clicks — this is a real product limitation, not an agent bug.
- **Trace gaps:** step ids `[1,2,3,4,6,7,8,10,15,16,17,18]` — six missing steps (5, 9, 11, 12, 13, 14). F16 still pending.

### A3 — Cheapest TPE→NRT flight — FAIL (F19 regression)
- **Thinking:** Single focused ask `What is your departure date…`. **Plan after answer is back to 1 step** (`"Book a flight from Taipei to Tokyo and return the cheapest fare."`) — verbatim original task with no mention of `December 15, 2026` or `one-way`. F19's one-shot retry was used (planner saw the corrective note) but the second response was likewise degenerate, and per spec F19 accepts the second attempt regardless. The user's date and trip-type constraints are now invisible to every downstream step.
- **Action:** `goto flights.google.com` → `type "Where from?" "Taipei"` ok → `type "Where to?" "Tokyo"` ok → `click "Tokyo, Japan button"` **35 s timeout at L1_ax** → `read {}` → `locate "Taipei City Tokyo flight link"` 4-tier miss (~15 s of locator latency burned) → `locate "Search flights button"` 4-tier miss again (~25 s burned) → replan to 8 steps that **also do not mention the date or one-way** → harness 360 s budget exhausted on the next `read`.
- **Answer:** No terminal event. Two reinforcing root causes: (1) F19 retry budget is too small for date/numeric-only answers — the planner consistently produces a plan that doesn't reference them; (2) intent vocabulary is wrong on Google Flights ("Search flights button" doesn't match the page's `Search` button name) → 4-tier ladder traversal eats ~15 s per miss. F25 didn't fire because the "Tokyo, Japan button" hit was at L1_ax (F25 only triggers on L3_rerank/L_textmatch/L4_vision tiers).
- **Trace gaps:** step ids `[1,3,4,6,7,13]` — seven missing acts. The 365 s wall-clock with only 6 acts means each step is ~60 s on average; a lot of that is the locator ladder running silently.

### A6 — Best ramen Tokyo on Maps — PASS (with constraint-drop caveat)
- **Thinking:** Single focused ask. Plan after answer is 5 steps including `Search for 'ramen restaurants in Shinjuku, Tokyo'` and `Apply filter or sort by rating`. Replan after a Maps locator miss explicitly acknowledges the superlative limitation (`Note that multiple restaurants have high/similar ratings (acknowledge superlative limitation)`) — that is exactly the F20-shape behavior we wanted, generated organically by the planner without a prompt rule.
- **Action:** `goto maps.google.com` → `type "the combobox" "ramen restaurants in Tokyo" submit=true` → `locate "the search button"` 4-tier miss (harmless; submit handled the search) → `read "the list of ramen restaurants with their ratings" fallback=body` → `done` with three 4.8★ candidates (Jikasei MENSHO Shibuya, Menya NOBUNAGA Kyobashi, Halal Ramen Ueno Taito) plus a comparison note listing 3 lower-rated alternatives.
- **Answer:** `terminal.status="done"` with grounded list — evidence text snippet contains all three names verbatim from the Maps results page. Better than round-6's silent single-candidate done. **Caveat:** the user said "in Shinjuku" but the actual `type` call sent `"ramen restaurants in Tokyo"` (Shinjuku dropped from the search query despite being in plan step 2). The 3 winners are in Shibuya/Kyobashi/Taito — none in Shinjuku. So the answer is grounded but does not satisfy the user's locality constraint.
- **Trace gaps:** step ids `[1,4,6,8]` — four missing.

### U1 — 2018 Turing Award — PASS (F23 win, 43 s)
- **Thinking:** No ask, 4-step plan, coherent.
- **Action:** `goto en.wikipedia.org/wiki/Turing_Award` → `read find="2018"` → `outcome=ok, match_count=1` (this is the F23 fix; round-8 returned `outcome=error` here and sent the agent on a 374 s wandering loop) → `done` with all 3 winners and the citation. 6 events, no replans, no halts.
- **Answer:** `{winners: ["Yoshua Bengio", "Geoffrey Hinton", "Yann LeCun"], year: 2018, citation: "..."}`. Evidence text snippet is verbatim from the recipients table including the citation. Factually correct. **Cleanest non-trivial run in the suite's history.**

### U4 — "Attention Is All You Need" — PASS (clean, F23 negative path)
- **Thinking:** No ask, 4-step plan.
- **Action:** `goto arxiv.org` → `type "Attention Is All You Need" submit=true` → `read fallback=body` results page → **`read find="Vaswani"`** returns `outcome=ok, match_count=0` (note: this is the F23 distinction at work — round-8 returned `outcome=error` here, treating "absent on this page" as "page broken"; round-9 returns ok with 0 matches and the agent correctly interprets it as "look elsewhere") → `goto /abs/1706.03762` → `read fallback=body` → `done` with full abstract, 8 authors, arXiv id.
- **Answer:** Verbatim 4-paragraph abstract; URL and evidence both grounded.

---

## F28 — F19 retry budget is insufficient for date/numeric-only answers

**Severity:** P1.

**Evidence:**
- A3 (`…/round9/A3.json` event 4): user answered `"December 15, 2026, one-way"`; the resulting `plan reason=initial` has 1 step that is verbatim the original task with none of `december`, `15`, `2026`, `one-way`. F19's single retry (`agent/plan.py:312–321`) was used (the corrective note was sent), and the planner returned another degenerate response. Per F19's "cap at one attempt" rule, the loop accepts the second attempt regardless. Round-6 also fixed this for non-numeric answers (Shinjuku, Tianmu still survive in A6 / A1) — only the date/quantity-shaped answers are dropping today.
- A6 (`…/round9/A6.json` event 7): the planner *did* include "Shinjuku" in the plan steps (so F19's plan-text check passes), but the **actual `type` tool call dropped Shinjuku** — `type {text: "ramen restaurants in Tokyo"}` instead of "in Shinjuku, Tokyo." So the F19 contract ("answer survives into the *plan*") is satisfied, but the answer doesn't reach the action layer. Two complementary failure modes; same root: the answer-to-action chain is too lossy.

**Diagnosis:** F19 is a structural plan-text containment check. Three independent gaps:
1. The retry budget is 1; for hard-to-paraphrase answers (dates, numbers, locale-specific names), the planner needs a stronger nudge or a second-line enforcement.
2. F19 only verifies *plan steps* — it does not verify that downstream tool calls (`type`, `goto`, `click`) preserve the answer when the plan step text contained it.
3. `_ANSWER_NOT_INCORPORATED_MESSAGE` likely says "incorporate the answer" without specifying *which* answer or *which* tokens are missing. A more directive note ("the user's answer was X; your plan does not mention X; rewrite") would help; the current spec is unclear on phrasing.

**Fix:**
1. **Strengthen the F19 retry message** in `agent/plan.py`: include the literal user answer text and the specific missing tokens (computed from `_answer_tokens`), so the LLM has zero ambiguity. Phrase: `"Your previous plan does not reference the user's answer ({answer!r}). At minimum, the tokens {missing_tokens} must appear in the plan steps."`.
2. **Optional second retry, gated on numeric-shape detection.** Only when `_answer_tokens` contains a digit-bearing token (years, dates, prices, IDs) and the first retry still fails, allow one more attempt. The gate is structural ("the answer contains a digit"), not domain — generalises to any task asking for numeric specificity.
3. **Plan-step → tool-arg drift detector** (separate concern, fold into a new ticket if scope creeps): for each `type`/`goto`/`click` whose containing plan step references an answer token, assert that token appears in `args.text` / `args.url` / `args.intent`. On miss, surface as a soft `step_advance` warning (no halt) so the next planner iteration sees it. Defer to F30 if separation is cleaner.

**TDD shape:**
- Unit: `_FakeLLMClient` returns (a) ask_user `"What is your departure date?"`, (b) 1-step plan that omits "December 15", (c) on retry-1, another 1-step plan that omits it. Assert `plan()` makes a third call when the answer contains a digit token (numeric-shape gate). Existing F19 tests should still pass on word-shaped answers (Shinjuku, Tianmu).
- Unit: same fake but answer is `"highest-rated by Google reviews, in Shinjuku"`. Assert exactly 2 LLM calls (current F19 behavior preserved on non-numeric answers).
- Unit: corrective message includes the literal answer text and missing tokens. (Simple string-content assertion.)

**Expected impact:** A3 plan post-answer becomes ≥3 steps that name the date and one-way constraint; downstream `type` of "December 15, 2026" into the date field becomes possible. Estimated +1 case in ambiguous smoke. Cost: at most +1 LLM call per ambiguous run when the answer is numeric-shaped (small fraction).

---

## F29 — Bump F16 to P1 (trace-gap closure)

**Severity:** P1 (was P2 in round-5).

**Evidence:**
- A1 round-9: act step ids `[1,2,3,4,6,7,8,10,15,16,17,18]`; six missing (5, 9, 11, 12, 13, 14).
- A3 round-9: act step ids `[1,3,4,6,7,13]`; seven missing (2, 5, 8–12).
- A6 round-9: act step ids `[1,4,6,8]`; four missing.
- Three diagnostic rounds in a row (rounds 5, 8, 9) where the trace was sparse enough that update_agent2 had to *guess* what the LLM was doing during silent steps. In round-9 the silence accounts for ~50 % of step ids in the failing cases. The clean cases (U1: `[1,2,3]`, U4: `[1,2,3,4,5,6,7]`) have zero gaps — which is itself diagnostic: gaps correlate with failures, but we cannot tell whether they *cause* the failures or merely mark them.

**Diagnosis:** Same as F16's original. The fix shape is unchanged from `agent/loop.py:1` — the bump is severity, not direction. Until this lands, every `update_agent2` pass spends 30–40 % of its time inferring step contents from neighbors.

**Fix (unchanged from F16):**
1. In `agent/loop.py`, the branches that `continue` after `_consecutive_no_tool_call_steps += 1` and after JSON-decode/arg-validate failures must each emit a single `step_advance` trace event with `step_id`, `reason ∈ {no_tool_call, parse_error, arg_validate_error}`, and the assistant `content` truncated to 256 chars.
2. The trace-writer already supports `kind="step_advance"` (per round-8 commit `0fd2756`); the wiring just isn't installed at the silent branches.

**TDD shape:** unchanged from F16. Add: a regression test that replays the round-9 A1 trace and asserts the resulting step-id sequence is contiguous after the patch.

**Expected impact:** Zero pass-rate change. Round-10's update_agent2 saves ~30 % wall time in diagnosis. More importantly, F28 (above) and any future "answer-to-action chain" investigation depends on knowing what the LLM emitted at gap steps — without F29, F28's "drift detector" idea cannot be validated against trace data.

---

## F30 — Plan-step → tool-arg drift on user-supplied tokens

**Severity:** P2.

**Evidence:**
- A6 round-9: plan step 2 reads `Search for 'ramen restaurants in Shinjuku, Tokyo'`. The actual `type` call at event 7 sends `text: "ramen restaurants in Tokyo"` — Shinjuku silently dropped between plan and execution. Final answer lists 3 restaurants in Shibuya/Kyobashi/Taito — grounded on the page but not in the requested locality.
- This is the symmetric failure to F19: F19 ensures the *plan* references the answer; F30 catches the case where the plan does, but the *tool args* don't.

**Diagnosis:** The agent's per-step LLM call sees the plan step text but the resulting `args.text` is freely chosen by the LLM. There is no structural check that user-answer tokens that appear in the current plan step also appear in the tool args. Generic shape: any answer constraint can be lost at the plan→action boundary if the per-step LLM compresses or paraphrases.

**Fix:**
1. Compute the set of user-answer tokens (reuse `_answer_tokens` from F19) once per run.
2. Before dispatching a `type` / `goto` / `click` / `read intent=` tool call, check whether the *current plan step text* (from `step_advance` or the active step) contains any answer token. If yes, assert that the same token appears in the relevant arg field (`text` for type, `url` for goto, `intent` for click/read). On miss, do not halt — emit a `supervisor` event with `verdict="answer_token_dropped"`, `expected_token=...`, and let the next iteration's planner system note include the warning.
3. The check is text-shape only — no semantic interpretation. "Shinjuku in plan, not in args" is a literal substring miss.

**TDD shape:**
- Unit: synthetic plan step `"Search for X in Shinjuku"`; tool call `type {text: "X"}`. Assert supervisor emits `answer_token_dropped` with `expected_token="Shinjuku"`.
- Unit: same plan step, tool call `type {text: "X in Shinjuku"}`. Assert no event.
- Unit: plan step contains no answer tokens. Assert no event regardless of args (no false positives).

**Expected impact:** A6 issues a `type` call that includes Shinjuku on the next iteration after the drift is flagged. Generalises to any locality / numeric / proper-noun answer constraint. Small token cost (1 supervisor event per drift); zero pass-rate cost on cases without drift.

---

## Lower-severity round-9 observations (track, do not file)

- **A1 5-times-`網路訂位 link`-click** — agent clicked the same `intent` at steps 3/6/8/10/16, all `outcome=ok`/`nav`, no progress on the booking flow between clicks. Could be a "same fingerprint + same URL + N consecutive clicks → flag no-progress" detector, but I want F29 (step_advance) to land first so we can see whether the LLM is re-issuing the intent or the loop is dispatching from a stale plan. Do not file until F29 evidence exists.
- **A6 superlative-acknowledgement organic** — replan step 2 reads `Note that multiple restaurants have high/similar ratings (acknowledge superlative limitation)`. This is the F20 behavior we wanted, produced by the planner without prompt-side scaffolding. Worth keeping in mind: if F20's structural classifier ever lands, it should not preempt this organic acknowledgement.
- **A3 "Search flights button" intent** — the page's actual button is named just `Search`. F24 doesn't refuse this (it has a name token). Worth noting that F19/F30 won't help either — "search flights" is the agent's paraphrase, not a user answer. The only fix here would be a prompt-side hint ("use the most-specific page-rendered button name") which conflicts with the de-bench-maxx direction. Leave alone.
- **`_summary.json` PASS flag still misleading** — re-flagged from rounds 5/8. All 5 marked PASS though A3 had no terminal and A1 was failed. The runner is in `/tmp/`; if it ever moves in-repo, fold `terminal.status not in {None, "failed"}` AND `result is not None` into the verdict.

## Round-9 cross-cutting note

Round-9 is the cleanest round so far — 3 honest passes (U1, U4, A6-with-caveat) and 1 honest failure (A1 self-emitted `tool=fail`). F23 is the standout production win: U1 went from a 374 s timeout to a 43 s correct answer, with no other code changes on that path. F21 (partial-status downgrade) and F11/F19 (plan-shape checks) are silently working in cases that previously surfaced as bogus `done`. The remaining issues are concentrated and concrete: F28 (date-shaped answer drop), F29 (bump F16 — three rounds is enough), F30 (plan→args drift). All three live in `agent/plan.py` / `agent/loop.py` / `agent/supervisor.py`; none require prompt-shape changes. The de-bench-maxx direction continues to hold.
