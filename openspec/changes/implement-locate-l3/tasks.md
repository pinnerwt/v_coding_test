## 1. Test fixtures (red prep)

- [ ] 1.1 Create `task2/tests/fixtures/locate_l3_three_save.html` containing exactly three `<button>Save</button>` elements, each inside a distinct `<section>` with a distinct `aria-label` and an inner `<h2>` heading: "Profile", "Settings", "Documents". Each section also contains a short `<p>` of nearby text that names the section's purpose. No other element with accessible name `Save` and no surrounding overlays.
- [ ] 1.2 Create `task2/tests/fixtures/locate_l3_three_save_alt.html` — same three sections by heading text ("Profile", "Settings", "Documents") but with different class names, different sibling order (e.g. Settings as the first section), and a different outer wrapper. Used to verify the L3 fingerprint is stable across DOM rearrangements that preserve the section heading.
- [ ] 1.3 No conftest changes — `fixture_server` and `playwright_chromium` are reused.

## 2. Failing tests (red)

- [ ] 2.1 Add `task2/tests/agent/test_locate_l3.py`. Import `locate, locate_l1, locate_l3, LocateResult, LocatorMiss` from `agent.locate` so the import alone fails until `locate_l3` exists.
- [ ] 2.2 Write `_make_chat_stub(content_or_callable)` test helper that returns a callable conforming to `agent.llm.chat`'s signature, returning a `ChatResponse` whose `content` is the configured string (or invoking the callable for dynamic responses). Helper SHALL also accept a `fail_if_called=True` mode for "no LLM call expected" assertions.
- [ ] 2.3 Write `test_locate_l3_three_save_picks_middle` against `locate_l3_three_save.html` — call `locate_l3(b._page, role="button", name="Save", llm_chat=stub_returning('{"index": 1}'))`; assert `LocateResult.tier == "L3_rerank"`, `confidence == 0.8`, `role == "button"`, `name == "Save"`, and `page.locator(result.selector)` resolves to a single element whose enclosing `<section>` has `aria-label="Settings"` (the second of the three sections in DOM order).
- [ ] 2.4 Write `test_locate_l3_single_candidate_skips_llm` against the existing `locate_l1.html` fixture for `role="button"`, `name="Submit"` (which has exactly one matching button) — call `locate_l3(b._page, role="button", name="Submit", llm_chat=fail_if_called_stub)`; assert returned `LocateResult.tier == "L3_rerank"`, `confidence == 0.8`, and the stub was never invoked.
- [ ] 2.5 Write `test_locate_l3_zero_candidates_skips_llm` against `locate_l3_three_save.html` for `role="button"`, `name="Refund"` — call with `fail_if_called_stub`; assert `LocatorMiss(reason="zero_matches", match_count=0)` and stub was never invoked.
- [ ] 2.6 Write `test_locate_l3_malformed_json_raises_ambiguous` against `locate_l3_three_save.html` — call with stub returning `content="not even close to JSON"`; assert `LocatorMiss(reason="ambiguous", match_count=3)`.
- [ ] 2.7 Write `test_locate_l3_index_out_of_range_raises_ambiguous` — same fixture, stub returning `{"index": 99}`; assert `LocatorMiss(reason="ambiguous", match_count=3)`.
- [ ] 2.8 Write `test_locate_l3_index_negative_raises_ambiguous` — stub returning `{"index": -1}`; assert `LocatorMiss(reason="ambiguous", match_count=3)`. (Documents that we treat negatives as out-of-range, not Python negative indexing.)
- [ ] 2.9 Write `test_locate_l3_missing_index_field_raises_ambiguous` — stub returning `{"selected": 0}` (valid JSON, wrong key); assert `LocatorMiss(reason="ambiguous", match_count=3)`.
- [ ] 2.10 Write `test_locate_l3_non_integer_index_raises_ambiguous` — stub returning `{"index": "1"}`; assert `LocatorMiss(reason="ambiguous", match_count=3)`. (We require an actual integer; a string-formatted integer is treated as malformed.)
- [ ] 2.11 Write `test_locate_l3_selector_round_trips` against the three-save fixture — pick `index=2` ("Documents"); assert that `page.locator(result.selector)` resolves to exactly one element AND that the element's `textContent` is `"Save"` AND that the enclosing section's `aria-label` is `"Documents"`.
- [ ] 2.12 Write `test_locate_l3_fingerprint_stable_across_dom_changes` — call `locate_l3` against both `locate_l3_three_save.html` and `locate_l3_three_save_alt.html` with stubs that pick the candidate whose section heading is `"Settings"` (whose DOM index differs across the two pages); assert the two `LocateResult.ax_fingerprint` values are equal.
- [ ] 2.13 Write `test_locate_l3_prompt_contains_intent_and_candidates` — capture the messages passed to the stub via a recording stub; assert that the `messages` list contains a string that includes the intent words "Save" / "button" AND that each of the three candidates' section headings ("Profile", "Settings", "Documents") appears in the prompt content. (This is the smoke test that the prompt assembly is wired up; we do NOT pin the exact prompt text — that is an implementation detail.)
- [ ] 2.14 Write `test_locate_orchestrator_cascades_l1_ambiguous_to_l3` against `locate_l3_three_save.html` — call `locate(b._page, "Save button", llm_chat=stub_returning('{"index": 0}'))`; assert returned `LocateResult.tier == "L3_rerank"` and `result.role == "button"`, `result.name == "Save"`. This replaces the prior L2-era assertion that L1 ambiguous propagated unchanged.
- [ ] 2.15 Write `test_locate_orchestrator_surfaces_l3_ambiguous` against the three-save fixture — call `locate(b._page, "Save button", llm_chat=malformed_stub)`; assert `LocatorMiss(reason="ambiguous", match_count=3)`.
- [ ] 2.16 Update `task2/tests/agent/test_locate_l2.py::test_locate_orchestrator_does_not_cascade_on_l1_ambiguous` — rename to `test_locate_orchestrator_l1_ambiguous_now_cascades_to_l3` (or remove it entirely if the new test in `test_locate_l3.py` covers the same path). The old assertion that `LocatorMiss(reason="ambiguous")` propagated from `locate()` is no longer valid behaviour. Document the rename in the commit message.
- [ ] 2.17 From `task2/`, run `uv run pytest tests/agent/test_locate_l3.py -x` and confirm every test fails for the expected reason (missing `locate_l3` symbol, or orchestrator not yet cascading to L3). Existing `tests/agent/test_locate.py` and `tests/agent/test_locate_l2.py` (after the 2.16 update) SHALL still be all-green except for the renamed test.

