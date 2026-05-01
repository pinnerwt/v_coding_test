# Ask-User Smoke — Remaining Issues

Round-1: `task2/benchmark/feat-task2-sessions-ask-user-http/ask_user_smoke/{A1,A3,A6,U1,U4}.json`.
Round-2 / round-3 / round-4: `…/round{2,3,4}/`.

## Round-4 verdicts

| case | task                              | expected ask | asked | terminal | result quality                | t (s) |
|------|-----------------------------------|--------------|-------|----------|-------------------------------|-------|
| A1   | Book Inparadise (旭集) Saturday   | yes          | yes   | failed   | null (clean fail)             | 167   |
| A3   | Cheapest TPE→NRT flight           | yes          | yes   | failed   | null (clean fail)             | 115   |
| A6   | Best ramen Tokyo on Maps          | yes          | yes   | failed   | null (clean fail)             | 180   |
| U1   | 2018 Turing Award                 | no           | no    | done     | correct (Bengio/Hinton/LeCun) | 245   |
| U4   | "Attention Is All You Need" abstract | no        | no    | done     | correct (verbatim abstract)   | 110   |

### A1 — Book Inparadise (旭集) — FAIL
- **Thinking:** Asked one focused question on location; canned answer baked into 8-step plan.
- **Action:** `goto maps.google.com/search/...` → `read` (2 ms, ok but empty) → step jumps 2→7 (84 s gap, no events) → supervisor `premature_done` halt → `locate intent="開啟預約連結 link" L1_ax=miss, L2_dom=miss` → terminal failed `no_progress`.
- **Answer:** null (clean fail, no fabrication).

### A3 — Cheapest flight TPE→NRT — FAIL
- **Thinking:** Asked single date question (good). Plan after answer collapsed to 1 bullet — `["Book a flight from Taipei to Tokyo and return the cheapest fare."]`. Not actionable.
- **Action:** `goto google.com/flights` → `click timeout` → `read error` → halt → same `click` retried → `timeout` again → halt → terminal failed.
- **Answer:** null (clean fail).

### A6 — Best ramen Tokyo on Maps — FAIL
- **Thinking:** F3 ask phrasing **landed live** (matches one-shot example).
- **Action:** `goto maps.google.com` → `locate intent="the search textbox" L1_ax=miss, L2_dom=miss` → halt → fallback `goto /maps/search/...` → 2× `read error` → 2 more halts → terminal failed.
- **Answer:** null. Root cause is the textbox locator missing on Google's combobox-role search input.

### U1 — 2018 Turing Award — PASS (slow)
- **Thinking:** 3-step plan, no ask. Coherent.
- **Action:** `goto google` → search-box L1+L2 miss → `goto en.wikipedia.org/wiki/Turing_Award` → `read find=2018` ok → 5 supervisor `premature_done` halts interspersed with successful `read`/`click` → `done` accepted.
- **Answer:** Bengio/Hinton/LeCun, citation correct, evidence snippet directly supports answer. ✓

### U4 — "Attention Is All You Need" abstract — PASS
- **Thinking:** 4-step plan, no ask.
- **Action:** `goto arxiv.org` → `type` (with submit) → `read intent` *error* → `read find="Attention Is All You Need"` ok → `goto /abs/1706.03762` → `read intent` *error* → `read find=Abstract` ok → `done`.
- **Answer:** Full abstract verbatim, URL + snippet correct. ✓ Cleanest run (0 halts, 110 s).

---

## F9 — Supervisor `premature_done` halts fire excessively on extraction tasks

**Severity:** P1.

**Evidence:**

- U1 (`…/round4/U1.json`): **5 consecutive `premature_done` halts** at steps 8/10/12/14, all between successful `read`s on the Wikipedia Turing Award page. Wall-clock 245 s for a task that should take ~60 s. Each halt costs an LLM round-trip (~20–30 s on Qwen3.5-27B) and emits a halt event with `trigger_event_seq=0` (no `act` event tied to it).
- A6 (`…/round4/A6.json`): 3 halts where the agent had only completed `goto`+`read`s — supervisor refused `done` even though no answer was produced.

**Diagnosis:** The supervisor classifies a `done` as premature based on a heuristic that doesn't see the LLM's `result` payload — it fires on plan-cursor mismatch or a `next_goal` containing nav verbs. On extraction tasks the LLM correctly proposes `done` once it has the answer in context, but the heuristic doesn't have visibility into the proposed result, so it halts. The retry costs +20–30 s and a fresh planning context. `agent/loop.py`'s `_classify_done` (or wherever T1/T2 live) is the target.

**Fix:**

