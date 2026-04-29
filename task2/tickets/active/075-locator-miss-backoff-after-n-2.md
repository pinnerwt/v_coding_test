---
id: 75
slug: locator-miss-backoff-after-n-2
status: active
tier: 1
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-implement-no-tool-call-repeat/webvoyager/20260429_013158.json
related:
- 106
- 70
- 72
- 73
filed_pr: null
merged_pr: null
archived_at: null
trigger: '`/done_pr` step 1b'' diagnostic on 2026-04-29 against PR #106 (ticket #73).
  The trace inspection that ruled out "Qwen sampling noise" as the sole cause is recorded
  in PR #106''s review thread on the same date.'
---

75. **Locator-miss backoff after N=2 escalations on the same intent root noun.** Diagnostic on PR #106's WebVoyager run (`task2/benchmark/task2-implement-no-tool-call-repeat/webvoyager/20260429_013158.json`) showed `webvoyager-2`'s 9-consecutive-click loop is driven by a real locator-pipeline weakness, not stochastic noise. The case logs **3 explicit `locatormiss` escalations** on intent variants `"the first Search button"`, `"the Search button after Login link"`, `"the Search button after the Login link"` — all `from_tier=L1_ax, to_tier=null, reason=locatormiss`. Per-step latency ramps from 5–10s in steps 0–6 to **24–39s in steps 7–12** during the click loop; cache_events: `{hits: 0, misses: 6, invalidations: 0}`. The arXiv homepage Search button is not addressable through the AX tree by these phrasings (icon-only or no accessible name), and `_stuck_buf` (#70) cannot fire because the planner re-phrases the intent string each time so `(tool_name, json.dumps(args))` differs byte-by-byte. Concrete fix: in `agent/locate.py` (or wherever the escalation outcome is recorded), maintain a per-case map `intent_root → consecutive_locatormiss_count` keyed on the intent's *root noun phrase* (a cheap stem: lowercase + stopword strip + match the trailing 1–3 tokens before the optional "after X" qualifier — e.g. `"first Search button"`, `"Search button after Login link"` both reduce to `"search button"`). When the count reaches `_LOCATORMISS_BACKOFF_K = 2`, surface the signal to the next observation as `last_action.locator_miss_streak: 2` (or a new `ObservationEvent.locator_backoff_intent: "search button"` field) and add a system-prompt clause telling the planner: "intent `search button` has missed twice; do not call `click(intent=...search button...)` again — try `goto(<canonical-search-url>)` or `type(intent=<query-input>)` instead." Reset the counter on any successful tool call OR on a different intent root. Tests: a stub `Browser` whose `_locate_l1_ax` returns `LocatorMiss` for any click whose intent contains `"search button"` (case-insensitive); a stub `LLMClient` that emits `click(intent="the first Search button")`, `click(intent="the Search button after Login link")` for the first two steps; assert that step 3's observation contains the `locator_backoff_intent` signal AND the existing prompt-render produces a system message that names the missed intent. A second test with two misses on different root nouns (`"Search button"` then `"Login link"`) asserts the counter does NOT trip (different roots). A third test asserts a successful click between two misses resets the counter. *Why useful:* webvoyager-2 added $0.18 + 245s + 172K tokens to PR #106's run vs baseline — every cent and second of that came from re-trying the same locator-miss family. The fix doesn't require building the visual L2 fallback (separate ticket); it just makes the planner stop dispatching `click(intent=...)` against an element the AX tree provably cannot find. Pairs with #72 (observation-digest companion) which catches the *symptom* of no state change; this catches the specific *cause* of locator-miss thrashing earlier and with a more actionable signal to the planner. Same mechanism would help any future arXiv/Wikipedia/etc case where a button's accessible name diverges from the planner's natural-language guess. *Trigger:* `/done_pr` step 1b' diagnostic on 2026-04-29 against PR #106 (ticket #73). The trace inspection that ruled out "Qwen sampling noise" as the sole cause is recorded in PR #106's review thread on the same date.
