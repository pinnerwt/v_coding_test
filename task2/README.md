# Task 2 — Generalized Browser Automation Agent

## Benchmarks

The agent is exercised by two benchmark suites. The **basic benchmark** is a synthetic, fixture-backed suite that covers the agent's mechanism contracts (locate ladder, cache invalidation, supervisor halt/replan). It runs offline against bundled HTML fixtures and is the inner loop for development. The **WebVoyager benchmark** runs a curated subset of [WebVoyager](https://arxiv.org/abs/2401.13919) tasks against the live web and is the outer-loop signal for "does the agent generalize to a random task on a real site." Both write per-branch artifacts under `benchmark/<branch>/` and feed the trend charts.

<!-- TRENDS:BEGIN -->
### Basic benchmark

![Pass rate over time](benchmark/_trends/pass_rate.svg)

![Latency by status (p50 solid, p95 dashed)](benchmark/_trends/latency.svg)

![Cost by status](benchmark/_trends/cost.svg)

![Failure classes over time](benchmark/_trends/failure_classes.svg)

Cost and latency are split into passed vs. failed cases: a failing case bails out early, so a higher pass rate naturally raises totals. Compare the green (passed) and red (failed) series within a branch, not the totals across branches.

#### Latest run — `task2-implement-loop-type-tool` (2026-04-28 11:48 UTC)

| Case | Status | Steps | Latency | Tokens | USD |
|---|---|---:|---:|---:|---:|
| `canary-read-h1` | succeeded | 3 | 30.4 s | 4,894 | $0.0058 |
| `correction-l1-miss-l2-hit` | succeeded | 4 | 21.3 s | 6,289 | $0.0069 |
| `correction-replan` | succeeded | 3 | 21.4 s | 4,669 | $0.0053 |
| `drift-submit-form-v1` | succeeded | 2 | 14.7 s | 2,852 | $0.0033 |
| `drift-submit-form-v2` | succeeded | 4 | 21.9 s | 6,341 | $0.0070 |
| `fixture-count` | succeeded | 3 | 24.5 s | 4,790 | $0.0055 |
| `fixture-heading` | succeeded | 3 | 27.7 s | 4,753 | $0.0056 |
| `maintenance-drift-rename-v1` | succeeded | 2 | 16.2 s | 2,896 | $0.0034 |
| `maintenance-drift-rename-v2` | succeeded | 2 | 18.4 s | 2,985 | $0.0036 |
| **Total (9 cases, 9 passed)** | | 26 | 196.3 s | 40,469 | $0.0463 |
<!-- TRENDS:END -->

### WebVoyager benchmark (live web)

WebVoyager tasks are real-world web navigation prompts (e.g. "Navigate to wikipedia.org and find the 2018 Turing Award winners") originally published by [He et al., 2024](https://arxiv.org/abs/2401.13919) under CC BY 4.0. We vendor a curated subset under `eval/bench/data/webvoyager/`, biased toward sites that are stable, popup-free, and load fast (Wikipedia, arXiv, GitHub, HuggingFace, BBC News, Cambridge Dictionary, Wolfram Alpha) so the suite stays cheap enough to run on every branch. Sites known to gate behind login, captcha, or aggressive bot detection (Booking, Flights, Amazon, Allrecipes, Apple, Coursera) are deliberately excluded.

Run the live suite from `task2/`:

```bash
LLM_BASE_URL=http://localhost:8090 LLM_MODEL=qwen3.5-27b \
  uv run python -m scripts.bench --suite webvoyager --live
```

Live results land under `eval/results/` (configurable via `EVAL_RESULTS_DIR`). The trend charts above only reflect the basic benchmark today; WebVoyager is tracked separately while the suite stabilizes.

#### Tier-0 baseline (3 tasks, 2026-04-28)

| Case | Site | Status | Steps | Latency | USD |
|---|---|---|---:|---:|---:|
| `webvoyager-1` | Wikipedia | failed (`tool_error`: `LLMError('http 400')` at step 0) | 0 | 0.0 s | $0.0000 |
| `webvoyager-2` | arXiv | succeeded | 9 | 92.9 s | $0.1146 |
| `webvoyager-3` | GitHub | succeeded | 6 | 51.9 s | $0.0405 |

2/3 passed. Per-passing-task cost ≈ $0.08, latency ≈ 50–90 s. The Wikipedia failure is a `LLMError('http 400')` from the Qwen endpoint at step 0 (zero tokens billed) — likely transient endpoint state, not an agent bug. Persisted at `benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json` for reference.

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
