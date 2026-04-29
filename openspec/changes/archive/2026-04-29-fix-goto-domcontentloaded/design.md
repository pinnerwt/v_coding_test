## Context

WebVoyager-1's per-step latency profile is bimodal: steps 0-9 average ~7s/step, steps 10-19 average ~28s/step. Prompt tokens stay flat after step 10 (history truncation in play), so the slowdown is not LLM-driven. The latency is in browser tool calls — `goto`, `read`, `click` — and the dominant source is `_page.goto(url, wait_until="load")`, which blocks until ALL subresources finish loading. Step 13's `goto` measured 31964ms in the latest run; surrounding read/click steps inherit the same load-state contention because Playwright's implicit waits stall on the same lifecycle.

## Decision

Change `wait_until="load"` to `wait_until="domcontentloaded"` and add an explicit `timeout=15000` (ms) on both call sites in `Browser.goto`. The agent's downstream operations (`_body_text`, AX-tree extraction via `Accessibility.getFullAXTree`) all work as soon as DOMContentLoaded has fired — waiting for `load` is wasted time on content-heavy pages.

The 15s timeout is the hard ceiling for unreachable / slow-DCL pages. It is strictly tighter than Playwright's 30s default, so the only behavior changed for already-fast pages is the wait-until target (which they already satisfy at the same instant).

## Alternatives considered

- **`wait_until="commit"`** (DOM construction not yet started, just navigation committed): too aggressive — `b.read("h1")` would race the parser. DCL is the right floor.
- **Add a swallow-on-timeout `wait_for_load_state("load", timeout=2000)` after DCL goto**: reasonable for SPA hydration cases. Deferred to a follow-up ticket — WebVoyager's Wikipedia / arXiv / GitHub fixtures all read static-DOM content that DCL guarantees, so this is YAGNI for the current acceptance criterion.
- **Make `wait_until` configurable per call**: deferred — there is no caller today that needs a different lifecycle, and adding the knob now would cost a config surface for no benefit.

## Risks

- **SPA hydration**: some pages render their target text only after a post-DCL JS hydration step. For WebVoyager's seed suite (Wikipedia, arXiv, GitHub) this is not a concern. If a future case hits this, add the deferred swallow-on-timeout `wait_for_load_state("load")`.
- **Timing-sensitive test for the 15s timeout path**: the transient-retry path means a worst-case unreachable page makes two DCL attempts + 250ms sleep ≈ 30s. Bound the assertion at 31s (not 16s) to absorb this.
- **Per-test HTTP server**: the new tests must use `daemon=True` threads and shut down cleanly even on test failure. Mirror the `_start_fixture_server` / `_stop_fixture_server` shape from `task2/tests/conftest.py:20-42`.
