# Task 2 — Generalized Browser Automation Agent

<!-- TRENDS:BEGIN -->
## Benchmark trends

![Pass rate over time](benchmark/_trends/pass_rate.svg)

![Latency by status (p50 solid, p95 dashed)](benchmark/_trends/latency.svg)

![Cost by status](benchmark/_trends/cost.svg)

![Failure classes over time](benchmark/_trends/failure_classes.svg)

Cost and latency are split into passed vs. failed cases: a failing case bails out early, so a higher pass rate naturally raises totals. Compare the green (passed) and red (failed) series within a branch, not the totals across branches.

### Latest run — `task2-implement-failure-clustering-histogram` (2026-04-28 07:16 UTC)

| Case | Status | Steps | Latency | Tokens | USD |
|---|---|---:|---:|---:|---:|
| `canary-read-h1` | succeeded | 3 | 27.8 s | 4,299 | $0.0052 |
| `correction-l1-miss-l2-hit` | failed | 2 | 23.6 s | 2,745 | $0.0035 |
| `correction-replan` | succeeded | 2 | 19.4 s | 2,656 | $0.0033 |
| `drift-submit-form-v1` | failed | 2 | 26.7 s | 2,868 | $0.0037 |
| `drift-submit-form-v2` | failed | 2 | 26.5 s | 2,863 | $0.0037 |
| `fixture-count` | failed | 0 | 0 ms | 0 | $0.0000 |
| `fixture-heading` | succeeded | 3 | 26.3 s | 4,182 | $0.0050 |
| `maintenance-drift-rename-v1` | failed | 2 | 20.6 s | 2,648 | $0.0033 |
| `maintenance-drift-rename-v2` | failed | 2 | 20.2 s | 2,648 | $0.0033 |
| **Total (9 cases, 3 passed)** | | 18 | 191.2 s | 24,909 | $0.0309 |
<!-- TRENDS:END -->


See `plan.md` for the full design. This README is the operator's guide.

## Setup

```bash
cd task2
uv sync
uv run playwright install chromium
```

`playwright install chromium` is a one-time post-`uv sync` step — Playwright wheels do not ship the browser binary, and `uv` does not run post-install hooks.

## Running tests

```bash
uv run pytest
```

## Lint / format

```bash
uv run ruff check .
uv run ruff format .
```

## Deployment

### Docker (local)

```bash
docker build -t vici-task2 task2/

docker run -p 8000:8000 \
  -e LLM_BASE_URL=<openai-compatible-base-url> \
  -e LLM_MODEL=<model-name> \
  -e LLM_API_KEY=<optional-api-key> \
  vici-task2
```

For persistent SQLite storage across restarts, mount a host directory:

```bash
docker run -p 8000:8000 \
  -e LLM_BASE_URL=<openai-compatible-base-url> \
  -e LLM_MODEL=<model-name> \
  -e DB_PATH=/data/vici.db \
  -v /host/path:/data \
  vici-task2
```

### Zeabur

Live URL: `<TBD: Zeabur URL after deployment>`

Connect this repo on the Zeabur dashboard, set the build root to the repo root (the `task2/zeabur.json` file points Zeabur to `task2/Dockerfile`), then set these environment variables:

- `LLM_BASE_URL` — reachable OpenAI-compatible API endpoint
- `LLM_MODEL` — model name to use
- `LLM_API_KEY` — API key (optional, omit for key-free endpoints)
- `DB_PATH` — path inside the container for the SQLite DB (default `/tmp/vici.db`; set to a mounted volume path for persistence)

## Configuration

Environment variables consumed by the LLM client (see `agent/llm.py`):

- `LLM_BASE_URL` — defaults to `http://localhost:8090`
- `LLM_MODEL` — required (no default)
- `LLM_API_KEY` — optional, forwarded as `Authorization: Bearer ...`

## Self-correction & self-maintenance — measured

Three eval cases in `eval/cases/` exercise the agent's self-correction and self-maintenance mechanisms end-to-end:

- `correction-l1-miss-l2-hit` — forces the L1→L2 escalation path: the fixture page (`tests/fixtures/correction_l1_miss.html`) has a `<div class="btn">Submit</div>` with no ARIA role, so L1 (`get_by_role`) returns zero matches and the Supervisor escalates to L2 (CSS taxonomy selector). The `CaseResult.escalations` field must be non-empty.

- `correction-replan` — forces the supervisor-halt → one-shot replan path: the fixture page (`tests/fixtures/correction_replan_deadend.html`) has only a heading and no actionable elements, causing repeated locate misses that exhaust the supervisor's attempts, triggering `halt` and then `plan_module.replan()`. The eval test mocks `loop()` to emit a `PlanEvent(reason="replan")` to the trace writer. `CaseResult.replans` must equal 1.

- `maintenance-drift-rename` (variants `v1`, `v2`, `shared_cache: true`) — forces cache invalidation: v1 caches a selector for `<button>Submit</button>`, then v2 presents `<button>Send</button>`. The warm cache entry's AX fingerprint (accessible name "Submit") differs from the live element ("Send"), so `locate()` calls `cache.invalidate()` and falls through to the L1–L4 ladder. `CaseResult.cache_events["invalidations"]` for v2 must be ≥ 1.

Per-case `Escalations`, `Replans`, and `Cache Inv.` columns appear in the scoreboard (see `<!-- SCOREBOARD:BEGIN -->` below) alongside a "Mechanism firing rates" block.

### Known gaps

- Single replan budget: the supervisor fires replan at most once per run (`replan_used` flag). A multi-replan budget is out of scope for this ticket.
- `to_tier` heuristic within a step: `from_tier` is exact (resolved via `trigger_event_seq`); `to_tier` is the first `LocateEvent(outcome="hit")` scoped to the supervisor's `step_id`, so two escalations within the same step for different intents could in principle overlap (rare — most steps escalate at most one intent).
- Replan path tested via partial mock: the `correction-replan` eval assertion uses a mocked `loop()` that emits a `PlanEvent(reason="replan")` directly. Full end-to-end coverage (with a real LLM call on the deadend fixture) is recorded as a gap.
- Vision tier uncached: `L4_vision` results are intentionally not cached; the `maintenance-drift-rename` case only exercises the AX-fingerprint path.
- No transient-failure retry: the current supervisor handles `LocatorMiss`, `Ambiguous`, and `NoEffect` but does not retry transient browser errors (e.g., network timeouts).
- No post-action assertion: the agent does not verify that a click or type had the intended effect before advancing.
- Coarse AX fingerprint: the fingerprint is built from accessible role + name only; layout or style changes that don't affect the AX tree are invisible to the cache invalidation path.