## 3. Implementation (green)

- [ ] 3.1 In `task2/agent/locate.py`, add module constants `_L3_MAX_CANDIDATES = 10`, `_L3_MAX_HEADING_CHARS = 100`, `_L3_MAX_NEARBY_CHARS = 200`, `_L3_CONFIDENCE = 0.8`.
- [ ] 3.2 Add a JS helper string constant `_L3_CANDIDATE_CONTEXT_JS` that, given an element, returns `{section_heading: str, nearby_text: str}` with truncation done in JS (no Python post-processing of large strings). `section_heading` extraction order: closest ancestor `<section>`'s `aria-label` → first descendant heading (`h1..h6`) of that section → closest preceding heading sibling. `nearby_text` extraction: `textContent` of the closest semantic ancestor (`section, article, nav, aside, main, form`) trimmed and truncated; fallback to parent's text content. Apply `String.prototype.slice(0, limit)` for truncation; collapse internal whitespace before truncating.
- [ ] 3.3 Implement `locate_l3(page, *, role, name, llm_chat=None) -> LocateResult`:
  - Build the candidates locator: `loc = page.get_by_role(role, name=name, exact=False) if name else page.get_by_role(role)`.
  - `count = loc.count()`. If `count == 0`, raise `LocatorMiss(reason="zero_matches", match_count=0)`. The LLM SHALL NOT be invoked.
  - If `count == 1`, build the L3 result for the unique candidate via `loc.first.evaluate(_L3_CANDIDATE_CONTEXT_JS)` to get `section_heading` for the fingerprint, and a selector of the form `f'role={role}[name="{escaped_name}" i] >> nth=0'` (or `f'role={role} >> nth=0'` when `name is None`). The LLM SHALL NOT be invoked.
  - If `count >= 2`:
    - Resolve the LLM callable: `chat_fn = llm_chat if llm_chat is not None else _resolve_default_llm_chat()`. The default-resolver SHALL import `agent.llm.chat` lazily.
    - Cap candidates at `_L3_MAX_CANDIDATES`; for each candidate `i in range(K)`, capture `{accessible_name, section_heading, nearby_text}` via `loc.nth(i).evaluate(...)` (reusing the existing `_ACCESSIBLE_NAME_JS` for the name and `_L3_CANDIDATE_CONTEXT_JS` for the rest, or merging them into one JS pass for efficiency — implementer's call, but document the choice).
    - Build the prompt via a private helper `_build_l3_messages(role, name, candidates)`. The prompt SHALL be a two-message list: a `system` message stating the rerank task and the JSON-only reply contract, and a `user` message containing the intent (e.g. `"Save button"`) and a numbered list of candidates with their section heading and nearby text.
    - Call `response = chat_fn(messages=prompt_messages, temperature=0.0)`.
    - Parse: `data = json.loads(response.content)`; require `isinstance(data, dict)` and `isinstance(data.get("index"), int)` and `0 <= data["index"] < K`. Any failure raises `LocatorMiss(reason="ambiguous", match_count=count)`.
    - Build the selector: `f'role={role}[name="{_escape_quoted(name)}" i] >> nth={chosen_index}'` (or the no-name variant when `name is None`).
    - Build the fingerprint: `sha256(f"{role}:{name or ''}:{candidates[chosen_index].section_heading}".encode()).hexdigest()`.
    - Return `LocateResult(tier="L3_rerank", role=role, name=name, selector=selector, ax_fingerprint=fingerprint, confidence=_L3_CONFIDENCE)`.
- [ ] 3.4 Add a private helper `_resolve_default_llm_chat()` that does `from agent.llm import chat; return chat`, so module load of `agent.locate` does NOT pull in `agent.llm` / `httpx`.
- [ ] 3.5 Modify `locate(page, intent, *, llm_chat=None)` to add the `ambiguous` branch:
  ```python
  except LocatorMiss as miss:
      if miss.reason == "zero_matches":
          return locate_l2(page, role=role, name=name)
      if miss.reason == "ambiguous":
          return locate_l3(page, role=role, name=name, llm_chat=llm_chat)
      raise
  ```
  The L2 branch is unchanged (L2's own `LocatorMiss` still propagates; we deliberately do NOT cascade L2 ambiguous to L3 in this ticket — see design.md "Non-Goals").
- [ ] 3.6 Update the module-level signature to add the optional kwarg-only `llm_chat` parameter on `locate(...)`. Backwards compatibility: positional `locate(page, intent)` SHALL still work for all existing callers.
- [ ] 3.7 From `task2/`, run `uv run pytest tests/agent/test_locate_l3.py` and confirm all new tests pass.
- [ ] 3.8 From `task2/`, run `uv run pytest` (full suite) and confirm tickets #1, #2, #3, #4 tests still pass — in particular the renamed L2-era test in `test_locate_l2.py` reflects the new orchestrator behaviour, and L1 / L2 happy-path tests are unaffected.

## 4. Refactor + housekeeping

- [ ] 4.1 Reread `task2/agent/locate.py`. Look for unifying the per-candidate context extraction with `_ACCESSIBLE_NAME_JS` (one JS function returning all three fields) if it does not bloat that helper beyond readability.
- [ ] 4.2 Confirm `LocateResult`'s field order, frozen-ness, and L1 / L2 constants are unchanged.
- [ ] 4.3 Confirm `agent.llm` is NOT imported at module top of `agent.locate`. Verify with `python -c "import sys, agent.locate; assert 'agent.llm' not in sys.modules"` — actually this is too brittle for a unit test (tests pull in `agent.llm` themselves), so just verify by reading the imports at the top of `agent/locate.py`.
- [ ] 4.4 Run `uv run ruff format .` (no changes after green) and `uv run ruff check .` (clean).
- [ ] 4.5 No new dependencies added to `task2/pyproject.toml`.

## 5. Validation

- [ ] 5.1 Run `openspec validate implement-locate-l3 --strict` — change SHALL be valid.
- [ ] 5.2 Final pre-commit gate from `task2/`: `uv run ruff format .` (no changes), `uv run ruff check .` (clean), `uv run pytest` (all tests pass).
- [ ] 5.3 Three or four conventional commits on the branch:
  - `chore(task2): scaffold implement-locate-l3` (already created in step 2 of the parent skill — counts).
  - `test(task2): add failing L3 locator tests and fixtures`.
  - `feat(task2): add L3 LLM-rerank locator tier and L1-ambiguous cascade`.
  - `refactor(task2): <whatever 4.1 ends up doing>` — only if a real cleanup happens; skip if 4.1 finds nothing worth changing.
- [ ] 5.4 No hooks bypassed at any point.