1. When classifying a `done` call, inspect the proposed `result` payload — if it contains a non-empty answer field (`result`, `answer`, `winners`, etc.) **and** the page snapshot contains substring evidence for that field, downgrade `premature_done` → `accept`.
2. Add a per-run halt-count for the same `(tool, classified_as)` pair that escalates to `accept` on the 3rd halt with the same evidence (assume the LLM has converged).
3. Emit the `act` event for the rejected `done` so the trace shows what was proposed (currently `trigger_event_seq=0`).

**TDD shape:**

- Unit on `_classify_done`: a `done` whose `result.answer` substring appears in the latest page snapshot is **not** classified `premature_done`.
- Regression on U1: simulate 5 `done` attempts with the same correct `result`; loop must accept by attempt 2, not attempt 5.

**Expected impact:** −60 % wall clock on extraction tasks (U1 from 245 s → ~100 s estimated); −5 LLM calls per such case.

---

## F10 — Trace gaps swallow locator/internal retries (debuggability hole)

**Severity:** P2 (no functional impact; major debuggability impact).

**Evidence:**

- A1 (`…/round4/A1.json`): events jump from step-2 (read ok, ms=2) to step-7 (supervisor halt) — **84-second gap** with no `act` / `locate` / `observe` events.
- A6 round-4: step-1 → step-4 jump (no events for steps 2–3).
- U1 round-4: step-1 → step-4 jump.
- U1 step-7 → step-9 (step-8 supervisor halt with `trigger_event_seq=0`, no `act` event for the rejected `done`).

**Diagnosis:** `step_id` increments inside the loop on each tool dispatch, but trace events for some internal paths (locator retries with no observable browser change, rejected `done` calls, ms=0/2 fast paths) aren't emitted. Reviewers can't tell what the agent did during the gap.

**Fix:**

1. Emit `act` events for *every* tool call, including rejected `done` (with `outcome="halted_by_supervisor"`).
2. Emit `locate` events for every tier attempt, including L3_rerank / L4_vision / L_textmatch (round-4 shows these never appear in any trace — either not run or not logged).
3. Add a `step_advance` event when `step_id` increments without a corresponding tool event, so the gap is at least visible.

**TDD shape:**

- Unit on the trace emitter: a `done` rejected by the supervisor produces an `act` event with `outcome="halted_by_supervisor"` *before* the halt event.
- Unit on the locator: invoking `locate` on a fixture where L1/L2 miss but L3 hits emits 3 events.

**Expected impact:** No pass-rate change; cuts post-mortem time roughly in half for P1 investigations.

---

## F11 — Plan can collapse to a 1-step verbatim restatement of the task after `ask_user`

**Severity:** P2.

**Evidence:**

- A3 round-4: after answer `"December 15, 2026, one-way"`, the planner returned `steps=["Book a flight from Taipei to Tokyo and return the cheapest fare."]`. Not actionable — the agent's first `goto google.com/flights` had no plan support.

**Diagnosis:** After the `ask_user` round-trip, `plan()` re-calls the LLM with the answer baked in. On Qwen3.5-27B the second call sometimes returns a single-bullet plan that just echoes the task. `_PLAN_SYSTEM` says "produce the plan" but doesn't require N steps.

**Fix:**

1. In `agent/plan.py`'s `_PLAN_SYSTEM`, append: *"Final plans MUST contain at least 3 concrete navigation/interaction steps. A 1-step plan that restates the task is not acceptable."*
2. Validation in `_parse_plan`: if `len(steps) < 2`, emit a `replan` immediately with reason `"plan too short"`.

**TDD shape:**

- Unit: a 1-step plan from the LLM triggers a re-plan event before the loop dispatches any action.
- Unit: post-`ask_user` plan with `len(steps) >= 3` passes through unchanged.

**Expected impact:** small (~1 case in 16); unblocks A3-style tasks where the plan-cursor T4 path can't fire because there's no plan to advance through.

---

## F12 — `read(intent="…")` consistently errors on first call; `read(find="…")` works

**Severity:** P2.

**Evidence:**

- U4 round-4: `read intent="the search results showing papers"` → error; immediate `read find="Attention Is All You Need"` → ok. Same again at the abstract page: `read intent="the abstract section"` → error; `read find="Abstract"` → ok.
- U1 round-4: `read intent="the 2018 Turing Award recipients section"` → error; later `read find="2018"` → ok.
- The agent learns this pattern in-context, but burns one LLM round-trip per occurrence.

**Diagnosis:** `agent/observe.py`'s intent-mode `read` path is unreliable on real pages — likely the intent-to-selector translation fails when the page is dense / dynamic. `find=` mode (substring search) is robust because it doesn't rely on translation.

**Fix:**

