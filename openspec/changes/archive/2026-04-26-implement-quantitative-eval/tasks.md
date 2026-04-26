## 1. Pricing module (llm-pricing spec) — RED first

- [x] 1.1 Write failing test `task2/tests/agent/test_pricing.py`: assert `compute_usd(prompt_tokens=2000, completion_tokens=500, model="qwen3", price_table=<synthetic dict>)` returns `0.007`; assert unknown model falls back to `[default]`; assert `load_price_table(path=<fixture toml>)` returns expected dict shape.
- [x] 1.2 Create `task2/agent/pricing.py` with `compute_usd(prompt_tokens, completion_tokens, model, price_table) -> float` and `load_price_table(path=None) -> dict` using `tomllib` (stdlib, Python 3.11+). Make 1.1 tests pass.
- [x] 1.3 Create `task2/config/pricing.toml` with a `[default]` section (`prompt_per_1k = 0.001`, `completion_per_1k = 0.002`) and a `[models.qwen3]` section (`prompt_per_1k = 0.002`, `completion_per_1k = 0.006`). No provider-specific float literals in any `.py` file.
- [x] 1.4 Write failing test asserting no hardcoded rate literals exist in `.py` files under `task2/` (scan source, exclude test fixture dicts and the TOML file itself). Make it pass trivially since rates live only in TOML.
- [x] 1.5 Run `uv run ruff check . && uv run ruff format .` from `task2/`; fix any issues.

## 2. LLMClient gains usd field (llm-client delta spec) — RED first

- [x] 2.1 Write failing test in `task2/tests/agent/test_llm.py`: mock HTTP response with `usage.prompt_tokens=1000, completion_tokens=500`; assert `ChatResponse.usd == 0.005` when `LLMClient` is constructed with `price_table={"models": {"qwen3.5": {"prompt_per_1k": 0.002, "completion_per_1k": 0.006}}, "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002}}` and `model="qwen3.5"`.
- [x] 2.2 Add `usd: float` to `ChatResponse` dataclass in `task2/agent/llm.py`.
- [x] 2.3 Add `price_table: dict | None = None` parameter to `LLMClient.__init__`; lazy-load from `task2/config/pricing.toml` when `None`; call `compute_usd` in `_parse_response`/`chat` and set `ChatResponse.usd`. Make 2.1 pass.
- [x] 2.4 Run `uv run ruff check . && uv run ruff format .`; run `uv run pytest task2/tests/agent/test_llm.py` — all green.

## 3. RunResult metrics (agent-loop delta spec) — RED first

