---
id: 61
slug: tighten-system-prompt-discourage-premature-fail
status: archived
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies:
- 59
pre_flight_gates: []
evidence: []
related:
- 62
filed_pr: null
merged_pr: null
archived_at: '2026-04-28'
trigger: 'surfaced from benchmark analysis on 2026-04-28 alongside #59.'
---

61. **Tighten system prompt to discourage premature `fail`.** `_build_system_prompt` at `agent/loop.py:182-190` currently ends with `If you cannot complete the task, call \`fail\` with a reason.` Combined with the missing `click` tool (until #59 lands), this trains the model to bail after one `read`: every drift/correction failure in the latest benchmark emits `fail` on step 2 of a 5-step budget. Even after #59 lands, the phrasing invites the model to give up the moment it is uncertain. Tighten to: "Call `fail` ONLY for irrecoverable conditions — login walls, captchas, pages that don't exist, or required information genuinely absent from the page. If a target element exists on the page but you don't know how to act on it, attempt `click`/`type` with a natural-language `intent` first; the locator pipeline will resolve it." Tests: (a) a behavioral test using a recorded LLM transcript (or a stub that returns `fail` on step 1 against a page where the target visibly exists) asserts the fail path is gated by a supervisor nudge that re-prompts the model with the tightened phrasing, OR — if we choose the simpler path — assert that the system prompt string contains the "ONLY for" phrasing and the action-first guidance (string-shape lock-in test). Pick (a) only if #62 lands first; otherwise the simpler (b) is enough. *Why useful:* removes a recurring "model gives up despite having tools to try" pattern that masks real `LocatorMiss` failures. *Trigger:* surfaced from benchmark analysis on 2026-04-28 alongside #59.
