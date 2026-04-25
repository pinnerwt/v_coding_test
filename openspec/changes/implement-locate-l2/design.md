## Context

`task2/agent/locate.py` currently exposes L1 only: a Playwright `get_by_role(role, name=name, exact=False)` query that returns either a unique match, a `LocatorMiss(reason="zero_matches")`, or a `LocatorMiss(reason="ambiguous")`. The shared shapes (`LocateResult`, exception hierarchy, intent parser) and the orchestrator entry point `locate(page, intent)` all landed in ticket #3.

L1 leans on Playwright's accessible-name algorithm, which already covers `<label for>`, `aria-label(ledby)`, wrapping `<label>`, and `title`. What it does **not** cover is the agent's working reality on real sites:

- Inputs whose only "label" is `placeholder` text — the `getByPlaceholder` API exists for exactly this case and is widely used in practice. Some browsers expose placeholder as fallback accessible name; Playwright's `get_by_role(name=...)` does not consistently match it.
- Non-semantic clickables — `<div class="btn" onclick>Submit</div>`, `<span role="">Submit</span>` — that have no accessible role at all. L1 returns zero. The element is plainly visible to the user; the agent should be able to click it.

Without L2, the agent's only options on these are "ask the LLM to rewrite the intent" (wasteful) or "halt" (defeats the point of self-maintenance).

Constraints worth naming up front:
- **The orchestrator contract is now load-bearing.** Ticket #3 documented "ticket #4 extends `locate()` to L2 without touching call sites" — that promise has to hold here. The cascade behavior is part of the public surface.
- **L1's design intentionally drew a line at "I have a unique answer or I don't."** L2 must hold the same line per-strategy; it must not pick arbitrarily when its own DOM heuristics yield multiple candidates.
- **Ambiguous L1 ≠ zero L1.** Cascading to L2 on a *zero* miss is recovery from "AX tree didn't see it". Cascading to L2 on an *ambiguous* miss would be a different failure mode (AX saw too many) that L3 rerank is the right tier for. We must not collapse the two.
- **No new dependency.** Playwright already ships `get_by_placeholder`, `Locator.filter(has_text=...)`, and CSS-selector queries. Anything more (e.g. text-similarity libraries) is L3's job.
- **Tests use real Playwright.** Same rule as #2/#3: mocking Playwright would test that we know how to call our own wrappers, not that the heuristics actually resolve real DOM.

## Goals / Non-Goals

**Goals:**
- A `locate_l2(page, *, role, name) -> LocateResult` resolver that catches the two L1-blind cases above (placeholder-only inputs, non-semantic clickables) and returns a uniquely identified element.
- A small, ordered set of L2 strategies (placeholder; text-contains over a per-role clickable taxonomy) where the *first* strategy yielding exactly one match wins.
- An updated `locate(page, intent)` that cascades L1 → L2 on `LocatorMiss(reason="zero_matches")` only.
- L2 results carry `tier="L2_dom"` and a confidence value strictly less than L1's `1.0`, so downstream consumers (locator cache in ticket #7, supervisor in ticket #8, trace events in ticket #12) can tell tiers apart without string-sniffing.
- L2 holds the same "unique or miss" contract per strategy: no arbitrary picks.