- [x] 3.1 Write failing test in `task2/tests/agent/test_loop.py`: synthetic 2-step run (mocked `LLMClient` returning `goto` on step 1 with `usage(prompt=100, completion=10)` and `usd=0.00022`, then `done` on step 2 with `usage(prompt=150, completion=20)` and `usd=0.00034`). Assert `result.steps == 2`, `result.prompt_tokens == 250`, `result.completion_tokens == 30`, `result.usd ≈ 0.00056`, `result.latency_ms_total > 0`, `len(result.latency_ms_per_step) == 2`, `len(result.step_breakdown) == 2`.
- [x] 3.2 Write failing test: `timeout` path (mocked LLM never calls `done`/`fail`, `max_steps=2`) — assert `result.status == "timeout"`, `result.steps == 2`, `len(result.latency_ms_per_step) == 2`.
- [x] 3.3 Write failing test: `step_breakdown[0]` has all required keys (`step`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls`).
- [x] 3.4 Extend `RunResult` dataclass in `task2/agent/loop.py` with new fields (all with `field(default_factory=...)` or scalar defaults so existing callers compile). Keep `frozen=True`.
- [x] 3.5 Add step-level timing (`time.monotonic()` before observation, after dispatch) and accumulation of tokens/USD in `loop()`. Build `step_breakdown` list and return updated `RunResult`. Make 3.1–3.3 pass.
- [x] 3.6 Run full `uv run pytest task2/tests/agent/test_loop.py` — all green including pre-existing tests.
- [x] 3.7 Run `uv run ruff check . && uv run ruff format .`.

## 4. CaseResult metrics and _run_case wiring (eval-metrics spec) — RED first

- [x] 4.1 Write failing test in `task2/tests/test_eval.py`: mock `loop()` to return a `RunResult` with `steps=3, prompt_tokens=400, completion_tokens=60, usd=0.0009, latency_ms_total=1200, latency_ms_per_step=[400,400,400], step_breakdown=[...]`; assert `_run_case` returns `CaseResult` with matching non-zero values.
- [x] 4.2 Write failing test: `CaseResult` with `prompt_tokens=100, latency_ms_per_step=[200,300]` serialises to JSON with those keys present.
- [x] 4.3 Extend `CaseResult` dataclass in `task2/scripts/eval.py` with new fields (`prompt_tokens`, `completion_tokens`, `latency_ms_total`, `latency_ms_per_step`, `step_breakdown`), all with zero/empty defaults.
- [x] 4.4 Wire `_run_case` to populate new `CaseResult` fields from `RunResult`. Make 4.1 and 4.2 pass.
- [x] 4.5 Run `uv run pytest task2/tests/test_eval.py` — all green.
- [x] 4.6 Run `uv run ruff check . && uv run ruff format .`.

## 5. score.py (score-script spec) — RED first

- [x] 5.1 Create vendored fixture `task2/tests/fixtures/results/sample_results.json` with two cases (one `succeeded` with `latency_ms_total=400, steps=2, prompt_tokens=200, completion_tokens=30, usd=0.0005, latency_ms_per_step=[200,200], step_breakdown=[...]`, one `failed` with `latency_ms_total=800, steps=1`). Add a golden snapshot `task2/tests/fixtures/results/sample_results_scoreboard.md` with the expected output (leave as TODO placeholder; fill after implementing score.py by capturing its output).
- [x] 5.2 Write failing test `task2/tests/test_score.py`: call `score.py` as a subprocess or import its `generate_scoreboard(data: dict) -> str` function; assert output contains `| ` (table row), `succeeded`, `p50:`, `Total USD:`, `| Tier |`.
- [x] 5.3 Write failing test: p50/p95 computation correctness with `latency_ms_total` values `[100, 200, 800]` → p50=200, p95=800.
- [x] 5.4 Write failing test: golden snapshot match (stub — initially expected to fail until 5.5 produces stable output, then capture and vendor the snapshot).
- [x] 5.5 Implement `task2/scripts/score.py`: `generate_scoreboard(data) -> str` function; `main(argv)` with argument parsing (`results_file` positional, `--update-readme`, `--readme-path`, `--output`). Emit per-case table, summary line, p50/p95, totals, tier-mix table.
- [x] 5.6 Capture actual `score.py` output for the fixture file; write it to `task2/tests/fixtures/results/sample_results_scoreboard.md`. Re-run golden snapshot test — it should now pass.
- [x] 5.7 Write failing test for `--update-readme`: create a temp README with sentinels; run `score.py --update-readme`; assert sentinels still present and content between them matches `generate_scoreboard()` output. Also assert idempotency (run twice, content identical).
- [x] 5.8 Implement `--update-readme` splice logic in `score.py`. Make 5.7 pass.
- [x] 5.9 Run `uv run pytest task2/tests/test_score.py` — all green.
- [x] 5.10 Run `uv run ruff check . && uv run ruff format .`.

## 6. /score slash skill (score-skill spec)

- [x] 6.1 Write failing test in `task2/tests/test_score.py` (or a separate `test_skill.py`): assert `.claude/commands/score.md` exists at the repo root and contains `uv run python scripts/score.py`.
- [x] 6.2 Create `.claude/commands/score.md` as a thin skill that runs `uv run python scripts/score.py` from `task2/` with the user-supplied argument (path or `--latest`). No scoring logic in the file. Under 30 lines total. Make 6.1 pass.

## 7. README scoreboard regeneration

- [x] 7.1 Add `<!-- SCOREBOARD:BEGIN -->` and `<!-- SCOREBOARD:END -->` sentinel comments to `task2/README.md` around the existing "Live eval results" table section.
- [x] 7.2 Run `uv run python scripts/score.py eval/results/<latest>.json --update-readme` from `task2/`; verify the README scoreboard section is updated with real metrics (non-zero `steps`, `usd`).
- [x] 7.3 Commit the regenerated README (content between sentinels updated by `score.py`, not by hand).

## 8. End-to-end sanity and integration

- [x] 8.1 Run the full test suite: `uv run pytest` from `task2/`. All tests green.
- [x] 8.2 Run `uv run ruff check .` from `task2/` — zero warnings.
- [x] 8.3 Run `uv run python -m scripts.eval --case fixture-heading` (fixture only) and confirm the printed output shows non-zero `steps` and `$` values. (Requires live LLM at localhost:8090 — skipped in CI; unit tests cover this path.)
- [x] 8.4 Run `uv run python scripts/score.py eval/results/<latest>.json` and verify scoreboard markdown is emitted to stdout with correct structure.
