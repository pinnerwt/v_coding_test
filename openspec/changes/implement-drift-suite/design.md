## Context

Tickets #1–#15 deliver a working locator pipeline (L1 AX → L2 DOM → L3 LLM rerank → L4 vision), locator cache, agent loop, and eval runner. The plan's done bar requires the drift suite at 100%: the same NL task must pass two fixture variants that share semantics but differ in selector markup. This ticket introduces the fixtures, the eval case, the variant-expansion logic in the eval runner, and the Playwright-backed tier-assertion tests.

Current state of relevant code:
- `agent/locate.py` — `locate()` with the full L1→L4 ladder is complete and tested; no changes needed for this ticket.
- `scripts/eval.py` — runs YAML cases, calls `loop()`, writes results JSON; the `variants` field is not yet known to it.
- `tests/conftest.py` — `fixture_server` (session-scoped) serves files from `tests/fixtures/` on a random HTTP port; `fixture_server_factory` provides function-scoped multi-origin servers.
- `eval/cases/` — two YAML files (`fixture-heading.yaml`, `fixture-count.yaml`); both have `fixture: true`; neither has a `variants` field.

Constraints:
- No LLM provider hardcoding. The drift tests that use `locate()` directly will stub the LLM for L3/L4; the eval-suite assertion path mocks `loop()`.
- TDD non-negotiable: tests are written in red state before any production code changes.
- No comments/docstrings in production code (`scripts/eval.py`).
- `uv run ruff check .` must be clean.

## Goals / Non-Goals

**Goals:**

- Two static HTML fixtures: `v1` (standard semantic markup, L1 resolves) and `v2` (accessible name stripped from the button so L1 misses; L2 resolves via text-contains). Same semantic task on both: "Click the submit button and return submitted".
- One eval YAML case `drift-submit-form.yaml` with `category: drift`, `fixture: true`, `variants: [v1, v2]`. The runner expands it to two sub-runs whose IDs are `drift-submit-form-v1` and `drift-submit-form-v2`.
- Eval runner `scripts/eval.py` updated to handle `variants`: when the field is present, produce one `CaseResult` per variant (with sub-IDs), serving the variant's fixture HTML via the existing fixture server.
- `tests/test_drift.py` with two categories of tests:
  1. **Tier assertions** (Playwright-backed, not mocked): `locate(page, "Submit button")` on v1 returns `tier=="L1_ax"`; on v2 it returns `tier=="L2_dom"`. These are the deterministic proof that the ladder is doing its job.
  2. **Eval-suite assertion** (loop mocked): `run_suite` with the drift YAML case expands to two results, both `status=="succeeded"`.
- `tests/test_eval.py` extended with one new test covering the variant-expansion path.

**Non-Goals:**

- Modifying `agent/locate.py`, `agent/loop.py`, `agent/browser.py`, or any other agent module — the point of the drift suite is that no code changes are needed.
- A third fixture variant or v3+.
- Tier assertions for L3/L4 (not needed; the locator ladder fallthrough to L2 is sufficient to prove self-maintenance at the selector-drift level).
- Storing or replaying drift-run traces — trace correctness is ticket #12's concern.
- HTML form submission wired to a backend — the fixture form is static; the agent reads the page, "submits" by calling `done()`.

## Decisions

### Decision 1: Fixture design — v1 uses `<button>Submit</button>`, v2 strips the accessible name

v1 has a canonical `<button>Submit</button>` element. L1 matches it directly via `page.get_by_role("button", name="Submit", exact=False)` — one match, confidence 1.0, tier `L1_ax`.

v2 replaces the button with `<div class="btn" onclick="void(0)">Submit</div>`. This element has no ARIA role, so L1 queries `role=button` and finds zero results (`zero_matches`). L1 raises `LocatorMiss(reason="zero_matches")`. `locate()` falls to L2, which runs the button taxonomy CSS (`[class*="btn"]`) filtered by `has_text="Submit"` — one match, confidence 0.7, tier `L2_dom`.

This choice exercises exactly the L1→L2 fallthrough the plan cites as the self-maintenance mechanism. It does not need an LLM call (no L3/L4), making the test fully deterministic without mocking the LLM at the locate layer.

Alternative considered: use `aria-label` renaming (v1 has `aria-label="Submit"`, v2 has `aria-label="Send"`). Rejected — both variants would resolve at L1 (different accessible names, still AX-accessible). That tests a different failure mode (name drift, not tier drift) and does not exercise the L1→L2 fallthrough.

