## Context

The eval runner (`scripts/eval.py`) and fixture cases (tickets #15 and #16) are complete. The runner already accepts `--live` and already skips non-fixture cases when `--live` is absent — that logic is in `run_suite`: `if not live and not case.get("fixture", False): _skipped_result(case)`. Live cases therefore require no change to the runner's control flow; they only need correctly authored YAML files and tests that verify the gating behavior.

Live sites introduce non-determinism. The design priority is choosing sites that are structurally stable and extracting only coarse facts (titles, counts, snippets) so that minor content drift does not break validators.

Existing constraints:
- No login, no captcha — halted with `blocked` status, not attempted (per plan non-goals).
- `loop()` is the canonical entrypoint; live cases go through it unchanged.
- LLM config from env vars; no hardcoded provider URL.
- No comments/docstrings in production code; `ruff` clean.
- The drift suite (ticket #16) is already complete and covers category 6 — do not duplicate.

## Goals / Non-Goals

**Goals:**

- Five YAML case files under `task2/eval/cases/`, one per category (1 search-and-extract, 1 form-fill, 1 multi-page-nav, 1 conditional-pick, 1 read-and-summarize). Each targets a real public URL, has no login/captcha dependency, and has realistic budgets.
- `task2/tests/test_live_gating.py`: TDD-first tests asserting runner gating (skip without `--live`, include with `--live`). Only the runner's decision logic is under test; browser and loop are mocked.
- `task2/README.md` updated with a "Live eval results" section documenting the last manual run honestly (leaderboard format: site, status, steps used, notes).
- Ruff clean; full fixture test suite still passes after adding the new test module.

**Non-Goals:**

- Running live cases in CI — they are gated behind `--live` specifically to keep CI deterministic.
- Adding a sixth category (drift suite, ticket #16, is already done).
- Achieving a specific pass rate on live cases — results are reported honestly; 60% is the stated goal but the spec does not mandate it.
- Introducing a new runner script, parallel execution, or retry logic.
- Modifying `agent/loop.py`, `agent/browser.py`, or `agent/locate.py` — this ticket is purely additive to the eval layer.

## Decisions

### Decision 1: Use `live: true` field (not a new flag) to identify live cases

The existing runner already skips cases that lack `fixture: true`. Adding `live: true` is a documentation-only convention in the YAML — it does not change the runner's logic at all (the runner checks `case.get("fixture", False)`, not `case.get("live", False)`). The gating tests verify the observed behavior: a case without `fixture: true` is skipped when `live=False`. The `live: true` field makes the intent explicit in the YAML for human readers.

**Alternative considered**: add a `live` flag check to `run_suite` alongside `fixture`. Rejected — the existing logic already does the right thing; adding a second flag check would add code for no behavioral gain and could introduce inconsistency.

### Decision 2: Site choices — low-volatility, login-free, structurally stable

Each category targets a site with stable DOM structure and predictable content:

| Category | Site | URL | Rationale |
|---|---|---|---|
| Search & extract | Wikipedia | `https://en.wikipedia.org/wiki/Python_(programming_language)` | Stable article; extracting the first sentence of the lead paragraph is a coarse validator. |
| Form fill | DuckDuckGo search | `https://duckduckgo.com/` | Public search box; type a query, submit, read the first result title. No login, no captcha. Avoids Google (bot detection). |
| Multi-page nav | Books to Scrape | `https://books.toscrape.com/` | Designed explicitly for scraping practice; pagination is stable and intentional. Navigate to page 2, extract first book title. |
| Conditional pick | Books to Scrape | `https://books.toscrape.com/catalogue/category/books/mystery_3/index.html` | Find the first book with a rating of "Five" stars. Stable category page with explicit star-rating markup. |
| Read & summarize | Python docs | `https://docs.python.org/3/library/pathlib.html` | Official Python docs, long-term stable URL. Task: read the first paragraph of the `pathlib` module description and return it as a summary. |

**Alternative considered for form-fill**: a public form demo site (e.g., `https://httpbin.org/forms/post`). Rejected — httpbin forms are not a realistic browser interaction. DuckDuckGo is a real public search and exercises type + submit + read the result.

**Alternative considered for conditional pick**: HackerNews "Ask HN" filtered by points. Rejected — HN content changes frequently and point thresholds shift; extracting a book rating from a static catalogue is more stable.

### Decision 3: Validators are coarse — structural, not content-specific

Live site content changes. Validators check structure (non-empty string, list length) rather than exact values. For example, the Wikipedia case validates `summary.nonempty`, not that the summary contains a specific phrase. This keeps live cases meaningful (the agent returned something) without making them brittle to content updates.

### Decision 4: Budget sizing — generous, not tight

Live cases on a local Qwen3.5 27B are slower than hosted frontier models. Budgets are set generously (20–30 steps, $0.25–$0.50, 120 seconds) to avoid false `timeout` failures due to model speed rather than agent failure. These numbers can be tightened after observing actual run times.

### Decision 5: Test scope — gating only, no real-network tests

The test module (`test_live_gating.py`) patches `scripts.eval.loop` (same pattern as `test_eval.py`) and asserts runner gating behavior. It does NOT make real HTTP requests or launch a browser. Real-network execution is a manual `--live` concern, not a CI concern. This is the same test boundary used by the drift suite for the variant expansion path.

### Decision 6: README section — leaderboard format, filled after manual run

The spec requires the `task2/README.md` live-results section to exist; its content (actual pass/fail/score per case) is a documentation deliverable filled in manually after the first `uv run python scripts/eval.py --live` run. The spec requires the section header to be present and the format to follow the leaderboard pattern (table with site, status, steps, notes columns) rather than a claim of "all pass."

## Risks / Trade-offs

- **DuckDuckGo bot detection** → DuckDuckGo generally allows headless Playwright; if it breaks, the fallback is `https://www.ecosia.org/` (same structure). Called out in the case YAML as a comment (no — wait, no comments in non-test code; site choice is documented here in design.md).
- **Books to Scrape pagination stability** → The site is maintained specifically as a scraping demo; URL structure is unlikely to change. Low risk.
- **Python docs restructuring** → `docs.python.org/3/library/pathlib.html` has been stable for years. Low risk.
- **Qwen3.5 27B step budget** → The 20-step budget may be tight for multi-page nav on a slow local model. Mitigation: budget is set to 30 steps for the multi-page case.
- **Live cases slow CI if accidentally included** → The gating tests verify that `live=False` produces `status == "skipped"` for live cases. If the gating logic regresses, the gating tests fail before any slow network call happens.

## Open Questions

- None blocking. The site choices are decided; if a site becomes unreachable before the first manual run, fall back to the alternatives documented above.