**Non-Goals:**
- L3 semantic rerank with the LLM (ticket #5).
- L4 vision fallback (ticket #6).
- Locator cache writes (ticket #7) — `LocateResult.ax_fingerprint` is computed but no persistence happens here.
- Supervisor-level policy: replan, overlay sweep, repeated-attempt budget (ticket #8). The orchestrator's cascade is *one* tier-fall-through on a *single* miss kind; everything else stays in supervisor land.
- Wiring `agent/browser.py`'s `click(intent)` / `read(intent)`. Browser keeps its selector-based surface.
- Adding placeholder/title support for roles other than `textbox` and `button`/`link`. The L1 accessible-name algorithm already handles those.
- An L2 strategy for `checkbox` / `heading`. There is no DOM heuristic that beats AX for these in practice; `locate_l2` short-circuits with `zero_matches` so the supervisor can skip straight to L3/L4 later.

## Decisions

### Strategies, not a single query

L2 is a small **ordered list of strategies**, each a self-contained Playwright query. The first one that yields a unique match wins. Alternative considered: build one merged `Locator` and resolve at the end. Rejected — the strategies have different per-strategy ambiguity handling (e.g. multiple placeholders in a real form is plausible; multiple non-semantic divs with identical text is suspicious), and merging makes the trace event (`LocateEvent.candidates`, ticket #12) lose which strategy contributed which candidate. Keeping them separate lines up with the trace schema.

Order:
1. **Placeholder** (textbox only). Highest precision among L2 heuristics: `placeholder` is text the page author put there to identify a field.
2. **Text-contains over clickable taxonomy** (button/link only). Lower precision — visible text can collide with body copy — but this is the only thing that catches non-semantic clickables.

If strategy 1 finds a unique element we return immediately; we do not "also try" strategy 2 to confirm. The ordering reflects which heuristic is least likely to false-positive.

### Per-role DOM taxonomy for the text-contains strategy

For `button`, the taxonomy is:

```
button, input[type=button], input[type=submit], input[type=reset],
[role=button], [onclick], [class*="btn"], [class*="button"]
```

For `link`:

```
a[href], [role=link], [onclick]:not(button):not(input)
```

We intersect this taxonomy with `Locator.filter(has_text=name)` to constrain "elements that act clickable AND whose visible text contains the intent name". Alternative considered: query everything via `page.get_by_text(name)` and post-filter. Rejected — `get_by_text` returns far too many candidates on real pages (any text node containing the substring), so filtering ambiguity from a 50-element list is its own headache. Starting from a clickable taxonomy is much tighter.

`[onclick]` matches both intentional click handlers and the common pattern of `<div class="btn" onclick="…">`. `[class*="btn"]` and `[class*="button"]` are deliberate — many sites do not add an explicit handler and instead delegate from a parent, so the *class* is the only signal that this is meant to be clicked. Yes, this can over-match (a `<div class="btn-group">` wrapper has `btn` in its class). The text-contains filter prunes most of those, and the unique-or-miss contract handles the rest.

We do not include `[tabindex]` — too noisy, picks up arbitrary focusable elements like every link and form field, and produces ambiguity instead of resolution.

### Confidence value: `0.7`

L1 = `1.0`. L2 = `0.7`. The literal number is not load-bearing — it is the *ordering* that matters: any future tier (L3, L4) will produce a value strictly between 0 and 1, and the cache (ticket #7) will prefer higher-tier hits when it has more than one option. `0.7` leaves room above (L3 reranked picks could be `0.8`) and below (L4 vision could be `0.5`).

Alternative considered: defer confidence to ticket #5/#6 and just record `tier`. Rejected — every consumer that wants to compare across tiers ends up writing the same `tier == "L1_ax"` string-compare. A single numeric field is cleaner and matches the `LocateResult` shape we already locked in.

### `locate()` cascades only on `zero_matches`

The orchestrator becomes:

```python
def locate(page, intent):
    role, name = parse_intent(intent)
    try:
        return locate_l1(page, role=role, name=name)
    except LocatorMiss as miss:
        if miss.reason == "zero_matches":
            return locate_l2(page, role=role, name=name)
        raise  # ambiguous propagates; L3 (ticket #5) will catch
```

Alternative considered: cascade on both `zero_matches` and `ambiguous`. Rejected — L1 ambiguity means "the AX tree saw multiple equally-named elements", which is the case L3 (LLM rerank with surrounding text + section heading) is purpose-built for. L2's heuristics would not disambiguate any better than L1 did (placeholder doesn't apply to ambiguous buttons, text-contains over the clickable taxonomy will return the same N elements). Better to leave the ambiguity for the right tier than swallow it here.

Alternative considered: have the supervisor (ticket #8) own the entire cascade, leaving `locate()` as L1-only. Rejected for now — ticket #3's design explicitly promised ticket #4 would extend `locate()`. The supervisor still owns higher-level policy (overlay sweep, replan, retry budget); the tier cascade is a *resolution* concern, not a *recovery* concern, and belongs with the resolver.

### `locate_l2`'s ambiguity reporting

When *every* L2 strategy returns either zero or >1, we raise `LocatorMiss`. The choice of `match_count`:
- If at least one strategy returned >1 and none returned exactly 1 → `LocatorMiss(reason="ambiguous", match_count=N)` where `N` is the count from the *first non-empty strategy*. Reason: the supervisor / trace just needs an intelligible number indicating "more than one"; summing across strategies would double-count overlapping DOM queries. The exact number is for diagnostics, not policy.
- If every strategy returned zero → `LocatorMiss(reason="zero_matches", match_count=0)`.

Alternative considered: record per-strategy outcomes in the exception. Rejected as ticket #12's `LocateEvent.candidates` is the right home for that detail; the exception just needs to convey the kind of miss.

### Roles outside L2's known set short-circuit

`heading` and `checkbox` reach `locate_l2` only via the orchestrator cascade after an L1 zero-miss. There is no L2 heuristic for them that improves on AX:
- A heading without an accessible name is essentially invisible (no text content, no aria) — there is nothing for "text-contains" to match.
- A checkbox without a label is structurally indistinguishable from any other checkbox; `placeholder` does not apply.

`locate_l2` therefore raises `LocatorMiss(reason="zero_matches", match_count=0)` immediately for unknown roles. Alternative considered: raise a different exception type to distinguish "L2 declines" from "L2 tried and missed". Rejected — adds a code path the supervisor would have to special-case for no benefit; either way the next step is L3.

### Selector string for L2 results

L1 uses `role=...[name="..." i]`. L2 cannot use that — by definition, the matched element does not have an accessible role+name pair that AX would resolve. We instead synthesize the selector from the strategy that won:
- **Placeholder strategy**: `internal:role=textbox >> internal:attr=[placeholder=<name>i]` — wait, that is Playwright internals. Cleaner: `[placeholder*="<escaped>" i]`, validated by re-querying `page.locator(...)` and confirming `count() == 1` with the same DOM node.
- **Text-contains strategy**: the per-role taxonomy CSS plus a text predicate — Playwright supports the engine combination `<css> >> internal:has-text="<text>"` but to stay public-API-only we synthesize as a stable string the cache (ticket #7) can re-query: `<taxonomy-css> >> text=/<regex-escape of name>/i`. Playwright's `text=` engine is a documented locator format.

The **fingerprint**, however, still needs to be deterministic across drift. For L2 we hash `role + ":" + name + ":" + strategy` so two L2 hits that both used the same strategy share a fingerprint. We deliberately do not include the matched element's DOM path in the fingerprint — the entire point of L2 is that the DOM path is not reliable; if we hashed it we would invalidate the cache on every CSS class rename, which is exactly the failure mode self-maintenance is meant to survive.

Alternative considered: omit `selector` and store the raw `Locator` object. Rejected — `Locator` is page-scoped and not serializable; the cache (ticket #7) needs strings.

### Module organization: keep L2 in `locate.py`

Same call as L1: one file, clear top-to-bottom. We resist splitting `locate_l1.py` / `locate_l2.py` until a third tier proves the file is unwieldy. The file remains under ~200 LoC after this change.

## Risks / Trade-offs

- **`[onclick]` and `[class*="btn"]` over-match.** A page with many "btn" classes (button bars, button groups) will produce ambiguity. → Mitigated by the unique-or-miss contract: ambiguous L2 surfaces as `LocatorMiss(reason="ambiguous")`, which (after ticket #5) goes to L3 rerank with surrounding text. We accept that the L2 step itself is a no-op on those pages.
- **Placeholder text is sometimes user-visible noise** ("e.g. you@example.com") rather than a label. Matching `name="Email address"` against placeholder `"e.g. someone@example.com"` would miss. → Acceptable; that case still escalates to L3, and adding fuzzy placeholder matching (string similarity, LLM rerank) is exactly L3's job. We do *not* add a fallback here.
- **Text-contains is case-sensitivity-prone across browsers.** Playwright's `text=` engine is case-insensitive and trim-aware by default, so this is not a per-browser risk in practice — but it is a behavior we depend on. → Pinned via `uv.lock` like all of Playwright's behavior.
- **Cascading inside `locate()` mixes resolution with light recovery.** A purist would put even the one-step fall-through in the supervisor. → We accept the slight overlap because the alternative is ticket #3's stated promise (`locate()` extends without touching call sites) breaking. The supervisor still owns the *policy* of when to call `locate()` again, when to replan, etc.
- **`confidence=0.7` is a magic number.** It encodes a tier ordering, not a measured probability. → Documented in the spec; ticket #5 (L3) and ticket #7 (cache) are the natural points to revisit if a real probability becomes useful.
- **Placeholder match for textbox does not check for label-for / aria-label first.** L1 already did that — by the time we enter `locate_l2`, L1 has already returned `zero_matches`, which means there is no labelled textbox to match. So the order is correct *because of* the cascade contract. If a future caller invokes `locate_l2` directly (e.g. supervisor wants to skip L1), they must accept this design assumption. → Documented in the spec scenario for `locate_l2` direct invocation.
