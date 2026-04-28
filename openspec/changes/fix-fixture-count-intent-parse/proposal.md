## Why

`task2/eval/cases/fixture-count.yaml` currently fails with `IntentParseError("unknown role token 'items'")` (or `'list'`) when the agent's locate call processes the LLM's natural phrasing for "all list items". The `_SUPPORTED_ROLES` allow-list in `agent/locate.py` only covers interactive element roles (`button`, `link`, `textbox`, `checkbox`, `heading`) — the ARIA roles for list containers (`list`) and list children (`listitem`) are absent, so any intent ending with `items` or `list` crashes before the locate ladder even runs. This blocks `fixture-count` from ever producing a productive step, keeps it out of the canary set, and will trip other list-extraction cases in the eval suite.

## What Changes

- Extend `_SUPPORTED_ROLES` in `agent/locate.py` to include `list` and `listitem`.
- Add a role-alias normalization map (`_ROLE_ALIASES = {"items": "listitem", "lists": "list"}`) in `agent/locate.py` and apply it in `parse_intent` after lowercasing the role token, so the production-LLM phrasing `"list items"` parses to `("listitem", "list")` instead of raising `IntentParseError`.
- Add the L1/L2 cascade handling for these new roles: `list` and `listitem` have no interactive counterpart, so the L2 branch returns a `LocatorMiss(reason="zero_matches")` for them, falling through to L4; document this in the spec.
- Add a unit test in `task2/tests/test_locate.py` asserting `parse_intent("the list items")` returns `("listitem", "the list")` — no exception — and `parse_intent("list")` returns `("list", None)`.
- Add a stubbed-LLM integration test in `task2/tests/test_eval.py` running `fixture-count` against a minimal fake that emits the canonical phrasing and asserts `status in {"succeeded", "unverified"}`.
- Re-add `canary: true` to `task2/eval/cases/fixture-count.yaml` once the locate fix is green.
- Update `openspec/specs/canary-gate/spec.md` to enumerate three canary cases instead of two, and remove the hold-out note about `fixture-count`.
- Update `openspec/specs/locator-pipeline/spec.md` to extend the supported role set to include `list` and `listitem`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `locator-pipeline`: the supported role set (currently `button`, `link`, `textbox`, `checkbox`, `heading`) must be extended to `list` and `listitem`; the Intent parser requirement and its "unknown role rejected" scenario need to reflect the expanded set; the parser SHALL also normalize a small set of plural aliases (`items` → `listitem`, `lists` → `list`) so the production-LLM phrasing resolves to canonical roles.
- `canary-gate`: the canary case set (currently two cases: `fixture-heading`, `canary-read-h1`) must be updated to three cases, adding `fixture-count`; the hold-out note about `IntentParseError` must be removed now that the fix is in.

## Impact

- `task2/agent/locate.py` — `_SUPPORTED_ROLES` frozenset (now derived from `get_args(SupportedRole)`) and new `_ROLE_ALIASES` map applied in `parse_intent`.
- `task2/tests/test_locate.py` — new unit test scenarios for `list`/`listitem` role tokens.
- `task2/tests/test_eval.py` — new integration test for `fixture-count` with stubbed LLM.
- `task2/eval/cases/fixture-count.yaml` — add `canary: true`.
- `openspec/specs/locator-pipeline/spec.md` — delta spec updating the role allow-list.
- `openspec/specs/canary-gate/spec.md` — delta spec updating the canary case enumeration to three.
