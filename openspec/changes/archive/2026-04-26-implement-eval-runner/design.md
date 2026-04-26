## Context

Tickets #9–#14 deliver a fully working agent loop with trace persistence and an HTTP API. The eval runner (ticket #15) is the first automated measurement surface: a CLI script that loads YAML case definitions, runs each through `agent.loop.loop()`, and writes a structured results JSON. The runner must stay deterministic in CI (no live network by default), so fixture-backed cases drive the CI gate.

Existing constraints:
- `loop()` is the canonical entrypoint; the runner calls it unchanged.
- LLM configuration comes from env vars (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`); the runner must not hardcode any provider URL.
- `uv run python scripts/eval.py` from `task2/` is the invocation form.
- No comments/docstrings in production code.
- `uv run ruff check .` must be clean.

## Goals / Non-Goals

**Goals:**

- `task2/scripts/eval.py` that accepts `[--live] [--case <id>]` CLI flags, loads `eval/cases/*.yaml`, skips live-only cases when `--live` is absent, runs each remaining case through `loop()`, and writes `eval/results/<ts>.json`.
- YAML case schema: `id`, `domain`, `category`, `task`, `expect` (`schema`, `validators`), `budget` (`steps`, `usd`, `seconds`), and an optional `fixture: true` flag to mark CI-safe cases.
- Results JSON schema: top-level `{ "run_at": "<iso8601>", "cases": [...] }` where each entry has `id`, `status`, `steps`, `usd`, `l_tier_counts` (a dict of tier name → integer hit count extracted from `LocateEvent` records in the trace), and `validators` (a list of `{ "name": ..., "ok": bool }` per declared validator).
- Two toy YAML cases under `task2/eval/cases/`:
  - `fixture-heading.yaml` — fixture-backed (CI-safe), validates that the loop returns a `title` field that is non-empty.
  - `fixture-count.yaml` — fixture-backed (CI-safe), validates that an `items` field is a list with at least 1 element.
- Validator vocabulary (minimal, only what the two cases need): `title.nonempty`, `*.len_gte: N`.
- `pyyaml` added as a runtime dep via `uv add pyyaml`.
- Tests in `task2/tests/test_eval.py`: TDD-first, red before green. The agent loop is patched for unit tests (same pattern as `tests/api/test_server.py`); the case YAML files are loaded from fixture data in the test.

**Non-Goals:**

- Drift suite (ticket #16): fixture v1/v2 pairs — out of scope here.
- Live categories (ticket #17): one per category behind `--live` — out of scope here.
- Full category coverage (≥3 cases each) — only 2 toy cases needed.
- HTML scoreboard output — the README publishes results; that is a separate concern.
- Parallel case execution — sequential is sufficient and simpler to debug.
- Retries or partial-failure recovery within a case run.

## Decisions

### Decision 1: Script location — `task2/scripts/eval.py`, not `task2/eval/eval.py`

The plan states `scripts/eval.py` runs the suite. Placing it at `task2/scripts/eval.py` matches the plan verbatim and separates the runnable script from the data directory (`task2/eval/cases/`, `task2/eval/results/`). Having `eval/eval.py` would be confusing naming and would make `uv run python eval/eval.py` less idiomatic than `uv run python scripts/eval.py`.

**Alternative considered**: `task2/eval/runner.py`. Rejected — inconsistent with `scripts/eval.py` in the plan; scripts/ is the conventional location for CLI entry points.

### Decision 2: L-tier counts extracted from `TraceWriter` events, not from `loop()` return value

`loop()` returns a `RunResult` which does not include L-tier counts (by design — `RunResult` is the task outcome, not telemetry). L-tier counts must be extracted from the `LocateEvent` records in the trace. The runner creates a `TraceWriter` backed by an in-memory (`:memory:`) SQLite for each case run, passes it to a thin wrapper around `loop()`, then queries the events after completion to aggregate `tier` → count from `LocateEvent` records.

**Alternative considered**: extend `RunResult` with `l_tier_counts`. Rejected — changes the loop interface for a caller that is not yet defined (the unit test, ticket #12's contract). The runner must not drive interface changes to loop.py.

**Alternative considered**: parse the results JSON from `GET /tasks/{id}/trace` over HTTP. Rejected — the runner is a standalone CLI, not an HTTP client; adding a server round-trip adds fragility and latency for no gain.

### Decision 3: `TraceWriter` wired into the eval run path via a wrapper function

The runner defines a thin `_run_case(case, llm_client, browser) -> CaseResult` function that opens a `TraceWriter(":memory:")`, constructs an instrumented loop call (or uses the existing `loop()` directly if trace integration is already wired), and returns a `CaseResult` dataclass with `status`, `steps`, `usd`, `l_tier_counts`.

If `loop()` does not currently accept a `TraceWriter` argument (it does not, per the current spec), the runner extracts USD and step counts from `RunResult.totals` if available, or computes steps by counting `DecisionEvent`s in the trace. USD defaults to `0.0` if not tracked in `RunResult` (the loop does not currently track USD per run; this will be tracked as `0.0` until a later ticket wires it).

**Practical implication**: for this toy ticket, `l_tier_counts` will be `{}` (empty dict) in most fixture runs since the fixture cases are designed so L1 always hits. The schema must accept an empty dict; the test asserts the key is present and is a dict (not that it is non-empty).

### Decision 4: Validator vocabulary — two validators only, simple key-path evaluation

The two toy cases need: `title.nonempty` (the `title` key of the result dict must be a non-empty string) and `items.len_gte: 1` (the `items` key must be a list with length ≥ 1). The validator runner parses each string:

- `<key>.nonempty` → `bool(result.get(key, "").strip())`
- `<key>.len_gte: <N>` → `len(result.get(key, [])) >= N`

No other validators are added in this ticket. The grammar is intentionally minimal — it is the smallest vocabulary needed to demonstrate the runner and satisfy the two toy cases.

**Alternative considered**: a full JSONSchema validator (`jsonschema` lib). Rejected — overkill for 2 toy cases; the `expect.schema` field can evolve into full JSONSchema validation in a later ticket without breaking the `validators` list approach used here.

### Decision 5: Results JSON written to `task2/eval/results/<ts>.json` where `<ts>` is `YYYYMMDD_HHMMSS` UTC

Using a timestamp in the filename avoids collisions across runs and matches the `<ts>.json` notation in the plan. UTC avoids timezone ambiguity in CI. `datetime.utcnow().strftime("%Y%m%d_%H%M%S")` produces a sortable, URL-safe filename.

### Decision 6: Test strategy — patch `agent.loop.loop` at the `scripts.eval` import boundary

Tests use `unittest.mock.patch("scripts.eval.loop")` to inject a canned `RunResult` without a real browser or LLM. YAML case data is provided inline (not read from disk) to keep the test isolated from the case files. A separate integration-style test reads from the actual `eval/cases/*.yaml` files to validate their structure.

### Decision 7: `fixture: true` field in YAML marks CI-safe cases; `--live` flag gates live-only cases

Cases without `fixture: true` are skipped when `--live` is absent. This is the pattern described in the plan: "Live cases run behind `--live` so CI stays deterministic." Both toy cases have `fixture: true`, so the full suite runs in CI without a real browser or live network by default (the loop is mocked in unit tests; integration tests use local fixture pages).

## Risks / Trade-offs

- **USD tracking is `0.0` for now**: `loop()` currently does not surface per-run USD in `RunResult`. The `usd` field in the results JSON will be `0.0` until a later ticket wires cost tracking. The schema accepts any float; results are honest about the limitation.
- **L-tier counts are empty for fixture cases**: fixture HTML pages are simple; L1 always resolves. The `l_tier_counts` dict will be `{}` or `{"L1_ax": N}` for toy cases. The spec and test assert presence of the key, not a specific value.
- **`TraceWriter` in-memory per case**: each case run creates a fresh `:memory:` SQLite. There is no persistence of eval run traces. Persisting eval traces is a later concern (ticket #18 Dockerfile + Zeabur context).
- **Sequential execution**: running cases one-by-one is slow for large suites. Acceptable at 2 cases; parallelism is a ticket-#17 concern.
- **`scripts/` is not a Python package** (no `__init__.py` needed for a script invoked via `uv run python scripts/eval.py`), but tests need to import from it. The test will invoke the script via `subprocess` or by importing the module directly after adding `task2/` to `sys.path`. The preferred approach is to make `scripts/` a package with `__init__.py` so tests can `from scripts.eval import run_suite` directly.
