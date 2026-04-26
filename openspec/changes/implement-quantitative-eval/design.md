## Context

The eval runner (`scripts/eval.py`) runs each case through `loop()`, but `_run_case` hardcodes `steps=0`, `usd=0.0`, `l_tier_counts={}` in the returned `CaseResult`. The loop itself accumulates nothing: it does not count steps, measure wall time per step, or total tokens. `LLMClient.chat()` returns a `ChatResponse` with `usage` (token counts) but no `usd` field. There is no script to aggregate a results JSON into a markdown scoreboard, and the scoreboard in `task2/README.md` is hand-edited.

The change is cross-cutting: it touches `LLMClient`, `loop.py`, `CaseResult`, `scripts/eval.py`, adds `scripts/score.py`, a pricing config file, and a slash skill. Key design decisions concern (a) where the price table lives, (b) how per-step latency is measured, (c) how per-step → `LLMCallEvent` linkage works, and (d) how the README scoreboard is regenerated.

## Goals / Non-Goals

**Goals:**

- `LLMClient.chat()` returns `usd: float` computed from a configurable per-1k-token price table; no rate is hardcoded in Python source.
- `loop()` tracks step count, per-step wall-time, and cumulates tokens/USD; surfaces them via `RunResult` without breaking existing callers.
- `_run_case` threads `RunResult` metrics into `CaseResult`; the results JSON gains the new fields.
- `scripts/score.py` reads any `eval/results/<ts>.json` and emits a markdown scoreboard.
- `--update-readme` flag on `score.py` splices the scoreboard into `task2/README.md`.
- `/score` slash skill is a one-line wrapper that invokes `score.py`.
- TDD: every behavioral change starts with a failing test.

**Non-Goals:**

- Changing the trace schema (`LLMCallEvent.usd` already exists in `trace.py`; we do not restructure it).
- Real Playwright browser integration in new tests — synthetic/stubbed LLM and browser suffice.
- Multi-model price blending within a single run.
- Streaming token counting.

## Decisions

### D1: Price table in `task2/config/pricing.toml`

**Decision**: A TOML file at `task2/config/pricing.toml` holds per-model pricing as `[models.<model-id>]` sections with `prompt_per_1k` and `completion_per_1k` float keys. A `[default]` section acts as a fallback for unknown models.

**Alternatives considered**:
- *Env vars per model* (`PRICE_QWEN3_PROMPT=0.001`): combinatorial explosion for multi-model setups; harder to document and diff.
- *Hardcoded dict in Python*: violates the CLAUDE.md "no hardcoded provider rates" constraint.
- *JSON config*: TOML is more human-readable for float tables and is supported by Python's stdlib `tomllib` (Python 3.11+).

**How it's loaded**: `agent/pricing.py` exposes `load_price_table(path=None)` which reads the TOML (defaulting to `task2/config/pricing.toml` relative to the package root). `LLMClient` accepts an optional `price_table: dict` constructor argument; if absent it lazy-loads from the config file. Tests inject a synthetic dict directly, so no file I/O is required in tests.

### D2: Per-step latency measured in `loop.py` around each full observe→LLM→dispatch cycle

**Decision**: Each iteration of the loop's `for` body is wrapped in `time.monotonic()` calls: `t0 = time.monotonic()` before the observation, `t1 = time.monotonic()` after the dispatch (before looping). `latency_ms_per_step.append(int((t1 - t0) * 1000))`. The `LLMClient.chat()` call contributes its own internal `ms` field (already tracked in `LLMCallEvent`) but the step latency is coarser — it covers observation + LLM call + dispatch — which is what reviewers care about for end-to-end throughput.

**Alternative**: measure only the LLM call time. Rejected because browser tool latency is non-trivial and reviewers want total per-step cost.

### D3: Per-step → LLMCallEvent linkage via `step_breakdown` in `RunResult`

**Decision**: Each step produces a breakdown dict:
```json
{
  "step": 1,
  "latency_ms": 340,
  "prompt_tokens": 512,
  "completion_tokens": 48,
  "usd": 0.00028,
  "tool_calls": ["goto"]
}
```
The loop appends one dict per iteration. `LLMCallEvent.llm_call_id` linkage is implicit: a consumer can match step N's breakdown to the Nth `llm_call` event in the trace by sequence position. Full `llm_call_id` threading into `CaseResult` is deferred (it requires the trace writer in the loop, which is out of scope here).

**Alternative**: embed `llm_call_id` directly in the breakdown. Deferred because the loop does not currently write trace events; adding `TraceWriter` to the loop is ticket 12's concern.

### D4: README scoreboard regenerated via `scripts/score.py --update-readme`

**Decision**: `score.py` accepts an `--update-readme` flag. When set, it splices the generated scoreboard between two sentinel comments in `task2/README.md`:
```html
<!-- SCOREBOARD:BEGIN -->
...generated markdown...
<!-- SCOREBOARD:END -->
```
If the sentinels are absent, `--update-readme` appends the scoreboard as a new `## Live eval results` section. This is deterministic and diff-friendly.

**Alternative**: a `Makefile` target. Rejected because the repo does not use Make and adding it for one purpose is over-engineering. A flag on the existing script is simpler and composable with CI.

**Who calls it**: manually by a developer after a live eval run, or a future CI step. Not called automatically on every test run.

### D5: `usd` field added to `ChatResponse` (additive, not breaking)

**Decision**: `ChatResponse` gains a `usd: float` field. Existing callers that don't use it are unaffected. `LLMClient.chat()` computes it from `usage.prompt_tokens`, `usage.completion_tokens`, and the price table after parsing the response.

## Risks / Trade-offs

- **Price table out of date** → USD estimates diverge from actual spend. Mitigation: TOML is version-controlled; reviewers can update it. The `[default]` fallback emits `usd=0.0` with a logged warning so the system degrades gracefully rather than crashing.
- **Monotonic clock wraps on very long runs** → negligible risk on modern hardware (wrap time > 100 years).
- **`--update-readme` sentinel absent in README** → score.py falls back to appending; idempotent on second run once sentinels are in place.
- **`tomllib` is Python 3.11+ stdlib** → `task2/pyproject.toml` already targets Python 3.11; no new dep needed.
