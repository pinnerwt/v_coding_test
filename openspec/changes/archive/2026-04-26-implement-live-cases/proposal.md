## Why

The eval suite currently contains only fixture-backed cases (deterministic, no network), which means the agent's ability to complete real-world browser tasks is entirely unmeasured. Ticket #17 closes this gap by adding one live eval case per task category (categories 1–5), each targeting a real public site with no login or captcha requirement, gated behind the existing `--live` CLI flag so CI remains deterministic.

## What Changes

- Five new YAML case files under `task2/eval/cases/`, one per category: `live-search-extract.yaml`, `live-form-fill.yaml`, `live-multi-page-nav.yaml`, `live-conditional-pick.yaml`, `live-read-summarize.yaml`.
- Each live case has `live: true` (not `fixture: true`), so the existing `run_suite` skipping logic already gates them correctly behind `--live`.
- `task2/tests/test_live_gating.py`: new test module with TDD-first tests verifying (a) without `--live`, live cases produce `status == "skipped"` in the results JSON; (b) with `--live`, live cases are passed to `_run_case` rather than `_skipped_result`. The agent loop and browser are mocked — only runner gating logic is under test.
- `task2/README.md`: new section "Live eval results" documenting the last manual run scores honestly (leaderboard format, not pass/fail), per the brief.

## Capabilities

### New Capabilities

- `live-cases`: Five YAML eval cases (one per category 1–5) targeting real, login-free public URLs. Defines the site choices, task strings, expected output schemas, validators, and per-case budgets. Verifies eval runner gating logic (live-skipped without `--live`; live-included with `--live`).

### Modified Capabilities

- `eval-runner`: The `live` field in YAML cases is new; the existing `fixture` flag drives skipping, but the spec for `eval-runner` must now describe the `live` field as a recognized (non-`fixture`) case type whose gating behavior is tested.

## Impact

- **New files**: `task2/eval/cases/live-search-extract.yaml`, `task2/eval/cases/live-form-fill.yaml`, `task2/eval/cases/live-multi-page-nav.yaml`, `task2/eval/cases/live-conditional-pick.yaml`, `task2/eval/cases/live-read-summarize.yaml`, `task2/tests/test_live_gating.py`.
- **Modified files**: `task2/README.md` (new live results section).
- **Dependencies**: no new Python packages; uses existing `pyyaml`, `pytest`, `unittest.mock`.
- **Env vars**: none new; `EVAL_CASES_DIR`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` are unchanged.
- **Existing modules**: `scripts/eval.py` and `agent/loop.py` are consumed but not structurally modified; the `live` field in YAML is already handled by the existing `fixture`-flag gating logic (cases without `fixture: true` are skipped when `live=False`).
