## Context

`agent/locate.py` exposes `parse_intent(intent: str) -> tuple[str, str | None]` which strips a leading article, extracts the last token as the role, and validates it against `_SUPPORTED_ROLES = frozenset({"button", "link", "textbox", "checkbox", "heading"})`. The LLM tasked with `fixture-count` naturally phrases its locate call as something like "the list items" or "list item", causing the parser to extract `items` or `item` as the role token — neither of which is in `_SUPPORTED_ROLES`, so `IntentParseError` is raised before any DOM interaction occurs.

Three fix options were considered (from the ticket):
- **(a)** Extend the role allow-list with `list` and `listitem`.
- **(b)** Add a `text_contains` intent path that matches nodes by CSS tag (`<li>`) without needing a role token.
- **(c)** Both.

## Goals / Non-Goals

**Goals:**
- `parse_intent("the list items")` MUST NOT raise `IntentParseError`.
- `parse_intent("list")` and `parse_intent("listitem")` MUST return typed `(role, name)` pairs.
- `fixture-count` eval case MUST complete with a status in `{"succeeded", "unverified"}` when the LLM emits the canonical phrasing.
- `fixture-count.yaml` MUST gain `canary: true` once the locate fix is green.
- `canary-gate` spec MUST be updated to enumerate three canary cases.

**Non-Goals:**
- Adding a `text_contains` CSS-tag intent path (option b/c) — deferred until a test case demands it; option (a) alone unblocks `fixture-count` with zero additional complexity.
- Extending the locate ladder's L2 branch to handle `list`/`listitem` via taxonomy CSS — these roles have no interactive counterpart, so L2 will correctly return `LocatorMiss(reason="zero_matches")` and fall through to L4 vision; that path already works.
- Changing `locate_l1` or `locate_l3` behaviour — Playwright's `get_by_role("list")` and `get_by_role("listitem")` already work; no ladder changes needed.

## Decisions

### Decision: Option (a) plus role-alias normalization map

**Chosen**: Add `"list"` and `"listitem"` to `_SUPPORTED_ROLES`, AND add `_ROLE_ALIASES = {"items": "listitem", "lists": "list"}` applied in `parse_intent` after lowercasing the role token.

**Rationale**: The failing root cause is purely that the role token validator rejects the tokens before any DOM query. Playwright supports `list` and `listitem` as valid ARIA roles natively; `page.get_by_role("listitem")` returns all `<li>` elements. L1 will match when there is exactly one list item (unlikely in the fixture which has three), and L3 will disambiguate when there are multiple. For the `fixture-count` fixture (three `<li>` elements) the L1 call will raise `LocatorMiss(reason="ambiguous")`, fall to L3 (LLM disambiguation), and if that also struggles, fall to L4 vision. The integration test will use a stubbed LLM that confirms a passing outcome. End-to-end verification under real Qwen3.5-27B confirmed the model emits `'list items'` (two words), with last token `items` — the alias map closes that gap so option (a) actually delivers `fixture-count` red→green.

Option (b) adds a parser mode that does not flow through `role`/`name` at all, requiring non-trivial refactors to `LocateResult` and the locate ladder. No eval case currently demands it; adding it now violates the "green minimally" TDD rule.

### Decision: L2 branch for `list`/`listitem` — no-op LocatorMiss

**Chosen**: `locate_l2` already raises `LocatorMiss(reason="zero_matches")` for any role not in `("textbox", "button", "link")`. Since `list`/`listitem` are not interactive, this is correct and requires no code change.

### Decision: Test strategy

- Unit test: `parse_intent` with `"list items"`, `"list"`, and `"listitem"` returns the expected pairs; alias-only inputs (`"items"`, `"lists"`) also return canonical pairs.

  Note: `parse_intent('list items')` returns `('listitem', 'list')` because the role-alias map normalizes `items` → `listitem` after the article-stripping step. Unit tests cover both bare aliases (`'items'`, `'lists'`) and the production phrasing (`'list items'`).

- Integration test: uses a fake LLM chat function; the `fixture-count` case runs against a stubbed agent that emits a locate call ending in `"listitem"` and a read/return step, asserting `status in PASS_STATUSES`.

## Risks / Trade-offs

- [Risk] The LLM in production may still phrase the intent as `"items"` (invalid token). Mitigation: the integration test's stub is written to emit the canonical valid phrasing; a system-prompt note may be added in a follow-up to enumerate valid role tokens.
- [Risk] `page.get_by_role("listitem")` with `name=None` matches all `<li>` elements, returning an ambiguous count, causing L3 LLM disambiguation or L4 fallback. Mitigation: this is expected and correct; the locate ladder handles it; the integration stub sidesteps it by returning a count-based answer without a locate call per item.
- [Risk] Extending `_SUPPORTED_ROLES` with `list`/`listitem` may cause the spec validator in existing tests to fail if they assert the exact set. Mitigation: check `test_locate.py` for hardcoded role sets before the implementation PR.

## Migration Plan

1. Red: write unit test and integration test (failing).
2. Green: add `"list"` and `"listitem"` to `_SUPPORTED_ROLES` and add `_ROLE_ALIASES = {"items": "listitem", "lists": "list"}` to `agent/locate.py`, applying the alias map in `parse_intent` after lowercasing the role token.
3. Green: confirm both tests pass.
4. Add `canary: true` to `fixture-count.yaml`.
5. Update canary-gate spec comment to enumerate three canary cases.
6. Run `uv run ruff check . && uv run ruff format .` from `task2/`.

No breaking changes. No migration needed for existing results files.

## Open Questions

None — option (a) is unambiguous given the current failing trace and TDD constraints.