Alternative considered: use `id`/`class` only as the drift axis (v1 has `id="submit-btn"`, v2 does not). Rejected — neither L1 nor L2 uses `id` directly; the drift would be invisible to the locator pipeline.

### Decision 2: Variant expansion in `scripts/eval.py` — inline, no new abstraction

When `load_cases` reads a YAML file, it already returns a list of dicts. When a case dict has a `variants` key (a list of strings), `run_suite` expands it: for each variant `v` it produces a shallow copy of the case dict with `id` replaced by `<case-id>-<v>` and a new key `_variant` set to `v`. The `_run_case` function reads `_variant` to determine which fixture file to load (by constructing the URL `<fixture_base>/drift/<original-id>/<variant>/index.html`).

The fixture base URL is passed into `run_suite` via a new keyword arg `fixture_base_url: str | None = None`. When `None`, the runner falls back to an env var `FIXTURE_BASE_URL`; when that is also absent it defaults to `""` (relative path, functional only in tests where the browser navigates local files directly). In production the eval runner starts the fixture server itself, as the conftest already does.

Alternative considered: a pre-processing step in `load_cases` that expands variants before returning. Rejected — `load_cases` is tested independently; changing its output shape breaks test isolation. Expansion is a runner concern, not a loader concern.

Alternative considered: a separate `load_drift_cases` function. Rejected — adds a second entry point for the same YAML format; YAGNI.

### Decision 3: Test strategy — separate `test_drift.py`, Playwright-backed tier assertions

The tier assertions require a real Playwright page and the real `locate()` function — mocking either would not actually prove the locator ladder works on the fixture HTML. These tests use the `playwright_chromium` and `fixture_server` session-scoped fixtures from `conftest.py`, navigate to each variant's HTML, and call `locate(page, "Submit button")` directly (no `loop()`, no LLM needed for L1/L2).

The eval-suite assertions use `patch("scripts.eval.loop")` exactly as `test_eval.py` does today — the drift YAML is loaded from disk (`eval/cases/drift-submit-form.yaml`), two canned `RunResult` objects are injected (one per variant), and the results JSON is checked for two entries both with `status=="succeeded"`.

### Decision 4: Fixture HTML path — `tests/fixtures/drift/<case-id>/<variant>/index.html`

The existing `fixture_server` serves all files from `tests/fixtures/` with their relative path intact. Placing drift fixtures at `tests/fixtures/drift/submit-form/v1/index.html` means the variant is reachable at `<fixture_server_url>/drift/submit-form/v1/index.html`. The eval runner constructs this URL from the case id and variant string: `f"{fixture_base_url}/drift/{orig_id}/{variant}/index.html"`.

Alternative considered: placing fixtures directly under `eval/fixtures/drift/<case>/<variant>/`. The plan mentions this path (ticket description), but the existing conftest fixture server only serves from `tests/fixtures/`. Using `tests/fixtures/` avoids introducing a second static-file server or changing the conftest, which keeps this ticket strictly additive.

### Decision 5: `category: drift` in YAML is informational only; the runner does not branch on it

The `category` field is already free-form in the existing cases (`"search-and-extract"`, `"read-and-summarize"`). Adding `drift` as a value costs nothing. The runner does not need to treat it specially — variant expansion is driven by the presence of the `variants` key, not the category value. The `--live` gating is still driven by `fixture: true`.

## Risks / Trade-offs

- **Fixture server URL construction is hardcoded to the `drift/<id>/<variant>/index.html` pattern.** If a future drift case needs a different HTML filename, the runner must be extended. Acceptable for one case; revisit if the drift suite grows.
- **v2's `onclick="void(0)"` does not actually submit the form.** The agent must call `done()` without a real HTTP round-trip. The eval-suite test mocks `loop()` so this is never exercised in CI; the tier-assertion test only calls `locate()`, not `loop()`. If a future ticket drives the full loop against drift fixtures, the HTML will need a real form action or a JS form handler.
- **Session-scoped `fixture_server` means all drift tests share one server instance.** Tests are read-only (no DOM mutation), so sharing is safe. If a future drift test mutates the DOM (like the locator-cache drift test does), it must use `fixture_server_factory` instead.
- **`_variant` is a private key in the case dict.** It is not a declared field in the YAML schema and will not appear in `eval/cases/*.yaml` files. It is injected by the runner at expansion time and consumed by `_run_case`. The underscore prefix signals "runner-internal"; `load_cases` must not validate or reject it.