1. On first `read` error in intent-mode, **internally** retry as a no-args `read()` (returns the full snapshot) before surfacing the error. Saves one LLM round-trip.
2. Update the loop's executor system prompt to prefer `read(find=...)` over `read(intent=...)` for known-text extraction.
3. (Optional) Deprecate `intent` arg on `read` if the no-args + `find` covers the use cases.

**TDD shape:**

- Unit on `_read_handler`: `read(intent="...")` that errors triggers an internal `read()` retry; the LLM sees one `act` event with `outcome="ok"`.
- Snapshot test: tool-docstring update is reflected in the `tools` list passed to `llm.chat`.

**Expected impact:** −1 LLM call per extraction case (~−15 s per case on Qwen-27B); cleaner traces.

---

## F13 — Textbox locator misses `combobox`-role inputs (Google sites)

**Severity:** P2.

**Evidence:**

- A6 round-4: `locate intent="the search textbox"` on Google Maps → L1_ax miss, L2_dom miss → halt.
- U1 round-4: same intent on `google.com` homepage → L1+L2 miss; agent recovered by going directly to Wikipedia.

**Diagnosis:** Google's homepage and Maps both render their search input as `role="combobox"` (per ARIA combobox-with-listbox pattern). `agent/locate.py`'s textbox-tier translates the intent `"... textbox"` to `get_by_role("textbox", ...)` only, so combobox-role inputs are invisible to L1/L2.

**Fix:**

1. In `agent/locate.py`, when intent contains `textbox` / `search box` / `input`, expand the L1_ax tier to try both `role="textbox"` and `role="combobox"`.
2. L2_dom should include `[role=combobox]` in the input selector taxonomy.

**TDD shape:**

- Unit on the locator: synthetic page with `<div role="combobox" contenteditable>` → intent `"search textbox"` returns the combobox element from L1_ax.
- Regression: a captured Google homepage DOM → `intent="the search textbox"` returns the search combobox.

**Expected impact:** unblocks any case that starts at google.com / maps.google.com (~3 of 16 cases in the broader benchmark).

---

## F14 — F8 (`L_textmatch`) tier never appears in round-4 traces

**Severity:** P2 (verification gap).

**Evidence:**

- A1 round-4: `locate intent="開啟預約連結 link"` L1_ax + L2_dom miss → terminal failed. **No `L_textmatch` event.** F8 was added to fire after L2 miss, before L4_vision.
- All 5 round-4 traces: zero `L_textmatch` events even where intents contain CJK substrings (A1: `網路訂位`).

**Diagnosis:** Either (a) F8 is not wired into `_resolve_via_ladder` after L2 miss, (b) F8 fires but doesn't emit a trace event, or (c) the L2 miss path early-returns before F8 is reached. Unit test passes against the synthetic fixture, so the wiring is plausible but unverified live.

**Fix:**

1. Add an integration test that drives the live locator with an L1/L2-missing CJK intent and asserts an `L_textmatch` `kind=locate` trace event is emitted.
2. Audit `_resolve_via_ladder` and the trace emitter for the L2-miss → L_textmatch transition; ensure the event fires regardless of outcome.

**TDD shape:**

- Integration on the locator + trace pipeline: feed `tests/fixtures/locate_cjk_fallback.html` through the real loop → assert exactly one `L_textmatch` event.

**Expected impact:** verifies F8 (no behavior change if already correct); prerequisite for measuring real CJK lift.

---

## Lower-severity observations (track, do not file)

- **A1 `read` outcome=ok with ms=2** — page hadn't loaded; first read returns empty but reports ok. Should classify as "empty" or wait for paint before reporting ok.
- **A3 LLM retried the same failed click intent verbatim** — `click(intent="Find flights from Taipei City (TPE) to Tokyo (NRT) from NT$6,344 button")` timed out twice. The system prompt should say "after a timeout, vary the intent or change tool." Subsumed by F7 + F9 long-term.
- **U1 wasted hop** — `goto google` then immediately `goto wikipedia` without ever reading google. Planner step said "Search Google" but agent went direct to Wikipedia (faster but skipped its own plan step).
- **Two `[plan]` events per run** — `reason=started` (placeholder) + `reason=initial` (actual). Cosmetic, doubles plan-event count in SSE.
- **A1 `read` ok with empty content masked the failure** — the agent thought the search succeeded based on `outcome=ok`, then tried `done` and got halted. Tighten observe.py to return `outcome="empty"` when text is empty.

## Cross-cutting note on the smoke harness

Round-4 confirms the harness is solid: SSE delivery is in-order, ask-user round-trips correct, terminal events tagged. No harness-side bugs surfaced. The single-canned-answer convention from `ask_user_test_set.md` continues to be the right shape — F1 handles off-topic answers cleanly (verified rounds 2–4).
