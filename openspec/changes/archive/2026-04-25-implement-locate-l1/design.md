## Context

`task2/plan.md` §Architecture describes `agent/locate.py` as the heart of self-maintenance — a four-tier locator pipeline (L1 AX, L2 DOM, L3 LLM rerank, L4 vision). Ticket #3 is the smallest TDD slice: build **L1 only**, plus the shared shape (`LocateResult`, exception types, intent parser) that the next three tiers will plug into.

Current state: `task2/agent/` contains `llm.py` (ticket #1) and `browser.py` (ticket #2). `Browser.read(selector)` takes a raw CSS selector — the agent loop never sees an intent today because nothing parses one. There is no AX-tree query path, no resolver, no cache.

Constraints worth naming up front:
- **Intent → element is a *contract*, not just a function.** Three later tiers and a SQLite cache will share it. The shape we pick for `LocateResult` and exceptions in this ticket gets locked in for tickets #4, #5, #6, and #7. Wrong shape now = churn later.
- **L1 must be drift-resilient.** That is the whole point of the AX-tree tier — survive class/id renames as long as `role + accessible name` are preserved. The fixture must demonstrate that, not just "an element was found."
- **Real Playwright in tests, not mocked.** Same rule as ticket #2 (`CLAUDE.md` TDD section). The thing under test is "we correctly query the accessibility tree"; mocking Playwright would only test that we know how to call our own wrappers.
- **The intent vocabulary is finite for now.** L1 only needs the roles ticket #3 (and immediate downstream tickets) actually use. Don't ship a full ARIA role registry on speculation.

## Goals / Non-Goals

**Goals:**
- A `locate_l1(page, *, role, name) -> LocateResult` resolver that uses the accessibility tree (Playwright `get_by_role(role, name=...)`) and returns either a unique match or raises a typed miss.
- A small `parse_intent(intent) -> (role, name)` helper that turns "Submit button" / "the Submit button" into `("button", "Submit")`.
- A `LocateResult` dataclass with the fields every later tier needs: `tier`, `role`, `name`, `selector`, `ax_fingerprint`, `confidence`. The fingerprint is what ticket #7's locator cache invalidates against.
- A `locate(page, intent) -> LocateResult` orchestrator — for now it only calls L1, but the entry point exists so ticket #4 can extend it without touching call sites.
- Module-local exception types (`LocateError`, `LocatorMiss`, `IntentParseError`) so the future supervisor (ticket #8) can classify by exception type rather than string-matching error messages.

**Non-Goals:**
- L2 DOM heuristics (label-for, placeholder, ARIA-described-by, text-contains) — ticket #4.
- L3 semantic rerank with the LLM — ticket #5.
- L4 vision fallback — ticket #6.
- Locator cache (SQLite, AX-fingerprint invalidation) — ticket #7.
- Intent-based wiring into `agent/browser.py` (`click(intent)`, `read(intent)`) — those land with the loop tickets.
- Trace events (`LocateEvent`) — ticket #12 owns the trace schema.
- Auto-escalation between tiers from inside `locate()` — that policy lives in `agent/supervisor.py` (ticket #8). L1's job is "I have a unique answer or I don't"; routing the miss is someone else's job.
- A full ARIA role registry. We support exactly the roles the next few tickets call for: `button`, `link`, `textbox`, `checkbox`, `heading`.

## Decisions

### Playwright `get_by_role` over snapshotting the AX tree ourselves

`page.get_by_role(role, name=name, exact=False)` is built on top of the accessibility tree and returns a `Locator` we can immediately count, click, or read. The alternative — calling `page.accessibility.snapshot()` and walking the tree manually — gives us more data but forces us to convert AX nodes back into selectable elements ourselves (no public API for "give me the Locator for this AX node"). Snapshotting is the right tool for *building observations* (ticket — `agent/observe.py`), not for *resolving a single intent*.

`exact=False` for name matching: the AX accessible name is normalized (whitespace collapsed, casing preserved), but agent intents will be human-typed. Substring/case-insensitive matching is what `get_by_role` does by default with `exact=False` and matches the agent's mental model ("Submit button" should find a button labelled "Submit Form" too in later tiers; for L1 we still require uniqueness).

### `LocateResult.selector` is a Playwright role-locator string, not a CSS selector

We store `selector` as the Playwright locator expression that produced the match (e.g. `role=button[name="Submit" i]`). It is round-trippable via `page.locator(selector)` and survives serialization for the locator cache (ticket #7) and the trace `LocateEvent.candidates[].selector` field (ticket #12). CSS would be lossier — many AX matches have no stable CSS path.

### `ax_fingerprint` = `sha256(role + ":" + accessible_name)` for L1

The fingerprint exists so ticket #7's cache can detect drift. For L1, the only signal that matters is `(role, accessible name)` — that is *the* thing that picked the element. Hashing them gives a small stable string. Later tiers will extend the fingerprint definition (e.g. L2 may include a normalised label, L4 a perceptual hash) but each tier is responsible for its own scheme. The cache treats the fingerprint as opaque.

Alternative considered: include `text_content`, bounding-box, or DOM path. Rejected as over-spec for L1; those signals belong to lower tiers and would force the cache to re-evaluate them on every read.

### `LocatorMiss` carries a `reason` field, not separate exception types

`LocatorMiss(reason="zero_matches")` and `LocatorMiss(reason="ambiguous")` rather than `LocatorNotFound` + `LocatorAmbiguous`. The supervisor (ticket #8) routes both to the same place — try the next tier — and treating them as one type avoids a `try/except` cascade at every call site. The `reason` field is what the trace classifier reads.

`IntentParseError` is separate because it is a *programmer error / planner error*, not a UI-state failure: the supervisor cannot recover from it by switching tiers.

### Intent parsing: tokenize on whitespace, last token is the role

`parse_intent("the Submit button")` → strip leading article (`the`/`a`/`an`), take the trailing token (`button`), validate it against the known role set, return `(role="button", name="Submit")`. Empty name is allowed (`parse_intent("Submit button")` for a button literally named "Submit"; `parse_intent("Search button")` for one named "Search"; `parse_intent("button")` would yield `("button", None)`).

Alternative considered: ask the LLM to extract `(role, name)` from the intent. Rejected for L1 — adds an LLM round-trip on every action, masks failures, and the rule "trailing role keyword" matches what the planner is already going to emit (the planner prompt in ticket #5 will codify this convention). LLM-assisted intent parsing is a fallback we can introduce *if* the simple parser starts misclassifying real prompts, not before.

Alternative considered: accept structured `intent={"role": ..., "name": ...}` only. Rejected — the rest of the loop deals in NL and forcing structure on every call site is awkward. We accept *both*: `locate(page, intent="Submit button")` and `locate_l1(page, role="button", name="Submit")`.

### Roles supported in this ticket: `button`, `link`, `textbox`, `checkbox`, `heading`

Smallest set that covers ticket #3's fixture, plus the immediate next tickets' likely needs (form fill in #4, navigation in #9, observation in #10). Adding a role later is a one-line change to a frozen set; *removing* one is more painful, so we do not pre-load the registry.

### Module-local exceptions, no shared `agent/errors.py`

Same call we made in ticket #2: only one consumer today (`locate.py` itself, plus its tests). Promote shared types when a second module needs them. Ticket #8 (supervisor) is the natural promotion point — it imports failure types from every tier.

## Risks / Trade-offs

- **Substring name matching can over-match.** "Submit" matches "Submit form" too. → For L1 we still demand a *unique* match; multiple matches → `LocatorMiss(reason="ambiguous")`, escalates to L3 (LLM rerank) in ticket #5. Acceptable trade.
- **`get_by_role` is implemented in Playwright JS land**, so its accessible-name computation may diverge subtly from the spec on some elements (the docs note it does not implement the full algorithm). → We pin the Playwright version via `uv.lock`; future divergence shows up as a test diff, not silent breakage. The L2 tier (ticket #4) explicitly handles cases L1 misses.
- **The fixture's "spoofer" only proves we ignore *non-semantic* mimics.** A `<div role="button" aria-label="Submit">` looks identical to a real `<button>Submit</button>` in the AX tree and would correctly cause an `ambiguous` miss. → Tested explicitly: an ambiguous-match scenario in the spec validates that L1 *correctly fails open* rather than picking arbitrarily, so the supervisor can escalate.
- **Intent vocabulary will grow.** Every new role added is one line and one test, but it is still a touchpoint. → Acceptable; the alternative (open-vocabulary parsing now) is more risk for less benefit.
- **`LocateResult.confidence` for L1 is always `1.0` when a unique match is found.** It is not actually a graded confidence, just a tier marker. → Documented in the spec; L3 (rerank) is the first tier where confidence will carry signal. We keep the field now to avoid changing the dataclass shape mid-ticket.
