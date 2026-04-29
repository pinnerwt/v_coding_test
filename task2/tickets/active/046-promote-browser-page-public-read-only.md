---
id: 46
slug: promote-browser-page-public-read-only
status: active
tier: 6
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 62
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced repeatedly by review subagents on PR #62 (iteration 2 and iteration
  3 reviews).'
---

46. **Promote `Browser._page` to a public read-only accessor.** Multiple tests in `task2/tests/agent/test_loop.py` (and `tests/test_observe.py`) reach into `Browser._page` to drive `_locate_via_ladder` / fixture HTML directly. The underscore is the module's "do not touch outside class" contract, so each leak weakens the convention. Add a `Browser.page` property (or a `Browser.current_page() -> Page` method) returning `self._page` and migrate test call sites. Production code that already lives inside `Browser` keeps using `self._page` as today. Tests: existing tests pass after migration; a new test asserts `Browser.page` returns the same object as `Browser._page` for a freshly opened browser. *Why useful:* the underscore convention should mean something; today it is consistently violated by the test surface. *Trigger:* surfaced repeatedly by review subagents on PR #62 (iteration 2 and iteration 3 reviews).
