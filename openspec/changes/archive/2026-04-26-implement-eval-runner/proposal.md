## Why

The agent loop, trace writer, and API server (tickets #9–#14) are all functional, but there is no automated harness to measure whether the agent actually completes tasks correctly. Ticket #15 introduces the eval runner — a `scripts/eval.py` CLI that loads YAML case definitions, drives the agent loop against them, and writes a structured results JSON. This is the foundation for the scoreboard referenced in the plan and for CI-gated regression detection.

## What Changes

- New directory `task2/eval/cases/` containing two toy YAML case files: one fixture-backed case (deterministic, safe for CI) and one trivially scripted second case.
- New script `task2/scripts/eval.py`: loads `eval/cases/*.yaml`, resolves cases against the `--live` flag, runs each through the existing `agent.loop.loop()`, and writes `eval/results/<ts>.json` with per-case status, step count, USD, and L-tier resolution counts.
- New test file `task2/tests/test_eval.py`: TDD-first tests that assert the results JSON has the correct shape before any runner code is written.
- No new production modules beyond `scripts/eval.py` and the `eval/cases/*.yaml` files — the runner wires existing components only.
- `pyyaml` added as a runtime dependency via `uv add pyyaml`.

## Capabilities

### New Capabilities

- `eval-runner`: Eval script that loads YAML cases, runs the agent loop, and writes a per-case results JSON to `eval/results/<ts>.json`. Includes the YAML case schema (id, domain, category, task, expect, budget), the results JSON schema (per-case status, steps, USD, L-tier counts), and the validator vocabulary used by the two toy cases (`title.nonempty`, `*.len_gte: N`).

### Modified Capabilities

(none — `agent/loop.py`, `agent/trace.py`, `api/server.py` are not changed by this ticket)

## Impact

- **Code**: new `task2/scripts/__init__.py`, `task2/scripts/eval.py`, `task2/eval/__init__.py`, `task2/eval/cases/fixture-heading.yaml`, `task2/eval/cases/fixture-count.yaml`, `task2/tests/test_eval.py`.
- **Dependencies**: `pyyaml` added as runtime dep; no new dev deps.
- **Env vars**: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (already documented); `EVAL_CASES_DIR` (optional override for case directory, defaults to `eval/cases/` relative to `task2/`); `EVAL_RESULTS_DIR` (optional override for results directory, defaults to `eval/results/`).
- **Existing modules**: `agent/loop.py`, `agent/browser.py`, `agent/llm.py` consumed but not modified.
- **CLI**: `uv run python scripts/eval.py [--live] [--case <id>]` from `task2/`.
