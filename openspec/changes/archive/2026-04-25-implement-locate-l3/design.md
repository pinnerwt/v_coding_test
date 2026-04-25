## Context

`task2/agent/locate.py` after ticket #4 has L1 (AX-tree) and L2 (DOM heuristics). The orchestrator `locate(page, intent)` cascades L1 `zero_matches` → L2; L1 `ambiguous` is propagated unchanged with the explicit promise that "ticket #5 will catch it via L3 rerank". This change makes good on that promise.

The driver case from `task2/plan.md` is "fixture with three buttons sharing text 'Save'; LLM rerank (mocked) picks the right section." Three real `<button>Save</button>` elements all show up in the AX tree with role `button` and accessible name `Save`. L1 returns `LocatorMiss(reason="ambiguous", match_count=3)`. L2's heuristics (placeholder, text-contains over the button taxonomy) would also return three matches — they bring no new disambiguating signal. The right tool is to feed the candidates' *surrounding semantic context* (which section they live in, what nearby text says) to the LLM and let it pick.

Constraints:
- **Tests use real Playwright; the LLM is mocked.** Same rule as #1–#4. Mocking Playwright would be testing wrappers; mocking the LLM here is testing the rerank *plumbing*, not the LLM's intelligence — which is what the eval set (ticket #15+) is for.
- **No new dependency.** `agent.llm.chat` from ticket #1 is the only external surface we need.
- **The orchestrator's signature can grow but must stay backwards-compatible for callers passing only `(page, intent)`.** The agent loop (ticket #9) will invoke `locate()` from a tool dispatch; if we ever break the no-kwargs form here, ticket #9 has to refactor on top of an unfinished tier stack.
- **Confidence must keep its tier ordering.** L1=1.0, L2=0.7. L3 lives above L2 (it has more signal — full LLM read of nearby text) but below L1 (L1 had a unique AX answer; L3's pick is a probabilistic call). 0.8 is the obvious slot.
- **`locate_l3` itself runs the AX-tree query.** It does *not* take a pre-resolved Locator from the orchestrator. The reason is direct callability: any caller (a future supervisor that wants to skip L1/L2 entirely, or a test that exercises L3 in isolation) gets the same behaviour without first having to construct a candidate locator. The cost is a redundant `get_by_role` call when the orchestrator cascades — one extra AX-tree traversal per ambiguous L1 miss, which is cheap relative to the LLM round-trip we are about to make.

## Goals / Non-Goals

**Goals:**
- A `locate_l3(page, *, role, name, llm_chat=None) -> LocateResult` resolver that:
  - Re-queries `page.get_by_role(role, name=name, exact=False)` to gather candidates.
  - On 0 candidates → `LocatorMiss(reason="zero_matches", match_count=0)`.
  - On 1 candidate → returns it directly with `tier="L3_rerank"`, `confidence=0.8` (no LLM call needed; this keeps direct invocation cheap and avoids spurious LLM traffic).
  - On ≥2 candidates → builds a rerank prompt, invokes `llm_chat`, parses the JSON reply, picks the candidate at the returned index.
- An updated `locate(page, intent, *, llm_chat=None)` that cascades L1 `ambiguous` → L3 and forwards `llm_chat`.
- A `LocateResult` for L3 hits carrying:
  - `tier="L3_rerank"`.
  - `selector` that re-resolves to the same single element via `page.locator(...)`.
  - `ax_fingerprint` deterministic across runs that pick the same section, independent of class names and DOM path.
  - `confidence=0.8`.
- Bounded prompt size: at most `K = 10` candidates, each with at most `MAX_TEXT_CHARS = 200` of nearby text and `MAX_HEADING_CHARS = 100` of section heading. Prevents prompt blow-up on pages with many same-named affordances.

**Non-Goals:**
- L4 vision fallback (ticket #6).
- Locator cache writes (ticket #7).
- Supervisor-level policy: replan, overlay sweep, repeated-attempt budget, retry-with-different-strategy (ticket #8). L3 returns one answer per call; "what to do if it picks wrong" is supervisor land.
- Wiring `locate_l3` into `agent/browser.py`'s tool surface — `browser.py` is still selector-based.
- Cascading **L2 ambiguous** to L3. The ticket scope is "L1 ambiguous → L3 rerank"; widening it to L2 ambiguous would require its own design call (e.g. should we hand L3 the *L2* candidates, which are by construction non-AX, or re-enter from scratch?). Deferred until the eval set actually surfaces L2-ambiguous-then-L3 as a real failure mode.
- Free-form LLM responses. The LLM is constrained to reply with JSON containing exactly an `index` field; everything else is parse error.
- Chain-of-thought / "rationale" extraction. The trace event (ticket #12) will record the LLM's full prompt/response anyway; we do not need to surface a rationale through `LocateResult`.

## Decisions

### Re-query AX tree, do not pass candidates from `locate()`

Alternative considered: have the orchestrator catch L1's `LocatorMiss(reason="ambiguous")` and forward the *L1 Locator* (or the matched element handles) to L3, avoiding the second AX-tree query. Rejected — `LocatorMiss` would have to grow a payload field carrying the Playwright `Locator`, which leaks resolver internals into the exception API and breaks the existing "exception is just `reason` + `match_count`" contract. The redundant `get_by_role` call is microseconds; the LLM round-trip is hundreds of milliseconds. The cost is in the noise.

### `locate_l3` returns `L3_rerank` even on 1 candidate

When `get_by_role(role, name=name, exact=False)` returns exactly one element, we return immediately with `tier="L3_rerank"` and `confidence=0.8` instead of "passing through" to L1's behaviour. Reason: a caller invoking `locate_l3` directly has explicitly asked for the L3 tier; downgrading to `L1_ax` would surprise that caller and complicate the trace event (ticket #12). The orchestrator never invokes L3 on a unique L1 case (it returned successfully from L1 already), so the only path that hits this branch is direct invocation, which is the path that wants the L3 label.

This does mean direct callers using `locate_l3` on a uniquely named element get a "lower" confidence than if they had called L1. That is the price of explicitly demanding a tier; the orchestrator does not pay it.

### LLM contract: strict JSON-only reply

The prompt instructs the model to reply with **only** `{"index": <int>}` (no prose, no code fences). We attempt `json.loads` on the reply content; on failure, or if the parsed object lacks an integer `index` in `[0, K)`, we raise `LocatorMiss(reason="ambiguous", match_count=N)` where `N` is the candidate count.

Alternatives considered:
- **Tool-calling.** The OpenAI-compatible `tools` field is supported by `llm.py` and would force structured output. Rejected for now — Qwen3.5-27B served by a generic OpenAI-compatible adapter often ignores or partially honours the `tools` field, and a ticket #5 that depends on tool-calling working perfectly upstream is fragile. JSON-in-content is the lowest common denominator and is what every OpenAI-compatible server we have tested actually returns reliably.
- **Free-form prose with regex extraction.** Rejected — too brittle, the failure mode ("LLM said 'I think the second one'") is unobservable in tests.

If a future ticket finds the local model is reliable on `tools`, the prompt can be upgraded; the function signature does not need to change because `LLMClient.chat` already takes `tools`.

### Candidate context: accessible name + section heading + bounded nearby text

For each candidate (in DOM order, capped at `K = 10`) we extract via a single `page.evaluate` over the AX-tree resolved Locator:

- `accessible_name` — same JS as L1's `_ACCESSIBLE_NAME_JS`.
- `section_heading` — text of the closest ancestor `<section>`'s `aria-label`, or its first descendant heading (`h1..h6`), or the closest preceding heading sibling, in that order. Truncated to `MAX_HEADING_CHARS = 100`.
- `nearby_text` — `textContent` of the closest semantic ancestor (`section`, `article`, `nav`, `aside`, `main`, `form`) trimmed and truncated to `MAX_TEXT_CHARS = 200`. Falls back to the parent element's text content if no semantic ancestor is found.

This keeps the prompt small even on busy pages and gives the LLM the two strongest disambiguators we can hand it: the section it sits in, and what is around it.

Alternative considered: include each candidate's bounding-box position. Rejected — coordinates are L4 territory; introducing them at L3 muddies the tier boundary and bloats the prompt.

### Selector synthesis: `>> nth=N` over the L1 role-name selector

The chosen candidate's selector is:

```
role={role}[name="{escaped name}" i] >> nth={index}
```

`>> nth=N` is documented Playwright locator syntax. `page.locator(selector)` re-resolves to the same single element (assuming the page has not changed between candidate enumeration and re-querying — but at this point we are inside the same tick of the loop, so it has not).

Alternative considered: compute a CSS path / XPath for the chosen candidate via `page.evaluate`. Rejected — those are fragile under drift and the cache (ticket #7) is exactly the system that needs to *not* break under drift. The role+name+nth form is stable for as long as the page exposes the same set of N like-named affordances in the same DOM order, which is the contract the cache will rely on.

If the page changes such that the candidate order shifts, the cache (ticket #7) will revalidate via `ax_fingerprint`; that is the right layer to handle drift, not L3.

### `ax_fingerprint`: hash of `role + name + section_heading`

```
fingerprint = sha256(f"{role}:{name}:{section_heading}".encode()).hexdigest()
```

Reason: the disambiguating signal that distinguishes one "Save" button from another is the section it lives in. Two L3 hits on different runs that both pick the "Settings/Save" candidate must produce the same fingerprint so the cache (ticket #7) treats them as the same element. Two hits that pick different sections must produce different fingerprints.

We deliberately do *not* hash the chosen candidate's DOM path or class names. That is the L2 lesson restated: the entire point of the cache is to survive cosmetic CSS/DOM changes.

Alternative considered: hash the candidate index too. Rejected — index is exactly the DOM-path-y signal we want the cache to be robust against. If "Settings" gets reordered above "Profile" tomorrow, the cache should still recognise "the Save in Settings" as the same target.

Edge case: two candidates with identical section heading. Their fingerprints collide. We accept this — the LLM picked one of them, and from the cache's standpoint they really are interchangeable for the purpose of "click whichever Save is in Settings." If the page genuinely has two Save buttons in the same section with the same surrounding text, the user task is under-specified and falling back to ambiguous via the cache miss (when it later resolves to a different one) is the correct behaviour.

### Orchestrator: forward `llm_chat` through, do not import `agent.llm` at module top-level

```python
def locate(page, intent, *, llm_chat=None):
    role, name = parse_intent(intent)
    try:
        return locate_l1(page, role=role, name=name)
    except LocatorMiss as miss:
        if miss.reason == "zero_matches":
            return locate_l2(page, role=role, name=name)
        if miss.reason == "ambiguous":
            return locate_l3(page, role=role, name=name, llm_chat=llm_chat)
        raise
```

Inside `locate_l3`, the default-resolution of `llm_chat` happens lazily so that `import agent.locate` does not pull in `httpx` / `agent.llm` at module load time:

```python
def locate_l3(page, *, role, name, llm_chat=None):
    if llm_chat is None:
        from agent.llm import chat as llm_chat
    ...
```

This matters for two reasons:
1. Tests that exercise L1 / L2 only should never need `agent.llm` on the import path. (Ticket #4 already passes; this change should not regress it.)
2. The locator cache (ticket #7) will import `agent.locate` from a SQLite-only context where `agent.llm` may not be needed at all.

Alternative considered: a module-level `_default_llm_chat = agent.llm.chat`. Rejected — same import-cost concern.

### `LocatorMiss(reason="ambiguous")` on bad LLM output

When the LLM reply is unparseable or the index is out of range, `locate_l3` raises `LocatorMiss(reason="ambiguous", match_count=N)`. Reason: from the supervisor's standpoint, "the LLM could not pick" is structurally the same kind of failure as "L1 had too many matches" — the system needs an out-of-band recovery (overlay sweep, replan, escalate to L4). Reusing `ambiguous` keeps the supervisor's classification table small. We do *not* introduce a new `LocatorMissReason` value at this stage; ticket #8 (supervisor) is the right place to decide whether `"llm_unparseable"` deserves its own classification.

Alternative considered: raise a brand-new `LLMRerankError`. Rejected — supervisor would need to learn yet another exception type; the ticket scope does not require it.

### Module organization: keep L3 in `locate.py`

Same call as L1/L2: one file, top-to-bottom. The file grows by ~80 LoC after this change, still well under any reasonable split threshold. The moment an L4 lands the file may warrant splitting; not yet.

### Deterministic LLM call: temperature=0.0, no seed

We call `llm_chat(messages=..., temperature=0.0)` and rely on the local Qwen3.5-27B's near-deterministic behaviour at temperature 0. We do *not* pass a `seed` because (a) the hosted local server may or may not support it, and (b) tests mock the LLM, so seed reproducibility is not a runtime concern for ticket #5. The trace replay contract (ticket #12) records the prompt verbatim, which is what real determinism needs anyway.

## Risks / Trade-offs

- **LLM cost / latency on every L1-ambiguous resolve.** Each call to `locate_l3` triggers one LLM round-trip. On a page with many like-named affordances, repeated invocations within a single agent step compound. → Mitigated by ticket #7's locator cache: a successful L3 result is cached by `(origin, intent)` and on a re-resolve the cache returns the stored selector without re-invoking the LLM. Until ticket #7 lands, this is a known cost trade-off.
- **Local model JSON discipline.** Qwen3.5-27B is decent at structured output but not perfect. A malformed reply degrades to `LocatorMiss(reason="ambiguous")`, which the agent loop sees as "L3 could not disambiguate either" and (eventually, ticket #8) escalates. The risk is that *every* L3 attempt fails on a particular phrasing of the prompt. → The prompt is intentionally tiny ("which index best matches?"); we will measure failure rate via the eval set (ticket #15) and tighten the prompt or add a `tools` constrained variant if needed.
- **`>> nth=N` selector is stable only within a tick.** If the page DOM mutates between candidate enumeration and selector re-resolution, the index may shift. → In practice the L3 path runs synchronously inside one Playwright call sequence with no awaited navigation between `count()` and the eventual `page.locator(selector)`. Documented as a precondition: callers that store the selector for later use must accept that the page can change underneath it (which is exactly what the cache's `ax_fingerprint` revalidation handles).
- **Confidence=0.8 is a magic number.** Same caveat as L2's `0.7`. The literal value is not load-bearing; the *ordering* (L1 > L3 > L2 > future L4) is. Documented in the spec.
- **Section-heading extraction can return empty strings on flat pages.** A page with three "Save" buttons and no surrounding `<section>` / heading structure produces three identical empty section headings. The LLM has nothing to pick on; the rerank degenerates to "guess." → The result is still deterministic given the model, and the run is still valid (we return *some* index). The cache fingerprint will be the same across runs (same role+name+empty-section), which is fine — there really is no signal to distinguish them. If that pathology shows up in eval, we revisit by widening the nearby-text window in a later ticket.
- **Cascading inside `locate()` mixes resolution with light recovery.** Same purist objection raised in ticket #4. Same answer: `locate()`'s extension contract is part of the public surface; the supervisor still owns *policy* (when to call again, when to give up, when to overlay-sweep). The tier cascade is a *resolution* concern.
- **Mocking the LLM in tests.** Tests pass `llm_chat=lambda messages, **kw: ChatResponse(content='{"index": 1}', ...)`. This tests the plumbing (prompt assembly, response parsing, selector synthesis, fingerprint). It does *not* test that the real model picks well — that is the eval set's job. We accept this split.
