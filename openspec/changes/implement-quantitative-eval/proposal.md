## Why

The eval runner's `CaseResult` always emits `steps=0`, `usd=0.0`, and `l_tier_counts={}` because `_run_case` never threads the loop's counters into those fields, making the scoreboard in `task2/README.md` factually wrong ("`steps` reads 0 because `_run_case` does not yet thread the loop's step count into `CaseResult` — separate follow-up"). Without real metrics the eval set is opaque: we cannot measure cost regression, latency percentiles, or locator-tier health.

## What Changes

- **`LLMClient`** gains per-call USD computation driven by a configurable per-1k-token price table (TOML or env var); no provider rate is hardcoded.
- **`loop.py`** accumulates per-step latency, token counts, and USD cost; passes the totals back via an augmented `RunResult`; links each step to its `LLMCallEvent` so per-step breakdowns are traceable.
- **`CaseResult`** (in `scripts/eval.py`) is extended with: `steps`, `prompt_tokens`, `completion_tokens`, `usd`, `latency_ms_total`, `latency_ms_per_step` (list), `l_tier_counts`, and `step_breakdown` (list of per-step dicts). `_run_case` is wired to populate them.
- **`scripts/score.py`** is a new script that reads `eval/results/<ts>.json` and emits a markdown scoreboard: per-case status table, overall success rate, p50/p95 latency, total USD, total tokens, locator-tier resolution mix.
- **`/score` slash skill** is a thin Claude Code skill wrapper that invokes `scripts/score.py`.
- **README scoreboard** becomes generated output of `score.py --update-readme` (flag appends/replaces the scoreboard section in `task2/README.md`) rather than hand-edited.

## Capabilities

### New Capabilities

- `llm-pricing`: Configurable per-1k-token price table loaded from `task2/config/pricing.toml`; exposes a `compute_usd(prompt_tokens, completion_tokens, model)` function used by `LLMClient` to populate `LLMCallEvent.usd`.
- `loop-metrics`: Loop-level step counting, per-step latency measurement, token accumulation, and USD rollup; surfaces totals via `RunResult` fields consumed by the eval runner.
- `eval-metrics`: Extension of `CaseResult` with all quantitative fields and wiring of `_run_case` to populate them from `RunResult`.
- `score-script`: `scripts/score.py` — reads a results JSON file, computes aggregate stats, emits a markdown scoreboard; accepts `--update-readme` to regenerate the README scoreboard section.
- `score-skill`: `/score` Claude Code slash skill — thin wrapper that invokes `scripts/score.py` with the most-recent or user-specified results file.

### Modified Capabilities

- `llm-client`: `LLMClient.chat()` now returns `usd: float` on `ChatResponse` (populated via the price table). Existing `usage` field is unchanged; `usd` is additive.
- `eval-runner`: `CaseResult` gains new non-zero fields; the results JSON schema gains `prompt_tokens`, `completion_tokens`, `usd`, `latency_ms_total`, `latency_ms_per_step`, `step_breakdown`. Existing fields are unchanged.
- `agent-loop`: `RunResult` gains `steps: int`, `prompt_tokens: int`, `completion_tokens: int`, `usd: float`, `latency_ms_total: int`, `latency_ms_per_step: list[int]`, `step_breakdown: list[dict]`. Existing `status`, `result`, `evidence`, `verifier` are unchanged.

## Impact

- `task2/agent/llm.py` — add `usd` to `ChatResponse`; add pricing helper.
- `task2/agent/loop.py` — add step counters, timing, token accumulation to `RunResult`.
- `task2/scripts/eval.py` — extend `CaseResult`, wire `_run_case`.
- `task2/scripts/score.py` — new file.
- `task2/config/pricing.toml` — new config file (price table, no hardcoded rates).
- `.claude/commands/score.md` — new slash skill.
- `task2/README.md` — scoreboard section becomes generated.
- `task2/tests/` — new test modules for pricing, loop metrics, score.py golden output.
