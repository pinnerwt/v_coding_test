---
id: 56
slug: fixture-count-fails-intentparseerror-items-list
status: active
tier: 1
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-implement-canary-suite/results.json
related:
- 37
filed_pr: 88
merged_pr: null
archived_at: null
trigger: 'surfaced by `/new_task2` smoke for ticket #37 on 2026-04-28; failing trace
  recorded under `task2/benchmark/task2-implement-canary-suite/results.json` (`fixture-count`
  case, `failure_class="tool_error"`).'
---

56. **`fixture-count` fails with `IntentParseError` for `items`/`list` role tokens.** When `task2/eval/cases/fixture-count.yaml` runs (with the `data:text/html,...<ul><li>...</li></ul>` fixture from #37), the agent's first locate call raises `IntentParseError("unknown role token 'items'")` (or `'list'`) from `agent/locate.py::IntentParser`. Reproduction: `cd task2 && uv run python -m scripts.eval --case fixture-count`; the case completes 0 productive steps, gets `failure_class="tool_error"`, and is currently held out of the canary set for that reason (canary suite #37 covers `fixture-heading` + `canary-read-h1` only). The locate engine's `INTERACTABLE_ROLES` (or equivalent role allow-list) does not include the ARIA roles for list containers (`list`) or list children (`listitem`), and the LLM's natural phrasing for "all list items" maps to those tokens. Fix options: (a) extend the allow-list to include `list`/`listitem` and verify the L1/L2/L3 cascade returns sensible candidates (likely L1 by role+name), (b) add a text_contains intent that lets the parser match "list of items" / "all items" by `nodes containing tag <li>` without going through the role token at all, (c) both. Tests: unit test in `task2/tests/test_locate.py` asserting `IntentParser.parse("the list items")` returns a typed intent (no exception); integration test in `task2/tests/test_eval.py` running `fixture-count` against a stubbed LLM that emits the canonical phrasing and asserts `status in PASS_STATUSES`. Once green, re-add `canary: true` to `fixture-count.yaml` and update the canary-gate spec to enumerate three canaries instead of two. *Why useful:* unblocks the third canary slot for the must-always-pass set (a single failure mode in the gate is brittle), and removes a class of `IntentParseError` failures that other list-extraction cases will trip on. *Trigger:* surfaced by `/new_task2` smoke for ticket #37 on 2026-04-28; failing trace recorded under `task2/benchmark/task2-implement-canary-suite/results.json` (`fixture-count` case, `failure_class="tool_error"`).
